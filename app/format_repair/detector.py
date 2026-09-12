"""格式问题检测。"""
from __future__ import annotations

import re

from app.format_repair.models import FormatIssue
from app.format_repair.rules import is_display_only_math, score_display_block

_LATEX_INLINE_RE = re.compile(r"\\\((?P<body>.*?)\\\)", re.DOTALL)
_LATEX_DISPLAY_RE = re.compile(r"\\\[(?P<body>.*?)\\\]", re.DOTALL)
_SINGLE_DISPLAY_RE = re.compile(r"\$\$(?P<body>[^\n$]*)\$\$")


def detect_format_issues(text: str) -> list[FormatIssue]:
    issues: list[FormatIssue] = []
    for pattern, kind, wrapper in (
        (_LATEX_INLINE_RE, "latex_inline", "$"),
        (_LATEX_DISPLAY_RE, "latex_display", "$$"),
        (_SINGLE_DISPLAY_RE, "single_line_display", "$$"),
    ):
        for index, m in enumerate(pattern.finditer(text or ""), start=1):
            body = (m.group("body") or "").strip()
            issues.append(
                FormatIssue(
                    id=f"issue_{index:03d}",
                    kind=kind,
                    start=m.start(),
                    end=m.end(),
                    original=m.group(0),
                    replacement=f"{wrapper}{body}{wrapper}",
                    reason=kind,
                )
            )
    return issues


def detect_ambiguous_display_blocks(
    text: str,
    *,
    min_score: int = 40,
    max_score: int = 70,
) -> list[dict]:
    pattern = re.compile(r"\$\$\s*\n(?P<body>.*?)\n\s*\$\$", re.DOTALL)
    out: list[dict] = []
    for m in pattern.finditer(text or ""):
        body = (m.group("body") or "").strip()
        if is_display_only_math(body):
            continue
        left = text[: m.start()].strip()
        right = text[m.end() :].strip()
        score = score_display_block(left, body, right)
        if min_score <= score < max_score:
            out.append(
                {
                    "start": m.start(),
                    "end": m.end(),
                    "original": m.group(0),
                    "body": body,
                    "left": left[-120:],
                    "right": right[:120],
                    "score": score,
                }
            )
    return out
