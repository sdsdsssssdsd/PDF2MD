"""终稿校验包装。"""
from __future__ import annotations

from app.format_repair.validator import validate_repaired_markdown
from app.utils.typora_math_repair import lint_typora_math


def validate_corrected_markdown(md: str) -> list[str]:
    warnings = list(validate_repaired_markdown(md or ""))
    for issue in lint_typora_math(md or ""):
        if issue.code in {"T-undef-cmd"}:
            warnings.append(f"Typora {issue.code}: {issue.message}")
    return warnings
