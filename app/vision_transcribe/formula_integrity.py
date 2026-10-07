# -*- coding: utf-8 -*-
"""高保真转录：公式/编号方程式完整性（禁止静默丢失）。"""
from __future__ import annotations

import re

# 「模型为：」后紧跟 where，中间无公式
_ORPHAN_WHERE = re.compile(
    r"(?:was|following|equation|model|specification|formulation)\s*:\s*"
    r"(?:\n\s*){1,4}where\b",
    re.I,
)

# 行末编号方程式 (1) / \quad (2)
_NUMBERED_EQ = re.compile(
    r"(?:\\quad\s*)?\((\d{1,2})\)\s*$",
    re.M,
)

# 行间公式常用 \\tag{1}（Typora/MathJax），与行末 (n) 等价
_TAG_EQ = re.compile(r"\\tag\{(\d{1,2})\}")

# 行间公式块 $$ ... $$（跨行）
_DISPLAY_BLOCK = re.compile(r"\$\$[\s\S]*?\$\$")

# 公式上下文：行内有 $ / LaTeX 命令 / 上下标，才算「编号贴在公式上」
_MATHY = re.compile(r"\$|\\[A-Za-z]+|[_^]")

# 行间 / 裸 LaTeX 公式痕迹
_MATH_BODY = re.compile(
    r"(?:\$\$[\s\S]+?\$\$|"
    r"\\logit\b|"
    r"\\beta[_\{]|"
    r"\\sum[_\{]|"
    r"\\operatorname\b|"
    r"\\frac\b|"
    r"\\begin\{aligned\})",
    re.I,
)


def _display_line_indexes(text: str) -> set[int]:
    """$$ ... $$ 覆盖到的行号（含首尾行）。"""
    covered: set[int] = set()
    for m in _DISPLAY_BLOCK.finditer(text):
        first = text.count("\n", 0, m.start())
        last = text.count("\n", 0, m.end())
        covered.update(range(first, last + 1))
    return covered


def numbered_equation_numbers(md: str) -> list[int]:
    """行末 (n) 形式的编号方程式。

    必须处于公式上下文（$$ 块内，或该行有 $ / LaTeX / 上下标），
    否则「解答. (1)」「(3)」这类**小问编号**会被误判成方程式编号，
    导致整批校验永久失败（历史故障：第十六届初赛 1–6 页）。
    """
    text = (md or "").replace("\r\n", "\n")
    covered = _display_line_indexes(text)
    nums: list[int] = []
    for idx, line in enumerate(text.splitlines()):
        m = _NUMBERED_EQ.search(line)
        if not m:
            continue
        if idx in covered or _MATHY.search(line[: m.start()]):
            nums.append(int(m.group(1)))
    return nums


def formula_integrity_errors(
    md: str,
    *,
    start_page: int | None = None,
    require_from_one: bool | None = None,
) -> list[str]:
    """返回非空则不应接受该批次（宁可重跑，不可丢公式）。

    编号连续性按**本批**检查：第 7–12 页从 (8) 起是合法的。
    只有首页批次（start_page<=1）才要求从 (1) 起算；批内空洞仍报错。
    """
    t = (md or "").replace("\r\n", "\n")
    errors: list[str] = []
    if require_from_one is None:
        require_from_one = start_page is not None and int(start_page) <= 1

    for m in _ORPHAN_WHERE.finditer(t):
        before = t[max(0, m.start() - 120) : m.start()]
        between = t[m.start() : m.end()]
        # 允许 where 前已有公式
        if not _MATH_BODY.search(before[-400:]) and not _MATH_BODY.search(between):
            errors.append(
                "检测到公式缺失：「模型/方程式」说明后直接进入 where 子句，"
                "中间应有完整公式（如编号式 (1)）"
            )
            break

    nums = numbered_equation_numbers(t)
    nums.extend(int(x) for x in _TAG_EQ.findall(t))
    if nums:
        uniq = sorted(set(nums))
        lo = 1 if require_from_one else min(uniq)
        hi = max(uniq)
        missing = [n for n in range(lo, hi) if n not in uniq]
        if missing:
            errors.append(
                f"编号方程式不连续：已有 {uniq}，缺少 {missing}"
            )

    return errors


def formula_integrity_penalty(
    md: str,
    *,
    start_page: int | None = None,
) -> int:
    """用于择优：每个完整性错误扣大量分。"""
    return len(formula_integrity_errors(md, start_page=start_page)) * 2_000_000


def count_numbered_equations(md: str) -> int:
    return len(numbered_equation_numbers(md))
