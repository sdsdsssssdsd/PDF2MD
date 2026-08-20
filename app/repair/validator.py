"""修复后校验（轻量、无外部依赖）。"""
from __future__ import annotations

import re


def validate_markdown(md: str) -> list[str]:
    """返回警告列表；空列表表示通过。"""
    warnings: list[str] = []
    if md.count("$") % 2 != 0:
        warnings.append("奇数个 $ 分隔符")
    if md.count("$$") % 2 != 0:
        warnings.append("$$ 数量不成对")

    # 粗检 begin/end
    begins = re.findall(r"\\begin\{([a-zA-Z*]+)\}", md)
    ends = re.findall(r"\\end\{([a-zA-Z*]+)\}", md)
    if sorted(begins) != sorted(ends):
        warnings.append("\\begin/\\end 环境可能不平衡")

    if re.search(r"\b\d+\s+\.\s+\d+\b", md):
        warnings.append("仍存在疑似拆开的小数")

    return warnings
