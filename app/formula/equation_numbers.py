"""从损坏 LaTeX / 上下文提取印刷公式编号。"""
from __future__ import annotations

import re
from typing import Any


def display_equation_number_from_latex(latex: str) -> str:
    """display 尾标 ``(n)``（排除函数参数 p(0) 等）。"""
    if not (latex or "").strip():
        return ""
    for m in re.finditer(
        r"(?<![\w\\])\(\s*((?:\d\s*)+)\)\s*(?:&|\\\\|$)",
        latex,
    ):
        n = re.sub(r"\s+", "", m.group(1))
        if n:
            return n
    return ""


def bind_equation_number_from_latex(cand: Any) -> str:
    """候选无绑定编号时，从 raw/text 尾标回填。"""
    bound = (getattr(cand, "equation_number", None) or "").strip()
    if bound:
        return bound
    blob = f"{getattr(cand, 'raw_text', '') or ''}\n{getattr(cand, 'text', '') or ''}"
    n = display_equation_number_from_latex(blob)
    if n:
        cand.equation_number = n
    return n
