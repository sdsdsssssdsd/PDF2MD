"""FormulaValidator：语法层 + 调用 CorruptionDetector 合成 FormulaQuality。"""
from __future__ import annotations

from app.formula.config import FormulaConfig
from app.formula.corruption import assess_corruption, context_mismatch
from app.formula.types import FormulaQuality, ValidationResult


def validate_latex(
    text: str,
    cfg: FormulaConfig | None = None,
    *,
    context_before: str = "",
    context_after: str = "",
) -> ValidationResult:
    cfg = cfg or FormulaConfig()
    body = text.strip()
    if body.startswith("$$") and body.endswith("$$"):
        body = body[2:-2].strip()
    elif body.startswith("$") and body.endswith("$") and not body.startswith("$$"):
        body = body[1:-1].strip()

    if not body:
        q = FormulaQuality(
            syntax_score=0.0,
            corruption_score=1.0,
            valid=False,
            recoverable=True,
            reasons=["empty"],
        )
        return ValidationResult(valid=False, issues=["empty"], severity=1.0, quality=q)

    q = assess_corruption(body, cfg)
    mismatch = context_mismatch(body, context_before, context_after)
    if mismatch:
        q.reasons.extend(mismatch)
        q.semantic_score = min(q.semantic_score, 0.3)
        q.corruption_score = max(q.corruption_score, 0.85)
        q.valid = False
        q.recoverable = True

    if len(body) > cfg.max_formula_chars and "too_long" not in q.reasons:
        q.reasons.append("too_long")
        q.corruption_score = max(q.corruption_score, 0.7)
        if q.corruption_score >= 0.75:
            q.valid = False
            q.recoverable = True

    severity = max(q.corruption_score, 1.0 - q.syntax_score, 1.0 - q.semantic_score)
    return ValidationResult(
        valid=q.valid,
        issues=list(q.reasons),
        severity=severity,
        quality=q,
    )
