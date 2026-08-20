"""质量分析：只检测、不修改（Phase 0 规则集）。"""
from __future__ import annotations

import re

from app.repair.models import IssueType, RepairIssue

_DECIMAL_SPLIT = re.compile(r"(?<![\w.])\d+\s+\.\s+\d+(?![\w.])")
_SUSPICIOUS_SUB = re.compile(
    r"\\(?:pm|le|ge|in|times|cdot)_\{[^}]+\}"
)
_PROSE_WORDS = re.compile(
    r"\b(?:we|the|and|for|with|from|that|this|is|are|was|were|"
    r"associated|corresponds|including|construct|dataset)\b",
    re.I,
)
_HAT_CORRUPT = re.compile(r"ˆ\s*[A-Za-z]")  # 仅 Unicode hat，避免误伤 LaTeX ^
_DETACHED = re.compile(
    r"(?<![A-Za-z\\$])([A-Za-z])\s*\(\s*[A-Za-z0-9]+\s*\)\s*[A-Za-z0-9]\b"
)
_SPLIT_WORD = re.compile(r"\b(?:Pr\s+e\s+c|R\s+e\s+c|F\s+1)\b")
_DISPLAY_CONTAM = re.compile(
    r"\$\$[\s\S]{0,200}?\\text\{[^}]{20,}\}"
)
_DISPLAY_BLOCK = re.compile(r"\$\$[\s\S]+?\$\$")
_INLINE_BLOCK = re.compile(r"(?<!\$)\$(?!\$)([^$]+)(?<!\$)\$(?!\$)")


def _iter_math_spans(md: str) -> list[tuple[int, int, str, bool]]:
    """返回 (start, end, content, is_display)。"""
    spans: list[tuple[int, int, str, bool]] = []
    covered: list[tuple[int, int]] = []
    for m in _DISPLAY_BLOCK.finditer(md):
        spans.append((m.start(), m.end(), m.group(0)[2:-2], True))
        covered.append((m.start(), m.end()))

    def in_display(pos: int) -> bool:
        return any(a <= pos < b for a, b in covered)

    for m in _INLINE_BLOCK.finditer(md):
        if in_display(m.start()):
            continue
        spans.append((m.start(), m.end(), m.group(1), False))
    return spans


def analyze_markdown(md: str) -> list[RepairIssue]:
    issues: list[RepairIssue] = []

    without_disp = _DISPLAY_BLOCK.sub("", md)
    n_dollar = without_disp.count("$")
    if n_dollar % 2 != 0:
        issues.append(
            RepairIssue(
                type=IssueType.MALFORMED_DELIMITER,
                severity=0.5,
                message=f"奇数个行内 $（{n_dollar}）",
            )
        )

    if md.count("$$") % 2 != 0:
        issues.append(
            RepairIssue(
                type=IssueType.MALFORMED_DELIMITER,
                severity=0.55,
                message=f"$$ 数量异常（{md.count('$$')}）",
            )
        )

    for m in _DECIMAL_SPLIT.finditer(md):
        issues.append(
            RepairIssue(
                type=IssueType.DECIMAL_SPLIT,
                severity=0.25,
                message="疑似小数被拆开",
                start=m.start(),
                end=m.end(),
                original=m.group(0),
            )
        )

    for m in _SUSPICIOUS_SUB.finditer(md):
        issues.append(
            RepairIssue(
                type=IssueType.SUSPICIOUS_SUBSCRIPT,
                severity=0.4,
                message="运算符上疑似错误下标",
                start=m.start(),
                end=m.end(),
                original=m.group(0),
            )
        )

    for start, end, content, is_display in _iter_math_spans(md):
        stripped = re.sub(r"\\text\s*\{[^}]*\}", "", content)
        if _PROSE_WORDS.search(stripped):
            issues.append(
                RepairIssue(
                    type=IssueType.PROSE_IN_MATH,
                    severity=0.55 if not is_display else 0.7,
                    message="公式内疑似混入英文散文",
                    start=start,
                    end=end,
                    original=content[:120],
                )
            )

    for m in _HAT_CORRUPT.finditer(md):
        issues.append(
            RepairIssue(
                type=IssueType.HAT_CORRUPTION,
                severity=0.35,
                message="疑似 hat 符号损坏",
                start=m.start(),
                end=m.end(),
                original=m.group(0),
            )
        )

    for m in _DETACHED.finditer(md):
        issues.append(
            RepairIssue(
                type=IssueType.DETACHED_SCRIPT,
                severity=0.35,
                message="疑似上下标与变量拆散",
                start=m.start(),
                end=m.end(),
                original=m.group(0),
            )
        )

    for m in _SPLIT_WORD.finditer(md):
        issues.append(
            RepairIssue(
                type=IssueType.SPLIT_MATH_WORD,
                severity=0.3,
                message="疑似指标名被拆字",
                start=m.start(),
                end=m.end(),
                original=m.group(0),
            )
        )

    for m in _DISPLAY_CONTAM.finditer(md):
        issues.append(
            RepairIssue(
                type=IssueType.DISPLAY_CONTAMINATION,
                severity=0.7,
                message="行间公式疑似被长文本污染",
                start=m.start(),
                end=m.end(),
                original=m.group(0)[:160],
            )
        )

    n_ph = md.count("<!-- formula-not-decoded -->")
    if n_ph:
        issues.append(
            RepairIssue(
                type=IssueType.FORMULA_NOT_DECODED,
                severity=min(1.0, 0.2 + 0.05 * n_ph),
                message=f"未解码公式占位 {n_ph} 处",
            )
        )

    unicode_hits = sum(1 for ch in md if ch in "δαβγθλμπσφω∈≤≥≠±∑∏∫∞")
    if unicode_hits:
        issues.append(
            RepairIssue(
                type=IssueType.UNICODE_MATH,
                severity=min(0.45, 0.05 + unicode_hits * 0.01),
                message=f"正文含约 {unicode_hits} 处 Unicode 数学符号",
            )
        )

    return issues


def risk_score(issues: list[RepairIssue]) -> float:
    """按严重度总和饱和映射到 (0,1)；不随 issue 条数人为放大。"""
    if not issues:
        return 0.0
    total = sum(i.severity for i in issues)
    return 1.0 - 1.0 / (1.0 + total / 12.0)
