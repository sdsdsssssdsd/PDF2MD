"""FormulaMatchEvaluator — 仅用于 Benchmark / 离线校准，禁止写回生产 Markdown。

分层：
  exact_normalized_match  — 归一化后字符串一致（含少量别名）
  structural_match          — = / \\frac / 分子分母骨架一致
  token_match               — 关键数学词元重叠
  human_usable              — 结构可用 + 关键 token（人工等价）
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

LayerFailure = Literal[
    "extractor_success",
    "extractor_failure",
    "ocr_failure",
    "no_gold",
    "empty_candidate",
]


_SPACE = re.compile(r"\s+")
_LEFT_RIGHT = re.compile(r"\\(?:left|right|big|Big|bigg|Bigg)\s*")
_MATHRM = re.compile(r"\\(?:mathrm|mathbf|boldsymbol|mathscr|mathit|textrm|textbf)\s*\{([^{}]*)\}")
_BEGIN_END = re.compile(r"\\begin\{[^}]+\}|\\end\{[^}]+\}")
_QUAD = re.compile(r"\\(?:quad|qquad|,|;|!)|~+")
_AMP = re.compile(r"&+")


# 仅 benchmark 用的等价别名（生产不得据此改写公式）
_ALIASES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bvar(?:iance)?\b", re.I), "v"),
    (re.compile(r"\\varepsilon|\\epsilon|\bvarepsilon\b|\bepsilon\b", re.I), "eps"),
    (re.compile(r"\\times|\\cdot|×"), "*"),
    (re.compile(r"\\frac"), "FRAC"),
]


def normalize_latex(text: str) -> str:
    s = (text or "").strip()
    s = s.replace("$$", "").replace("$", "")
    s = _BEGIN_END.sub("", s)
    s = _LEFT_RIGHT.sub("", s)
    s = _MATHRM.sub(r"\1", s)
    s = _QUAD.sub("", s)
    s = _AMP.sub("", s)
    s = s.replace("{", "").replace("}", "")
    s = s.replace("\\", "")
    s = _SPACE.sub("", s)
    s = s.lower()
    for pat, repl in _ALIASES:
        s = pat.sub(repl, s)
    # 再压一次空白
    s = _SPACE.sub("", s)
    return s


def _frac_skeleton(text: str) -> list[tuple[str, str]]:
    """提取 \\frac{a}{b} → [(na, nb), ...]（已 normalize 片段）。"""
    out: list[tuple[str, str]] = []
    # 简易栈解析
    i = 0
    raw = text or ""
    while True:
        j = raw.find("\\frac", i)
        if j < 0:
            break
        k = j + 5
        while k < len(raw) and raw[k].isspace():
            k += 1
        if k >= len(raw) or raw[k] != "{":
            i = j + 5
            continue

        def read_brace(pos: int) -> tuple[str, int] | None:
            if pos >= len(raw) or raw[pos] != "{":
                return None
            depth = 0
            p = pos
            while p < len(raw):
                if raw[p] == "{":
                    depth += 1
                elif raw[p] == "}":
                    depth -= 1
                    if depth == 0:
                        return raw[pos + 1 : p], p + 1
                p += 1
            return None

        num = read_brace(k)
        if not num:
            i = j + 5
            continue
        den = read_brace(num[1])
        if not den:
            i = j + 5
            continue
        out.append((normalize_latex(num[0]), normalize_latex(den[0])))
        i = den[1]
    return out


def _structure_signature(text: str) -> dict[str, Any]:
    s = text or ""
    fracs = _frac_skeleton(s)
    return {
        "has_eq": "=" in s or r"=" in s,
        "frac_n": len(fracs),
        "fracs": fracs,
        "ops": sorted(
            {
                m.group(0)
                for m in re.finditer(r"\\(?:times|cdot|frac|sum|prod|left|right)|[+\-*/=^_]", s)
            }
        ),
        "scripts": len(re.findall(r"[_^]", s)),
    }


_TOKEN_RE = re.compile(
    r"\b(TP|TN|FP|FN|TPR|FPR|MSE|F1|Bias|Recall|Precision|Accuracy|Var|Variance|"
    r"varepsilon|epsilon)\b|\\(?:frac|times|mathrm|hat|varepsilon|epsilon)|"
    r"(?<![A-Za-z])(?:TP|TN|FP|FN|TPR|FPR)(?![A-Za-z])",
    re.I,
)


def extract_structure_tokens(text: str) -> set[str]:
    out: set[str] = set()
    for m in _TOKEN_RE.finditer(text or ""):
        tok = m.group(0).lower().lstrip("\\")
        if tok in {"mathrm", "hat"}:
            continue
        if tok in {"var", "variance"}:
            out.add("v")
        elif tok in {"varepsilon", "epsilon"}:
            out.add("eps")
        else:
            out.add(tok)
    # frac 分子分母里的短 token
    for a, b in _frac_skeleton(text or ""):
        for piece in (a, b):
            for part in re.findall(r"[a-z0-9]+", piece):
                if part in {"tp", "tn", "fp", "fn", "tpr", "fpr", "bias", "v", "eps", "y", "f"}:
                    out.add(part)
                if part in {"var", "variance"}:
                    out.add("v")
    return out


@dataclass
class MatchReport:
    exact_normalized_match: bool = False
    structural_match: bool = False
    token_match: bool = False
    human_usable: bool = False
    token_overlap: float = 0.0
    reasons: list[str] = field(default_factory=list)
    candidate_norm: str = ""
    gold_norm: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LayerReport:
    """区分 OCR 层 vs Extractor 层失败。"""

    raw_contains_usable: bool = False
    selected_usable: bool = False
    selected_exact: bool = False
    layer: LayerFailure = "no_gold"
    extractor_gap: bool = False  # raw 可用但 selected 不可用

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class FormulaMatchEvaluator:
    """Benchmark-only 匹配器。"""

    def compare(self, candidate: str, gold: str) -> MatchReport:
        reasons: list[str] = []
        if not (gold or "").strip():
            return MatchReport(reasons=["no_gold"])
        if not (candidate or "").strip():
            return MatchReport(reasons=["empty_candidate"], gold_norm=normalize_latex(gold))

        cn = normalize_latex(candidate)
        gn = normalize_latex(gold)
        exact = bool(cn and gn and (cn == gn or cn in gn or gn in cn))
        if exact:
            reasons.append("exact_normalized")

        cs = _structure_signature(candidate)
        gs = _structure_signature(gold)
        structural = False
        if gs["has_eq"] and cs["has_eq"]:
            if gs["frac_n"] == 0:
                # 无分式：归一化后高度相似或共享关键 ops
                structural = exact or (abs(len(cn) - len(gn)) <= max(4, len(gn) // 5) and cn[:8] == gn[:8])
            elif gs["frac_n"] > 0 and cs["frac_n"] > 0:
                # 至少一对 frac 骨架兼容
                structural = self._fracs_compatible(cs["fracs"], gs["fracs"])
            else:
                structural = False
        elif exact:
            structural = True
        if structural:
            reasons.append("structural_match")
        else:
            reasons.append("structural_mismatch")

        ct = extract_structure_tokens(candidate)
        gt = extract_structure_tokens(gold)
        if not gt:
            tok_overlap = 1.0 if exact else 0.0
        else:
            tok_overlap = len(ct & gt) / max(1, len(gt))
        token_ok = tok_overlap >= 0.5 or (exact and tok_overlap >= 0.3)
        if token_ok:
            reasons.append("token_match")

        # human_usable：结构对 + 关键 token；或 exact
        # Eq.(1) V vs Var：normalize 后 exact；若结构 + bias/eps/y 对上也算 usable
        human = False
        if exact and structural:
            human = True
            reasons.append("human_usable_exact")
        elif structural and token_ok:
            human = True
            reasons.append("human_usable_structural")
        elif structural and ("bias" in gt or "tp" in gt or "tpr" in gt or "fpr" in gt or "f1" in gt or "recall" in gt):
            # 分式骨架对且 gold 是指标式，候选含同族 token
            key = gt & {"bias", "tp", "tn", "fp", "fn", "tpr", "fpr", "f1", "recall", "precision", "eps", "v", "y"}
            if key and (ct & key):
                human = True
                reasons.append("human_usable_key_tokens")

        return MatchReport(
            exact_normalized_match=exact,
            structural_match=structural,
            token_match=token_ok,
            human_usable=human,
            token_overlap=round(tok_overlap, 3),
            reasons=reasons,
            candidate_norm=cn,
            gold_norm=gn,
        )

    @staticmethod
    def _fracs_compatible(
        cand: list[tuple[str, str]], gold: list[tuple[str, str]]
    ) -> bool:
        if not gold or not cand:
            return False
        for ga, gb in gold:
            for ca, cb in cand:
                # 分子分母 token 集合近似
                if _piece_close(ca, ga) and _piece_close(cb, gb):
                    return True
        return False

    def layer_report(
        self,
        *,
        raw_ocr: str,
        selected: str,
        gold: str,
    ) -> LayerReport:
        if not (gold or "").strip():
            return LayerReport(layer="no_gold")
        raw_m = self.compare(raw_ocr, gold)
        # raw 可能很长：若整页含 gold 结构，也算 contains
        raw_ok = raw_m.human_usable or raw_m.structural_match or raw_m.exact_normalized_match
        if not raw_ok and raw_ocr:
            # 在原文中找最像的 display 块再比一次
            raw_ok = self._raw_has_usable_formula(raw_ocr, gold)

        if not (selected or "").strip():
            if raw_ok:
                return LayerReport(
                    raw_contains_usable=True,
                    selected_usable=False,
                    layer="extractor_failure",
                    extractor_gap=True,
                )
            return LayerReport(
                raw_contains_usable=False,
                selected_usable=False,
                layer="ocr_failure" if not raw_ok else "empty_candidate",
            )

        sel_m = self.compare(selected, gold)
        if not raw_ok:
            return LayerReport(
                raw_contains_usable=False,
                selected_usable=sel_m.human_usable,
                selected_exact=sel_m.exact_normalized_match,
                layer="ocr_failure",
                extractor_gap=False,
            )
        if sel_m.human_usable or sel_m.exact_normalized_match:
            return LayerReport(
                raw_contains_usable=True,
                selected_usable=True,
                selected_exact=sel_m.exact_normalized_match,
                layer="extractor_success",
                extractor_gap=False,
            )
        return LayerReport(
            raw_contains_usable=True,
            selected_usable=False,
            selected_exact=False,
            layer="extractor_failure",
            extractor_gap=True,
        )

    def _raw_has_usable_formula(self, raw: str, gold: str) -> bool:
        from app.ocr.extractor import parse_equation_blocks

        for b in parse_equation_blocks(raw):
            m = self.compare(b.latex_or_text, gold)
            if m.human_usable or m.structural_match or m.exact_normalized_match:
                return True
        # 宽松：归一化 gold 核心出现在 raw
        gn = normalize_latex(gold)
        rn = normalize_latex(raw)
        if len(gn) >= 8 and gn in rn:
            return True
        core = re.sub(r"^(recall|f1|tpr|fpr|precision|accuracy)=", "", gn)
        if len(core) >= 8 and core in rn:
            return True
        return False


def _piece_close(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    if a in b or b in a:
        return True
    # TP+FN vs TP+FN 等
    sa, sb = set(re.findall(r"[a-z0-9]+", a)), set(re.findall(r"[a-z0-9]+", b))
    if not sb:
        return False
    return len(sa & sb) / len(sb) >= 0.66
