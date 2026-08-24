"""RecoveryGainEvaluator：syntax-valid ≠ recovery-success。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.formula.tokens import (
    operator_direction_conflict,
    sanitize_recovery_context,
    token_consistency,
)
from app.formula.types import FormulaQuality


@dataclass
class GainDecision:
    accept: bool
    promising: bool
    gain: float
    token_overlap: float
    reasons: list[str] = field(default_factory=list)


_TRUNC_TAIL = re.compile(r"(?:\\frac|\\times|\+|-|=)\s*$")
# \left\{ ... \right. 等定界符：花括号不参与「截断」计数
# LaTeX 字面量花括号写作 \{ / \}，故定界符后可选多余反斜杠
_DELIM_BRACE = re.compile(
    r"\\(?:left|right|bigl|bigr|Bigl|Bigr|biggl|biggr|Biggl|Biggr)\s*"
    r"\\?(?:\{|\}|\.|\[|\]|\(|\))"
)


def _unbalanced_braces(latex: str) -> bool:
    """真正可疑的花括号不平衡（忽略 \\left\\{ / \\right. 配对）。"""
    t = _DELIM_BRACE.sub("", latex or "")
    return t.count("{") != t.count("}")


def _prose_like_recovery(latex: str) -> bool:
    """OCR 出散文+引用上标时拒绝写回。"""
    t = latex or ""
    words = re.findall(r"[A-Za-z]{4,}", t)
    if len(words) < 3:
        return False
    if "=" in t:
        return False
    return not re.search(
        r"\\(?:frac|sum|int|left|begin|mathrm|min|max|hat|bar)", t
    )


def looks_truncated(latex: str) -> bool:
    """启发式截断检测（7.3B：降低假阳性，避免挡掉 insufficient 放行）。

    不再把「公式末尾逗号」当成截断（OCR 常在 \\quad (n) 前留逗号）。
    不再把 \\left\\{...\\right. 的定界花括号当成不平衡。
    """
    s = (latex or "").strip()
    if not s:
        return False
    if _unbalanced_braces(s):
        return True
    if _TRUNC_TAIL.search(s):
        return True
    if s.endswith("\\") or s.endswith("{") or s.endswith("("):
        return True
    return False


_FORMULA_EVIDENCE = re.compile(
    r"\\mathfrak|\\mathbf|\\frac|e\s*\^|e\^\{-|\\begin\{(?:cases|aligned)",
    re.I,
)


def _before_latex_formula_evidence(text: str) -> bool:
    t = text or ""
    return "=" in t and bool(_FORMULA_EVIDENCE.search(t))


def _normalize_formula_core(text: str) -> str:
    t = re.sub(r"\s+", "", text or "")
    t = re.sub(r"\\stackrel\{[^}]*\}\{[^}]*\}", "", t, flags=re.I)
    t = re.sub(r"&+", "", t)
    return t.lower()


def _original_structurally_supports(before_latex: str, after_latex: str) -> bool:
    """损坏原文与恢复式结构一致时，不因纯上下文词元缺失而硬拒。"""
    b = re.sub(r"\s+", "", (before_latex or "").lower())
    a = re.sub(r"\s+", "", (after_latex or "").lower())
    if not b or not a or "=" not in b:
        return False
    ac = _normalize_formula_core(after_latex)
    bc = _normalize_formula_core(before_latex)
    if len(ac) >= 8 and ac in bc:
        return True
    if re.search(r"e\^?\{?-", b) and re.search(r"e\^?\{?-", a):
        if "p" in b and ("mathbf{p}" in a or "p(t)" in a.replace("{", "").replace("}", "")):
            return True
    if re.search(r"h_\{ic\}", b) and re.search(r"h_\{ic\}", a):
        return True
    return False


def repair_known_ocr_subscripts(before_latex: str, after_latex: str) -> str:
    """原文有明确下标时，修正常见 OCR 混淆（不发明公式内容）。"""
    out = after_latex or ""
    if not out or not (before_latex or "").strip():
        return out
    norm_before = re.sub(r"\s+", "", before_latex or "").lower()
    if "h_{ic}" in norm_before and re.search(r"H_\{\s*lc", out, re.I):
        out = re.sub(r"H_\{\s*lc\s*\}", r"H_{ic}", out, flags=re.I)
    return out


def _membership_subscript_conflict(
    before_latex: str,
    after_latex: str,
    context_before: str = "",
    context_after: str = "",
) -> tuple[bool, str]:
    blob = f"{context_before} {context_after} {before_latex}".lower()
    norm_before = re.sub(r"\s+", "", before_latex or "").lower()
    has_ic_evidence = (
        "h_{ic}" in norm_before
        or re.search(r"H_\{\s*i[cC]", before_latex or "", re.I)
        or re.search(r"membership|begin\{cases\}", blob, re.I)
    )
    if not has_ic_evidence:
        return False, ""
    ocr_subs = {m.lower() for m in re.findall(r"H_\{\s*([a-z]+)\s*\}", after_latex or "", re.I)}
    if "lc" in ocr_subs and "ic" not in ocr_subs:
        return True, "membership_subscript_mismatch"
    if re.search(r"\bV\s*\(", before_latex or "") and re.search(
        r"Vl\s*\(", (after_latex or "").replace(" ", "")
    ):
        if not re.search(r"V_\{?\s*l", after_latex or "", re.I):
            return True, "vi_notation_mismatch"
    return False, ""


def _brier_score_conflict(
    before_latex: str,
    after_latex: str,
    context_before: str,
) -> tuple[bool, str]:
    """Brier 定义段：OCR 不得写成 F1/Prec 或缺 \\sum/\\hat{p}。"""
    ctx = (context_before or "")[-320:].lower()
    if not re.search(r"\bbrier\s+score\b|mean squared error between outcomes", ctx):
        return False, ""
    after = (after_latex or "").lower()
    if re.search(r"\bf1\b|\\mathrm\{prec\}|\\mathrm\{rec\}", after) and "brier" not in after:
        return True, "brier_context_conflict"
    if re.search(r"\\sum|hat\{p\}|\\mathrm\{brier\}|brier\s*=", after):
        return False, ""
    return True, "brier_context_conflict"


def _classification_metrics_conflict(
    before_latex: str,
    after_latex: str,
    context_before: str,
) -> tuple[bool, str]:
    """F1/Prec/Rec/TP 类公式：原文或上下文要求完整分类指标，OCR 截断则拒写。"""
    ctx = (context_before or "")[-320:].lower()
    if not re.search(r"\bf1\b|f1@0|precision and recall", ctx):
        return False, ""
    norm_before = re.sub(r"\s+", "", (before_latex or "").lower())
    norm_after = re.sub(r"\s+", "", (after_latex or "").lower())
    before_has = bool(
        re.search(r"tp|fp|fn", norm_before)
        or re.search(r"pr\s*e\s*c|prec", norm_before)
        or "&=" in norm_before
    )
    after_has = bool(
        re.search(r"tp|fp|fn", norm_after) or re.search(r"prec|rec", norm_after)
    )
    if before_has and not after_has:
        return True, "classification_metrics_incomplete"
    if re.search(r"precision and recall", ctx) and "f1" in norm_after and not after_has:
        if re.search(r"\\frac", after_latex or ""):
            return True, "classification_metrics_incomplete"
    return False, ""


def _obvious_context_formula_mismatch(context_before: str, after_latex: str) -> bool:
    """上下文明确指向某类指标/公式，而 OCR 结果明显无关 → 硬拒（防 MSE 段写出 E=mc^2）。"""
    ctx = (context_before or "").lower()
    a = re.sub(r"\s+", "", (after_latex or "").lower())
    if re.search(r"\bmse\b|bias[\s-]*variance|mean\s+squared\s+error", ctx):
        if re.search(r"e=mc\^?2|e\{=mc", a):
            return True
    return False


def evaluate_recovery_gain(
    *,
    before_quality: FormulaQuality | None,
    after_quality: FormulaQuality | None,
    before_latex: str,
    after_latex: str,
    context_before: str,
    context_after: str,
    after_valid: bool,
) -> GainDecision:
    """比较恢复前后质量；无显著改善或上下文冲突则拒绝。"""
    reasons: list[str] = []
    after_latex = repair_known_ocr_subscripts(before_latex or "", after_latex or "")
    before_c = float(before_quality.corruption_score) if before_quality else 1.0
    after_c = float(after_quality.corruption_score) if after_quality else 1.0
    gain = before_c - after_c

    ctx_source = sanitize_recovery_context(
        f"{context_before or ''} {context_after or ''}"
    )
    before_source = sanitize_recovery_context(before_latex or "")
    if _before_latex_formula_evidence(before_source):
        source = f"{ctx_source} {before_source}".strip()
    else:
        source = ctx_source
    overlap, tok_reasons = token_consistency(source, after_latex or "")
    reasons.extend(tok_reasons)
    op_conflict, op_reasons = operator_direction_conflict(
        context_before or "",
        after_latex or "",
        original_latex=before_latex or "",
    )
    if op_conflict:
        reasons.extend(op_reasons)
        reasons.append("ocr_context_conflict")

    sub_conflict, sub_reason = _membership_subscript_conflict(
        before_latex or "",
        after_latex or "",
        context_before or "",
        context_after or "",
    )
    if sub_conflict:
        reasons.append(sub_reason or "symbol_structure_mismatch")
        reasons.append("ocr_context_conflict")

    metrics_conflict, metrics_reason = _classification_metrics_conflict(
        before_latex or "",
        after_latex or "",
        context_before or "",
    )
    if metrics_conflict:
        reasons.append(metrics_reason or "classification_metrics_incomplete")
        reasons.append("ocr_context_conflict")

    brier_conflict, brier_reason = _brier_score_conflict(
        before_latex or "",
        after_latex or "",
        context_before or "",
    )
    if brier_conflict:
        reasons.append(brier_reason or "brier_context_conflict")
        reasons.append("ocr_context_conflict")

    if _obvious_context_formula_mismatch(context_before or "", after_latex or ""):
        reasons.append("ocr_context_conflict")

    if (
        "ocr_context_conflict" in reasons
        and "operator_direction_conflict" not in reasons
        and _original_structurally_supports(before_latex or "", after_latex or "")
    ):
        reasons = [r for r in reasons if r != "ocr_context_conflict"]

    truncated = looks_truncated(after_latex or "")
    promising = truncated and "ocr_context_conflict" not in reasons

    if "ocr_context_conflict" in reasons:
        return GainDecision(
            accept=False,
            promising=False,
            gain=gain,
            token_overlap=overlap,
            reasons=reasons,
        )

    if not after_valid:
        if truncated:
            reasons.append("ocr_truncated")
        else:
            reasons.append("ocr_still_invalid")
        return GainDecision(
            accept=False,
            promising=promising,
            gain=gain,
            token_overlap=overlap,
            reasons=reasons,
        )

    if _prose_like_recovery(after_latex or ""):
        reasons.append("ocr_prose_recovery")
        return GainDecision(
            accept=False,
            promising=False,
            gain=gain,
            token_overlap=overlap,
            reasons=reasons,
        )

    # Phase 6C：context_insufficient 不是 hard veto；要求语法有效 + 低 corruption
    insufficient = "ocr_context_insufficient" in reasons
    symbol_ok = "symbol_signature_support" in reasons
    if insufficient:
        after_ok = after_c <= 0.45 and after_valid and not truncated
        symbol_strong = (
            symbol_ok
            and after_valid
            and not truncated
            and after_c <= 0.35
            and gain >= 0.5
            and overlap >= 0.25
        )
        if not after_ok and not symbol_strong:
            reasons.append("insufficient_without_strong_evidence")
            return GainDecision(
                accept=False,
                promising=False,
                gain=gain,
                token_overlap=overlap,
                reasons=reasons,
            )
        # 有强正向证据：syntax valid + low corruption / symbol 签名 → 可接受
        reasons.append(
            "accept_despite_insufficient_context"
            if not symbol_strong
            else "accept_symbol_signature_support"
        )
        return GainDecision(
            accept=True,
            promising=False,
            gain=max(gain, 0.2),
            token_overlap=overlap,
            reasons=reasons,
        )

    # syntax-valid 不够：必须比原文有改善，或原文已经很脏且词元对得上
    if gain < 0.15 and before_c < 0.5:
        reasons.append("no_significant_gain")
        return GainDecision(
            accept=False,
            promising=False,
            gain=gain,
            token_overlap=overlap,
            reasons=reasons,
        )

    if overlap < 0.05 and before_c < 0.75 and not insufficient:
        # 原文不脏但 OCR 换了一套无关符号
        reasons.append("no_significant_gain")
        return GainDecision(
            accept=False,
            promising=False,
            gain=gain,
            token_overlap=overlap,
            reasons=reasons,
        )

    reasons.append("gain_accept")
    return GainDecision(
        accept=True,
        promising=False,
        gain=gain,
        token_overlap=overlap,
        reasons=reasons,
    )
