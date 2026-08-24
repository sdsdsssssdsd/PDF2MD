# -*- coding: utf-8 -*-
"""Typora/MathJax 兼容：指标 OCR 错字与假 LaTeX 命令修复（不发明公式结构）。"""
from __future__ import annotations

import re
from dataclasses import dataclass

# 标准 AMS/MathJax 常见命令 + 本项目常用；不在表内且非希腊字母 → 假命令
_KNOWN_MATH_COMMANDS = frozenset(
    {
        "frac",
        "sum",
        "prod",
        "int",
        "mathrm",
        "mathbf",
        "mathit",
        "mathcal",
        "mathbb",
        "operatorname",
        "text",
        "hat",
        "bar",
        "tilde",
        "vec",
        "dot",
        "ddot",
        "cdot",
        "times",
        "pm",
        "mp",
        "leq",
        "geq",
        "neq",
        "approx",
        "equiv",
        "infty",
        "partial",
        "nabla",
        "left",
        "right",
        "begin",
        "end",
        "tag",
        "label",
        "ref",
        "quad",
        "qquad",
        "hspace",
        "vspace",
        "displaystyle",
        "limits",
        "arg",
        "max",
        "min",
        "log",
        "ln",
        "exp",
        "sin",
        "cos",
        "tan",
        "alpha",
        "beta",
        "gamma",
        "delta",
        "epsilon",
        "varepsilon",
        "theta",
        "lambda",
        "mu",
        "sigma",
        "omega",
        "Gamma",
        "Delta",
        "Theta",
        "Lambda",
        "Sigma",
        "Omega",
        "colon",
        "to",
        "rightarrow",
        "Rightarrow",
        "Leftrightarrow",
        "forall",
        "exists",
        "in",
        "notin",
        "subset",
        "cup",
        "cap",
        "setminus",
        "emptyset",
        "cdots",
        "ldots",
        "vdots",
        "ddots",
        "stackrel",
        "overset",
        "underset",
        "binom",
        "choose",
        "atop",
        "over",
        "brace",
        "brack",
    }
)

_FAKE_CMD_FIXES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\\Precisio(?=_|\{|$)", re.I), r"\\mathrm{Precision}"),
    (re.compile(r"\\Precisi(?=_|\{|$)", re.I), r"\\mathrm{Precision}"),
    (re.compile(r"\\Recall(?=_|\{|$)"), r"\\mathrm{Recall}"),
    (re.compile(r"\\cdotMetric(?=\.|_|\\b|$)"), r"\\cdot \\mathrm{Metric}"),
    (re.compile(r"\\cdotMeric(?=\.|_|\\b|$)"), r"\\cdot \\mathrm{Metric}"),
)

_PLAIN_TYPO_FIXES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bAcuracy\b"), "Accuracy"),
    (re.compile(r"\bPrecisi(?=_|\b)"), "Precision"),
    (re.compile(r"\bPrecisio(?=_|\b)"), "Precision"),
    (re.compile(r"\bMeric(?=_|\b)"), "Metric"),
    (re.compile(r"\bMetricweighets\b"), r"\\mathrm{Metric}_{\\mathrm{weighted}}"),
)

_DISPLAY = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)


@dataclass(frozen=True)
class TyporaMathIssue:
    code: str
    message: str
    snippet: str = ""


def find_undefined_math_commands(body: str) -> list[str]:
    """返回疑似未定义 \\Command（Typora 爆红源）。"""
    unknown: list[str] = []
    seen: set[str] = set()
    for m in re.finditer(r"\\([A-Za-z]+)", body or ""):
        cmd = m.group(1)
        if cmd in _KNOWN_MATH_COMMANDS:
            continue
        if cmd in seen:
            continue
        seen.add(cmd)
        unknown.append(cmd)
    return unknown


