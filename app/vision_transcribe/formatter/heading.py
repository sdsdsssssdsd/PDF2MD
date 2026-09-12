"""低风险标题格式修复。"""
from __future__ import annotations

from app.vision_transcribe.vision_structure_repair import (
    markdown_lacks_structure,
    repair_block_breaks,
    repair_section_headings,
    repair_section_line_breaks,
)


def repair_heading(md: str) -> str:
    text = md or ""
    if not markdown_lacks_structure(text):
        return text
    text = repair_block_breaks(text)
    text = repair_section_line_breaks(text)
    return repair_section_headings(text)
