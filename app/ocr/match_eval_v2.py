# -*- coding: utf-8 -*-
"""FormulaMatchEvaluator v2 — 仅 Benchmark，禁止写回生产 Markdown。

k5：旧版 exact_normalized_match 含「子串即 exact」，不能再当 Exact Match。
本模块提供严格 Canonical Exact；CDM 直接接 OmniDocBench（未安装则为 None）。
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from app.ocr.match_eval import FormulaMatchEvaluator, normalize_latex

FailureLayer = Literal[
    "DETECTION_FAILURE",
    "GEOMETRY_FAILURE",
    "CROP_CLIPPED",
    "OCR_FAILURE",
    "POSTPROCESS_FAILURE",
    "GATE_FALSE_REJECT",
    "GATE_FALSE_ACCEPT",
    "WRITEBACK_FAILURE",
    "OK",
    "NO_GOLD",
    "EMPTY_CANDIDATE",
]

_SPACE = re.compile(r"\s+")
_TAG = re.compile(r"\\tag\*?\{[^}]*\}|\\eqno\b\s*(?:\([^)]*\)|\d+)?")
_LEFT_RIGHT = re.compile(r"\\(?:left|right|big|Big|bigg|Bigg)\s*")
_DFRAC = re.compile(r"\\(?:dfrac|tfrac)\b")
_QUAD = re.compile(r"\\(?:quad|qquad|,|;|!)\b|~+")
_BEGIN_END = re.compile(r"\\begin\{([^}]+)\}(?:\{[^}]*\})?|\\end\{([^}]+)\}")
_CMD = re.compile(r"\\[a-zA-Z]+|[{}\[\]()^_=+\-*/,]|[A-Za-z0-9]+|\\.|.")
# 字体包裹是样式，不是语义别名。保留 mathcal/mathscr/mathfrak（改字母身份）。
_FONT_WRAP = re.compile(
    r"\\(?:mathrm|operatorname|mathbf|boldsymbol|mathit|mathtt|textrm|textbf|text)\s*\{([^{}]*)\}"
)
_TRAILING_EQNUM = re.compile(r"[\(（]\s*\d{1,3}[a-zA-Z]?\s*[\)）]\s*\.?\s*$")


def _unwrap_font_commands(s: str) -> str:
    prev = None
    while prev != s:
        prev = s
        s = _FONT_WRAP.sub(r"\1", s)
    return s


def _strip_trailing_display_number(s: str) -> str:
    """k5 §七：编号与内容分离。有等号的整式尾标 (n) 去掉；P(0) 这类无等号调用保留。"""
    m = _TRAILING_EQNUM.search(s)
    if not m:
        return s
    head = s[: m.start()]
    if "=" in head:
        return head
    return s


def canonicalize_latex(text: str) -> str:
    """严格规范化：去围栏/编号/尺寸/字体包裹，保留结构 token。

    不做语义别名折叠（Var≠V、\\times≠*、\\mathcal{Y}≠y）。
    """
    s = (text or "").strip()
    s = s.replace("$$", "").replace("$", "")
    s = _TAG.sub("", s)
    s = _unwrap_font_commands(s)
    s = _BEGIN_END.sub("", s)
    s = _LEFT_RIGHT.sub("", s)
    s = _DFRAC.sub(r"\\frac", s)
    s = _QUAD.sub("", s)
    s = s.replace("{", "").replace("}", "")
    s = s.replace("&", "")
    s = _SPACE.sub("", s)
    s = _strip_trailing_display_number(s)
    s = s.rstrip(".,")
    return s


def latex_tokens(text: str) -> list[str]:
    s = canonicalize_latex(text)
    if not s:
        return []
    return [m.group(0) for m in _CMD.finditer(s)]


def token_edit_distance(a: str, b: str) -> int:
    ta, tb = latex_tokens(a), latex_tokens(b)
    if ta == tb:
        return 0
    n, m = len(ta), len(tb)
    if n == 0:
        return m
    if m == 0:
        return n
    prev = list(range(m + 1))
    for i, ca in enumerate(ta, 1):
        cur = [i] + [0] * m
        for j, cb in enumerate(tb, 1):
            cost = 0 if ca == cb else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[m]


def latex_brace_ok(text: str) -> bool:
    depth = 0
    for ch in text or "":
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def latex_environments_ok(text: str) -> bool:
    stack: list[str] = []
    for m in re.finditer(r"\\(begin|end)\{([^}]+)\}", text or ""):
        kind, name = m.group(1), m.group(2)
        if kind == "begin":
            stack.append(name)
        elif not stack or stack.pop() != name:
            return False
    return not stack


def compile_rate_ok(text: str) -> bool:
    """轻量 compile：括号/环境合法。不调用外部 TeX（CDM 才走 OmniDocBench）。"""
    s = (text or "").strip()
    if not s:
        return False
    if not latex_brace_ok(s):
        return False
    if not latex_environments_ok(s):
        return False
    if r"\end" in s and r"\begin" not in s:
        return False
    return True


def structure_diagnostics(text: str) -> dict[str, Any]:
    s = text or ""
    return {
        "frac": len(re.findall(r"\\frac\b|\\over\b", s)),
        "scripts": len(re.findall(r"[_^]", s)),
        "matrix": len(re.findall(r"\\begin\{[bp]?matrix\}", s)),
        "cases": len(re.findall(r"\\begin\{cases\}", s)),
        "align": len(re.findall(r"\\begin\{(?:align|aligned|split|gather)", s)),
        "sum_prod_int": len(re.findall(r"\\(?:sum|prod|int|oint|lim)\b", s)),
        "text": len(re.findall(r"\\text\{", s)),
        "fonts": len(re.findall(r"\\(?:mathbf|mathcal|mathrm|boldsymbol|mathscr)\b", s)),
        "accents": len(re.findall(r"\\(?:hat|bar|tilde|dot|ddot|vec)\b", s)),
        "left_right": len(re.findall(r"\\(?:left|right)\b", s)),
        "chars": len(s),
    }


def try_compute_cdm(pred: str, gold: str) -> float | None:
    """直接接 OmniDocBench CDM；未安装则返回 None，禁止自制分数冒充 CDM。"""
    compute_cdm = None
    try:
        from cdmeval import compute_cdm as compute_cdm  # type: ignore
    except Exception:
        try:
            from omnidocbench.metrics.cdm import compute_cdm as compute_cdm  # type: ignore
        except Exception:
            return None
    if compute_cdm is None:
        return None
    try:
        return float(compute_cdm(pred, gold))
    except Exception:
        return None


def classify_production_failure(
    *,
    geometry_ok: bool = True,
    crop_ok: bool = True,
    detection_ok: bool = True,
    ocr_ok: bool = False,
    exact: bool = False,
    gate_accepted: bool | None = None,
    writeback_applied: bool | None = None,
    gold_correct: bool | None = None,
) -> FailureLayer:
    if gold_correct is None and not (gold_correct is False):
        pass
    if not detection_ok:
        return "DETECTION_FAILURE"
    if not geometry_ok:
        return "GEOMETRY_FAILURE"
    if not crop_ok:
        return "CROP_CLIPPED"
    if not ocr_ok and not exact:
        if gate_accepted is True and gold_correct is False:
            return "GATE_FALSE_ACCEPT"
        return "OCR_FAILURE"
    if exact and gate_accepted is False:
        return "GATE_FALSE_REJECT"
    if gate_accepted is True and gold_correct is False:
        return "GATE_FALSE_ACCEPT"
    if gate_accepted is True and writeback_applied is False:
        return "WRITEBACK_FAILURE"
    if ocr_ok and not exact and gold_correct is True:
        return "POSTPROCESS_FAILURE"
    if exact:
        return "OK"
    return "OCR_FAILURE"


@dataclass
class MatchReportV2:
    strict_canonical_exact: bool = False
    token_edit_distance: int = 0
    token_edit_ratio: float = 1.0
    cdm: float | None = None
    cdm_available: bool = False
    compile_ok: bool = False
    structure: dict[str, Any] = field(default_factory=dict)
    legacy_exact_substring: bool = False
    candidate_canonical: str = ""
    gold_canonical: str = ""
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class FormulaMatchEvaluatorV2:
    """严格评测器。legacy 子串 exact 只作为对照字段，不再叫 Exact。"""

    def __init__(self, *, compute_cdm: bool = True) -> None:
        self.compute_cdm = compute_cdm
        self._legacy = FormulaMatchEvaluator()

    def compare(self, candidate: str, gold: str) -> MatchReportV2:
        reasons: list[str] = []
        if not (gold or "").strip():
            return MatchReportV2(reasons=["no_gold"])
        if not (candidate or "").strip():
            return MatchReportV2(
                reasons=["empty_candidate"],
                gold_canonical=canonicalize_latex(gold),
                compile_ok=False,
            )

        cc = canonicalize_latex(candidate)
        gc = canonicalize_latex(gold)
        exact = bool(cc and gc and cc == gc)
        if exact:
            reasons.append("strict_canonical_exact")
        else:
            reasons.append("strict_mismatch")

        dist = token_edit_distance(candidate, gold)
        denom = max(1, len(latex_tokens(gold)))
        ratio = dist / denom

        cdm: float | None = None
        if self.compute_cdm:
            cdm = try_compute_cdm(candidate, gold)
            if cdm is None:
                reasons.append("cdm_unavailable")
            else:
                reasons.append("cdm")

        compile_ok = compile_rate_ok(candidate)
        if compile_ok:
            reasons.append("compile_ok")
        else:
            reasons.append("compile_fail")

        legacy = self._legacy.compare(candidate, gold)
        if legacy.exact_normalized_match and not exact:
            reasons.append("legacy_substring_exact_not_strict")

        return MatchReportV2(
            strict_canonical_exact=exact,
            token_edit_distance=dist,
            token_edit_ratio=round(ratio, 4),
            cdm=cdm,
            cdm_available=cdm is not None,
            compile_ok=compile_ok,
            structure=structure_diagnostics(candidate),
            legacy_exact_substring=bool(legacy.exact_normalized_match),
            candidate_canonical=cc,
            gold_canonical=gc,
            reasons=reasons,
        )


def summarize_reports(
    rows: list[MatchReportV2],
    *,
    language: str | None = None,
) -> dict[str, Any]:
    del language
    n = len(rows)
    if n == 0:
        return {
            "n": 0,
            "strict_canonical_exact": 0.0,
            "mean_token_edit_ratio": 0.0,
            "compile_rate": 0.0,
            "cdm_mean": None,
            "cdm_n": 0,
        }
    exact_n = sum(1 for r in rows if r.strict_canonical_exact)
    compile_n = sum(1 for r in rows if r.compile_ok)
    cdms = [float(r.cdm) for r in rows if r.cdm is not None]
    return {
        "n": n,
        "strict_canonical_exact": round(exact_n / n, 4),
        "mean_token_edit_ratio": round(sum(r.token_edit_ratio for r in rows) / n, 4),
        "compile_rate": round(compile_n / n, 4),
        "cdm_mean": round(sum(cdms) / len(cdms), 4) if cdms else None,
        "cdm_n": len(cdms),
        "note": "micro_per_formula; paper_macro_computed_by_runner",
    }
