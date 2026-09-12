"""LaTeX 结构异常检测。"""
from __future__ import annotations

import re

from app.correction.models import CorrectionIssue

_GAMMA_OCR = re.compile(r"(?<![\\A-Za-z])Gamma!(?=\\left\b)")
_O_SPACING = re.compile(r"(?<![A-Za-z\\])O!(?=\\left\b)")
_BROKEN_ARRAY_BREAK = re.compile(
    r"(?<![\\])\\" + "\\[(?P<sp>1mm|\\d+(?:\\.\\d+)?(?:mm|pt|em|ex)?)\\]"
)
_BROKEN_ARRAY_BREAK2 = re.compile(
    r"\}\\" + "\\[(?P<sp>1mm|\\d+(?:\\.\\d+)?(?:mm|pt|em|ex)?)\\]"
)
_PLAIN_DISPLAY_BRACKET = re.compile(
    r"(?m)^[ \t]*\[[ \t]*\n(?P<body>.*?)\n[ \t]*\][ \t]*(?=\n|$)",
    re.DOTALL,
)
_LATEX_INLINE = re.compile(r"\\\((?P<body>.*?)\\\)", re.DOTALL)
_LATEX_DISPLAY = re.compile(r"\\\[(?P<body>.*?)\\\]", re.DOTALL)
_MATHY = re.compile(r"(\\[A-Za-z]+|[\^_=+\-*/<>]|\\frac|\\Gamma|\\text|\\boxed)")


def detect_latex_issues(text: str, *, start_id: int = 1) -> list[CorrectionIssue]:
    issues: list[CorrectionIssue] = []
    idx = start_id

    def add(kind: str, m: re.Match[str], after: str, severity: str = "high") -> None:
        nonlocal idx
        issues.append(
            CorrectionIssue(
                issue_id=f"LATEX-{idx:04d}",
                kind=kind,
                start=m.start(),
                end=m.end(),
                before=m.group(0),
                after=after,
                severity=severity,
                left_context=text[max(0, m.start() - 200) : m.start()],
                right_context=text[m.end() : m.end() + 200],
                environment="display_math" if kind.endswith("display") else "prose",
            )
        )
        idx += 1

    for m in _GAMMA_OCR.finditer(text or ""):
        add("possible_missing_latex_backslash", m, r"\Gamma\!\left")

    for m in _O_SPACING.finditer(text or ""):
        add("possible_lost_spacing_command", m, r"O\!\left")

    for m in _BROKEN_ARRAY_BREAK.finditer(text or ""):
        sp = m.group("sp")
        add("array_row_break", m, f"\\\\[{sp}]", severity="medium")

    for m in _BROKEN_ARRAY_BREAK2.finditer(text or ""):
        sp = m.group("sp")
        add("array_row_break", m, "}" + "\\\\[" + sp + "]", severity="medium")

    for m in _PLAIN_DISPLAY_BRACKET.finditer(text or ""):
        body = (m.group("body") or "").strip()
        if body and _MATHY.search(body) and "$" not in body:
            add(
                "plain_bracket_display",
                m,
                f"$$\n{body}\n$$",
                severity="medium",
            )

    for m in _LATEX_INLINE.finditer(text or ""):
        body = (m.group("body") or "").strip()
        add("latex_inline", m, f"${body}$", severity="low")

    for m in _LATEX_DISPLAY.finditer(text or ""):
        body = (m.group("body") or "").strip()
        add("latex_display", m, f"$$\n{body}\n$$", severity="low")

    return issues
