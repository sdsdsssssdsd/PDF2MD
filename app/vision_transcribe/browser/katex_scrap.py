"""检测 DOM inner_text 抽取产生的 KaTeX 竖排碎片（非 LaTeX 围栏）。"""
from __future__ import annotations

import re

# Mathematical Alphanumeric Symbols + 常见希腊字母
_MATH_CHAR = re.compile(
    r"[\u03B1-\u03C9\u03F5\u03D1\u03D6\u03F1\u03C2\u03D5"
    r"\U0001D400-\U0001D7FF]"
)
_SHORT_MATH_LINE = re.compile(
    r"^[\s\u200b\t]*(?:"
    r"[\u03B1-\u03C9\u03F5\u03D1\u03D6\u03F1\u03C2\u03D5\U0001D400-\U0001D7FF]"
    r"|[\(\)\[\]\+\-\=⋅∑∫×·]"
    r"|\d{1,2}"
    r"|[A-Za-z]{1,8}"
    r")[\s\u200b\t]*$"
)


def _line_is_katex_scrap(line: str) -> bool:
    s = (line or "").strip().replace("\u200b", "").replace("\t", "")
    if not s:
        return False
    if len(s) > 12:
        return False
    if _MATH_CHAR.search(s):
        return True
    if _SHORT_MATH_LINE.match(line or ""):
        return True
    return False


def has_dom_katex_scrap(text: str, *, min_run: int = 10) -> bool:
    """True = 像 Playwright inner_text 把公式拆成逐字/逐符号短行。"""
    if not text:
        return False
    # 已有成块 LaTeX 围栏时，通常不是 DOM 碎片模式
    if text.count("$$") >= 2:
        return False

    lines = text.splitlines()
    run = 0
    for line in lines:
        if _line_is_katex_scrap(line):
            run += 1
            if run >= min_run:
                return True
        elif not line.strip():
            if run >= min_run:
                return True
            run = 0
        else:
            if run >= min_run:
                return True
            run = 0
    return run >= min_run


def katex_scrap_score(text: str) -> float:
    """竖排碎片行占比（0~1），供抽取择优。"""
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    if not lines:
        return 0.0
    scrap = sum(1 for ln in lines if _line_is_katex_scrap(ln))
    return scrap / len(lines)
