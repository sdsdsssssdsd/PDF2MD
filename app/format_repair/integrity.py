"""原文完整性门。"""
from __future__ import annotations

import re

_DELIMITER_ESCAPE_RE = re.compile(r"\\(?:\(|\)|\[|\])")
_MATHY_BODY = re.compile(
    r"(\\[A-Za-z]+|[\^_=+\-*/<>]|\\frac|\\Gamma|\\text|\\boxed)",
)
_PLAIN_MULTILINE_BRACKET = re.compile(
    r"(?m)^[ \t]*\[[ \t]*\n(?P<body>.*?)\n[ \t]*\][ \t]*(?:\n|$)",
    re.DOTALL,
)
_PLAIN_SINGLELINE_BRACKET = re.compile(
    r"(?m)^[ \t]*\[(?P<body>[^\]\n]+)\][ \t]*$",
)
_LATEX_DISPLAY = re.compile(r"\\\[(?P<body>.*?)\\\]", re.DOTALL)
_LATEX_INLINE = re.compile(r"\\\((?P<body>.*?)\\\)", re.DOTALL)
_DISPLAY_MATH = re.compile(r"\$\$\s*\n(?P<body>.*?)\n\s*\$\$", re.DOTALL)
_INLINE_MATH = re.compile(r"(?<!\$)\$(?!\$)(?P<body>[^\$\n]+?)\$(?!\$)")
_SINGLE_LINE_DISPLAY = re.compile(r"\$\$(?P<body>[^\n$]+?)\$\$")
_HR_LINE = re.compile(r"(?m)^---\s*$")


def _strip_plain_bracket_line(m: re.Match[str]) -> str:
    body = m.group("body") or ""
    if _MATHY_BODY.search(body):
        return body
    return m.group(0)


def content_projection(text: str) -> str:
    """去掉数学/格式围栏，只保留语义字符序列。"""
    t = text or ""

    t = _PLAIN_MULTILINE_BRACKET.sub(lambda m: m.group("body"), t)
    t = _PLAIN_SINGLELINE_BRACKET.sub(_strip_plain_bracket_line, t)
    t = _LATEX_DISPLAY.sub(lambda m: m.group("body"), t)
    t = _LATEX_INLINE.sub(lambda m: m.group("body"), t)
    t = _DISPLAY_MATH.sub(lambda m: m.group("body"), t)
    t = _SINGLE_LINE_DISPLAY.sub(lambda m: m.group("body"), t)
    t = _INLINE_MATH.sub(lambda m: m.group("body"), t)
    t = _HR_LINE.sub("", t)
    t = _DELIMITER_ESCAPE_RE.sub("", t)
    return re.sub(r"\s+", "", t)


def integrity_ok(before: str, after: str) -> bool:
    return content_projection(before) == content_projection(after)


def projection_diff(before: str, after: str) -> str:
    a = content_projection(before)
    b = content_projection(after)
    if a == b:
        return ""
    return f"before={len(a)} after={len(b)}"
