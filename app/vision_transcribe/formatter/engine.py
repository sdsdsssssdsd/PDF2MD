"""Format Engine：先修复结构，再进入二次验证。"""
from __future__ import annotations

from app.vision_transcribe.formatter.heading import repair_heading
from app.vision_transcribe.formatter.markdown import repair_markdown
from app.vision_transcribe.formatter.page import repair_page_marker
from app.vision_transcribe.formatter.table import repair_table


def format_document(md: str) -> str:
    text = repair_page_marker(md or "")
    text = repair_heading(text)
    text = repair_table(text)
    text = repair_markdown(text)
    return repair_page_marker(text)
