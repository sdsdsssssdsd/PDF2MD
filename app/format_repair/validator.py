"""最终 Markdown / Typora 校验。"""
from __future__ import annotations

from app.repair.validator import validate_markdown
from app.utils.typora_math_repair import lint_typora_math


def validate_repaired_markdown(md: str) -> list[str]:
    warnings = list(validate_markdown(md or ""))
    warnings.extend(
        f"Typora {issue.code}: {issue.message}" for issue in lint_typora_math(md or "")
    )
    return warnings