def repair_typora_math_body(body: str) -> str:
    """修单行公式体（不含外围 $$）。"""
    s = (body or "").strip()
    if not s:
        return s

    for pat, repl in _FAKE_CMD_FIXES:
        s = pat.sub(repl, s)
    for pat, repl in _PLAIN_TYPO_FIXES:
        s = pat.sub(repl, s)

    # Docling 拆字下标：M _ { i j } → M_{ij}
    def _compact_subscript(m: re.Match[str]) -> str:
        inner = re.sub(r"\s+", "", m.group(2))
        return f"{m.group(1)}_{{{inner}}}"

    s = re.sub(
        r"([A-Za-z])\s+_\s*\{\s*([^}]+)\s*\}",
        _compact_subscript,
        s,
    )
    # A U C _ { c } → AUC_{c}
    def _compact_spaced_subscript(m: re.Match[str]) -> str:
        base = re.sub(r"\s+", "", m.group(1))
        inner = re.sub(r"\s+", "", m.group(2))
        return f"{base}_{{{inner}}}"

    s = re.sub(
        r"\b((?:[A-Za-z]\s+){1,6}[A-Za-z])\s+_\s*\{\s*([^}]+)\s*\}",
        _compact_spaced_subscript,
        s,
    )
    # 混淆矩阵：iand\hat → i \text{ and } \hat
    s = re.sub(
        r"=\s*i\s*and\s*\\hat",
        r"= i \\text{ and } \\hat",
        s,
        flags=re.I,
    )
    s = re.sub(r"iand\\hat", r"i \\text{ and } \\hat", s, flags=re.I)
    s = re.sub(r"\\hat\s*\{\s*y\s*\}\s*_\s*\{\s*k\s*\}", r"\\hat{y}_{k}", s)

    # 指标名统一用 \mathrm{}（仅常见 TP/FP 分式块）
    if re.search(r"TP_\{c\}|TP_c|FP_\{c\}|FN_\{c\}", s):
        s = re.sub(
            r"(?<![\\a-zA-Z])Accuracy(?=_|\b|=)",
            r"\\mathrm{Accuracy}",
            s,
        )
        s = re.sub(
            r"(?<![\\a-zA-Z])Precision(?=_|\b|=)",
            r"\\mathrm{Precision}",
            s,
        )
        s = re.sub(
            r"(?<![\\a-zA-Z])Recall(?=_|\b|=)",
            r"\\mathrm{Recall}",
            s,
        )
        s = re.sub(r"(?<![\\a-zA-Z])F1(?=_|\b|=)", r"\\mathrm{F1}", s)
        s = re.sub(
            r"(?<![\\a-zA-Z])Metric(?=_|\b|=)",
            r"\\mathrm{Metric}",
            s,
        )

    return s.strip()


def repair_typora_math_in_markdown(md: str) -> str:
    if not md or "$$" not in md:
        return md

    def _repl(m: re.Match[str]) -> str:
        body = repair_typora_math_body(m.group(1) or "")
        return f"$$\n{body}\n$$"

    return _DISPLAY.sub(_repl, md)


def lint_typora_math(md: str) -> list[TyporaMathIssue]:
    """扫描最终 MD；用于 repair.json / 批跑汇总。"""
    issues: list[TyporaMathIssue] = []
    if not md:
        return issues

    for m in _DISPLAY.finditer(md):
        body = (m.group(1) or "").strip()
        if not body:
            continue
        for cmd in find_undefined_math_commands(body):
            issues.append(
                TyporaMathIssue(
                    code="T-undef-cmd",
                    message=f"未定义 LaTeX 命令 \\{cmd}",
                    snippet=body[:120],
                )
            )
        for typo_pat, _ in _PLAIN_TYPO_FIXES:
            if typo_pat.search(body):
                issues.append(
                    TyporaMathIssue(
                        code="T-metric-typo",
                        message="疑似指标名 OCR 错字",
                        snippet=body[:120],
                    )
                )
                break
    return issues
