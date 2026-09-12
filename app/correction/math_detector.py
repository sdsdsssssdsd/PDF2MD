"""数学上下文异常检测。"""
from __future__ import annotations

import re

from app.correction.models import CorrectionIssue

_EQ_REF_LEFT = re.compile(
    r"(?:公式|式|Eq\.?|Equation|equation|见|由|式\s*\(|公式\s*\()\s*$",
    re.I,
)
_VAR_LEFT = re.compile(
    r"(?:若|当|如果|其中|即|对任意|令|设|记|为|满足|where|when|if|for|let)\s*$",
    re.I,
)
_VAR_RIGHT = re.compile(
    r"^\s*(?:为|是|满足|时|则|的|，|,|。|；|；|奇|偶|大于|小于|成立|表示|denotes|is|are|holds)",
    re.I,
)
_INLINE_VAR = re.compile(r"\((?P<var>[a-zA-Z])\)")


def detect_lost_inline_delimiters(
    text: str,
    *,
    start_id: int = 1,
) -> list[CorrectionIssue]:
    issues: list[CorrectionIssue] = []
    idx = start_id
    for m in _INLINE_VAR.finditer(text or ""):
        inner = m.group("var")
        left = text[max(0, m.start() - 24) : m.start()]
        right = text[m.end() : m.end() + 24]
        token = m.group(0)
        if _EQ_REF_LEFT.search(left) or inner.isdigit():
            continue
        if not (_VAR_LEFT.search(left) or _VAR_RIGHT.search(right)):
            continue
        issues.append(
            CorrectionIssue(
                issue_id=f"MATH-{idx:04d}",
                kind="possible_lost_inline_math_delimiter",
                start=m.start(),
                end=m.end(),
                before=token,
                after=f"${inner}$",
                severity="medium",
                left_context=text[max(0, m.start() - 200) : m.start()],
                right_context=text[m.end() : m.end() + 200],
                environment="prose",
            )
        )
        idx += 1
    return issues
