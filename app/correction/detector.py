"""Issue 检测总入口。"""
from __future__ import annotations

from app.correction.latex_detector import detect_latex_issues
from app.correction.math_detector import detect_lost_inline_delimiters
from app.correction.models import CorrectionIssue


def detect_issues(text: str) -> list[CorrectionIssue]:
    issues: list[CorrectionIssue] = []
    issues.extend(detect_latex_issues(text, start_id=1))
    base = len(issues) + 1
    issues.extend(detect_lost_inline_delimiters(text, start_id=base))
    return issues
