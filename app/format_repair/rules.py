"""本地确定性格式修复规则。"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.format_repair.integrity import integrity_ok
from app.format_repair.models import RepairConfig, RepairEdit
from app.format_repair.scanner import extract_protected_regions, restore_protected_regions
from app.utils.md_postprocess import normalize_display_math_multiline

_LATEX_INLINE = re.compile(r"\\\((?P<body>.*?)\\\)", re.DOTALL)
_LATEX_DISPLAY = re.compile(r"\\\[(?P<body>.*?)\\\]", re.DOTALL)
_DISPLAY_BLOCK = re.compile(r"\$\$\s*\n(?P<body>.*?)\n\s*\$\$", re.DOTALL)
_PLAIN_DISPLAY_BRACKET = re.compile(
    r"(?m)^[ \t]*\[[ \t]*\n(?P<body>.*?)\n[ \t]*\][ \t]*(?=\n|$)",
    re.DOTALL,
)
_PLAIN_SINGLELINE_DISPLAY = re.compile(
    r"(?m)^[ \t]*\[(?P<body>[^\]\n]+)\][ \t]*$",
)
_HR_LINE = re.compile(r"(?m)^---\s*$")
_COMPLEX_DISPLAY = re.compile(
    r"\\begin\{|\\end\{|\\tag\s*\{|\\label\s*\{|\\\\|"
    r"\\displaystyle|\\sum\b|\\int\b|\\boxed\b",
    re.I,
)
_DISPLAY_SIGNALS = (
    "如下",
    "如下所示",
    "结果如下",
    "公式如下",
    "表达式为",
    "计算结果为",
    "可写成",
    "as follows",
    "given by",
    "we obtain",
)
_LEFT_CONTINUE = (
    "当",
    "若",
    "如果",
    "其中",
    "即",
    "为",
    "是",
    "有",
    "满足",
    "得到",
    "可得",
    "令",
    "设",
    "记",
    "因为",
    "由于",
    "根据",
    "使得",
    "则有",
    "分别为",
    "定义为",
    "等于",
    "where",
    "when",
    "if",
    "for",
    "let",
    "with",
    "given",
    "assuming",
    "denote",
    "defined as",
    "equal to",
    "such that",
)
_RIGHT_CONTINUE = (
    "时",
    "则",
    "表示",
    "其中",
    "为",
    "是",
    "成立",
    "可得",
    "的情况下",
    "的值",
    "分别表示",
    "is",
    "are",
    "denotes",
    "represents",
    "where",
    "then",
    "holds",
)

_MATHY_BRACKET_BODY = re.compile(
    r"(\\[A-Za-z]+|[\^_=+\-*/<>]|\\frac|\\Gamma|\\text)",
)


@dataclass
class LocalRepairOutput:
    text: str
    edits: list[RepairEdit]
    rejected: list[RepairEdit]


def _normalize_newlines(text: str) -> str:
    return (text or "").replace("\r\n", "\n").replace("\r", "\n")


def _count_latex_commands(body: str) -> int:
    return len(re.findall(r"\\[A-Za-z]+", body or ""))


def _nesting_depth(body: str) -> int:
    depth = 0
    max_depth = 0
    for ch in body or "":
        if ch in "{[":
            depth += 1
            max_depth = max(max_depth, depth)
        elif ch in "}]":
            depth = max(0, depth - 1)
    return max_depth


def _ends_incomplete(left: str) -> bool:
    s = (left or "").strip()
    if not s:
        return False
    if s[-1:] in "。！？.!?；;":
        return False
    if s[-1:] == ":" and any(s.endswith(x) for x in _DISPLAY_SIGNALS):
        return False
    for word in _LEFT_CONTINUE:
        if s.endswith(word):
            return True
    return False


def _right_continues(right: str) -> bool:
    s = (right or "").strip()
    for word in _RIGHT_CONTINUE:
        if s.startswith(word):
            return True
    return bool(s[:1] in "，,。；;：:")


def _inline_score(left: str, body: str, right: str) -> int:
    score = 0
    if len(body) <= 48:
        score += 25
    if _count_latex_commands(body) <= 5:
        score += 15
    if _nesting_depth(body) <= 2:
        score += 15
    if _ends_incomplete(left):
        score += 25
    if _right_continues(right):
        score += 25
    if any(left.strip().endswith(x) for x in _DISPLAY_SIGNALS):
        score -= 40
    return score


def score_display_block(
    left: str,
    body: str,
    right: str,
) -> int:
    return _inline_score(left, body, right)


def is_display_only_math(body: str) -> bool:
    if not body or "\n" in body:
        return True
    if len(body) > 48 or _count_latex_commands(body) > 5:
        return True
    return bool(_COMPLEX_DISPLAY.search(body))


def _replace_latex_delimiters(text: str, edits: list[RepairEdit]) -> str:
    def inline(m: re.Match[str]) -> str:
        body = (m.group("body") or "").strip()
        after = f"${body}$"
        edits.append(
            RepairEdit("inline_delimiter", m.group(0), after, "latex_inline")
        )
        return after

    def display(m: re.Match[str]) -> str:
        body = (m.group("body") or "").strip()
        after = f"$$\n{body}\n$$"
        edits.append(
            RepairEdit("display_delimiter", m.group(0), after, "latex_display")
        )
        return after

    text = _LATEX_INLINE.sub(inline, text)
    text = _LATEX_DISPLAY.sub(display, text)
    return text


def _replace_plain_display_brackets(
    text: str,
    edits: list[RepairEdit],
) -> str:
    def repl(m: re.Match[str]) -> str:
        body = (m.group("body") or "").strip()
        if not body or "$" in body:
            return m.group(0)
        if not _MATHY_BRACKET_BODY.search(body):
            return m.group(0)
        if "\n[" in body or "\n]" in body:
            return m.group(0)
        after = f"$$\n{body}\n$$"
        edits.append(
            RepairEdit("display_delimiter", m.group(0), after, "plain_bracket_display")
        )
        return after

    text = _PLAIN_DISPLAY_BRACKET.sub(repl, text)

    def single(m: re.Match[str]) -> str:
        body = (m.group("body") or "").strip()
        if not body or "$" in body:
            return m.group(0)
        if not _MATHY_BRACKET_BODY.search(body):
            return m.group(0)
        after = f"$$\n{body}\n$$"
        edits.append(
            RepairEdit(
                "display_delimiter",
                m.group(0),
                after,
                "plain_singleline_display",
            )
        )
        return after

    return _PLAIN_SINGLELINE_DISPLAY.sub(single, text)


def _strip_horizontal_rules(text: str, edits: list[RepairEdit]) -> str:
    def repl(m: re.Match[str]) -> str:
        edits.append(
            RepairEdit("horizontal_rule", m.group(0), "\n", "remove_hr")
        )
        return "\n"

    return _HR_LINE.sub(repl, text)


def _compact_display(
    text: str,
    config: RepairConfig,
    edits: list[RepairEdit],
    rejected: list[RepairEdit],
) -> str:
    if not config.compact_display_math:
        return text

    def repl(m: re.Match[str]) -> str:
        body = (m.group("body") or "").strip()
        if not body or "\n" in body:
            return m.group(0)
        if len(body) > 48 or _count_latex_commands(body) > 5:
            return m.group(0)
        if _COMPLEX_DISPLAY.search(body):
            return m.group(0)
        left = text[: m.start()].strip()
        right = text[m.end() :].strip()
        score = _inline_score(left, body, right)
        if score < config.auto_inline_threshold:
            return m.group(0)
        after = f"${body}$"
        if not integrity_ok(m.group(0), after):
            rejected.append(
                RepairEdit("display_to_inline", m.group(0), after, "integrity_reject")
            )
            return m.group(0)
        edits.append(
            RepairEdit(
                "display_to_inline",
                m.group(0),
                after,
                f"score={score}",
                confidence=min(1.0, score / 100),
            )
        )
        return after

    return _DISPLAY_BLOCK.sub(repl, text)


def repair_local(
    text: str,
    config: RepairConfig | None = None,
) -> LocalRepairOutput:
    cfg = config or RepairConfig()
    edits: list[RepairEdit] = []
    rejected: list[RepairEdit] = []
    text = _normalize_newlines(text)
    masked, regions = extract_protected_regions(text)
    masked = _strip_horizontal_rules(masked, edits)
    if cfg.normalize_math:
        masked = _replace_plain_display_brackets(masked, edits)
        masked = _replace_latex_delimiters(masked, edits)
        masked = normalize_display_math_multiline(masked)
        masked = _compact_display(masked, cfg, edits, rejected)
    masked = re.sub(r"\n{3,}", "\n\n", masked)
    result = restore_protected_regions(masked, regions)
    result = re.sub(r"\n{3,}", "\n\n", result).strip() + "\n"
    return LocalRepairOutput(result, edits, rejected)
