"""UnwrappedFormulaDetector：评分器，不猜 LaTeX。"""
from __future__ import annotations

import re

from app.formula.config import FormulaConfig
from app.formula.types import DetectionHit

_MATH_OPS = set("=+-/*^_<>≤≥≈≠∈∉⊂⊃∪∩×±∞→←∂∑∫√⋅·")
_UNICODE_MATH = re.compile(
    r"[∈∉⊂⊃∪∩×±∞≤≥≈≠→←∂∑∫√⋅·πΠσΣαβγδελμθωϕφψ]|ˆ|˛|"
    r"[\U0001D400-\U0001D7FF]"
)
_VAR_PATTERN = re.compile(
    r"\b(?:p_?i|n_?b|x_?i|y_?i|TPR|FPR|F1|TP|FP|TN|FN|ECE|Brier|"
    r"conf|acc|IMD|TMA\d*)\b",
    re.I,
)
_OCR_JUNK = re.compile(r"˛|nb=\{|pi\s|n\s+b\s*=|b\s*-1B|1\|\s*n")
_EN_STOP = frozenset(
    "the a an and or but if then else when while for from with without "
    "into onto upon over under about after before between among against "
    "through during until that this these those there here is are was were "
    "be been being have has had do does did can could may might must shall "
    "should will would we you they he she it of to in on at by as".split()
)


def score_span(text: str) -> tuple[float, list[str]]:
    """返回 (0~1 分数, reasons)。越高越像漏检公式。"""
    s = text.strip()
    if len(s) < 4:
        return 0.0, []
    reasons: list[str] = []
    score = 0.0

    op_hits = sum(1 for ch in s if ch in _MATH_OPS)
    if op_hits:
        score += min(0.35, 0.08 * op_hits)
        reasons.append("math_ops")

    if _UNICODE_MATH.search(s):
        score += 0.25
        reasons.append("unicode_math")

    if _VAR_PATTERN.search(s):
        score += 0.2
        reasons.append("math_vars")

    braces = s.count("{") + s.count("}") + s.count("[") + s.count("]")
    if braces >= 2:
        score += 0.15
        reasons.append("brackets")

    if _OCR_JUNK.search(s):
        score += 0.35
        reasons.append("ocr_formula_junk")

    # 定义结构 A = ...
    if re.search(r"\b[A-Za-z][A-Za-z0-9_]*\s*=\s*\S", s):
        score += 0.15
        reasons.append("assignment")

    # 自然语言比例下降
    tokens = re.findall(r"[A-Za-z]+", s)
    if tokens:
        stop_n = sum(1 for t in tokens if t.lower() in _EN_STOP)
        ratio = stop_n / len(tokens)
        if len(tokens) >= 4 and ratio < 0.25:
            score += 0.2
            reasons.append("low_english")
        if len(tokens) >= 4 and ratio > 0.55 and op_hits == 0 and not _UNICODE_MATH.search(s):
            score -= 0.25
            reasons.append("mostly_english")

    # 已有 $ 定界则不是 unwrapped
    if "$" in s:
        score -= 0.5
        reasons.append("already_delimited")

    return max(0.0, min(1.0, score)), reasons


def detect_unwrapped(md: str, cfg: FormulaConfig | None = None) -> list[DetectionHit]:
    """在非代码/非已有公式区域扫描疑似漏检公式。

    Phase 1：只检测，不改写为 LaTeX。
    """
    cfg = cfg or FormulaConfig()
    if not cfg.detection_enabled:
        return []

    hits: list[DetectionHit] = []
    # 保护已有公式与代码
    protected = []
    for m in re.finditer(
        r"```[\s\S]*?```|\$\$[\s\S]*?\$\$|(?<!\$)\$(?!\$)(?:\\.|[^$\\])+?\$(?!\$)",
        md,
    ):
        protected.append((m.start(), m.end()))

    def _is_protected(i: int) -> bool:
        return any(a <= i < b for a, b in protected)

    # 按句子/分号粗切，再对窗口打分
    for m in re.finditer(r"[^\n.!?]{8,220}", md):
        if _is_protected(m.start()):
            continue
        span = m.group(0)
        # 跳过纯 Markdown 结构
        if span.lstrip().startswith(("#", "|", "!", "[", ">")):
            continue
        if re.match(r"^\s*[-*]\s", span):
            continue
        sc, reasons = score_span(span)
        if sc >= cfg.suspicious_threshold:
            hits.append(
                DetectionHit(
                    text=span.strip(),
                    score=sc,
                    start=m.start(),
                    end=m.end(),
                    reasons=reasons,
                )
            )

    # 去重叠：保留高分
    hits.sort(key=lambda h: (-h.score, h.start))
    kept: list[DetectionHit] = []
    used: list[tuple[int, int]] = []
    for h in hits:
        if any(not (h.end <= a or h.start >= b) for a, b in used):
            continue
        kept.append(h)
        used.append((h.start, h.end))
    return kept
