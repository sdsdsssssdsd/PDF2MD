"""正文残片清理（非公式结构）。从 md_postprocess 拆出。"""
from __future__ import annotations

import re

def repair_prose_artifacts(md: str) -> str:
    """正文里高频、与公式无关的 Docling/转义残片。"""
    if not md:
        return md
    # 千分位被拆进数学：29,$390 / 29$,370 → 29,390 / 29,370
    md = re.sub(r"(\d+),\$(\d{3})\b", r"\1,\2", md)
    md = re.sub(r"(\d+)\$,(\d{3})\b", r"\1,\2", md)
    # Markdown 误转义下划线：student\_assessments / view\_only
    md = re.sub(r"\\_", "_", md)
    # fi 连字被拆：de fi ne / ef fi cient / identi fi es
    md = re.sub(r"\b([A-Za-z]+)\s+fi\s+([A-Za-z]+)\b", r"\1fi\2", md)
    # 孤立页码行（图片后的 9 / 10）
    md = re.sub(r"(?m)\n\n(\d{1,2})\n\n", "\n\n", md)
    # 控制字符
    md = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", md)
    return md
