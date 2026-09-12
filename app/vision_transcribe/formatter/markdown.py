"""Markdown 结构与空白规范化。"""
from __future__ import annotations

import re

from app.vision_transcribe.vision_structure_repair import (
    markdown_lacks_structure,
    repair_vision_markdown_structure,
)


def repair_markdown(md: str) -> str:
    text = (md or "").replace("\r\n", "\n").replace("\r", "\n")
    if markdown_lacks_structure(text):
        text = repair_vision_markdown_structure(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"
