"""确定性 SafeCleaner：只做无语义风险格式清理。"""
from __future__ import annotations

import re
from pathlib import Path

from app.vision_transcribe.vision_structure_repair import repair_vision_markdown_structure

from app.utils.md_postprocess import (
    ensure_figure_table_separation,
    normalize_display_math_multiline,
)
from app.vision_transcribe.manifest import vision_dir
from app.vision_transcribe.models import BATCH_BEGIN_RE, BATCH_END_RE, PAGE_MARKER_RE

_HR_RE = re.compile(r"(?m)^(?:-{3,}|\*{3,}|_{3,})\s*$")
_JUNK_IMAGE_LINE = re.compile(r"(?m)^https://image\s*$")


def clean_vision_markdown(md: str, *, strip_page_markers: bool = True) -> str:
    text = (md or "").replace("\r\n", "\n").replace("\r", "\n")
    text = BATCH_BEGIN_RE.sub("", text)
    text = BATCH_END_RE.sub("", text)
    # 须在去掉 PAGE 标记前修复（FIGURE 占位 / example.com 依赖页码）
    text = repair_vision_markdown_structure(text)
    if strip_page_markers:
        text = PAGE_MARKER_RE.sub("", text)
    text = _HR_RE.sub("", text)
    text = _JUNK_IMAGE_LINE.sub("", text)
    # 压缩过多空行
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = normalize_display_math_multiline(text)
    text = ensure_figure_table_separation(text)
    return text.strip() + "\n"


def clean_and_write(output_dir: Path, raw_md: str | None = None) -> Path:
    vision = vision_dir(output_dir)
    if raw_md is None:
        raw_path = vision / "document.raw.md"
        raw_md = raw_path.read_text(encoding="utf-8")
    cleaned = clean_vision_markdown(raw_md, strip_page_markers=True)
    out = vision / "document.cleaned.md"
    out.write_text(cleaned, encoding="utf-8")
    return out
