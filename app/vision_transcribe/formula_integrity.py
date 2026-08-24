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


def formula_integrity_errors(md: str) -> list[str]:
    """返回非空则不应接受该批次（宁可重跑，不可丢公式）。"""
    t = (md or "").replace("\r\n", "\n")
    errors: list[str] = []

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

    nums = [int(x) for x in _NUMBERED_EQ.findall(t)]
    if nums:
        hi = max(nums)
        missing = [n for n in range(1, hi) if n not in nums]
        if missing:
            errors.append(
                f"编号方程式不连续：已有 {sorted(set(nums))}，缺少 {missing}"
            )

    return errors


def formula_integrity_penalty(md: str) -> int:
    """用于择优：每个完整性错误扣大量分。"""
    return len(formula_integrity_errors(md)) * 2_000_000


def count_numbered_equations(md: str) -> int:
    return len(_NUMBERED_EQ.findall(md or ""))
