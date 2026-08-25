"""按 PAGE 标记拆分批次 Markdown（P1）。"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.vision_transcribe.models import PAGE_END_RE, PAGE_MARKER_RE


@dataclass
class PageSlice:
    page: int
    body: str
    has_begin: bool = True
    has_end: bool = False
    chars: int = 0
    line_count: int = 0
    math_blocks: int = 0
    table_rows: int = 0
    figure_markers: int = 0

    def __post_init__(self) -> None:
        b = (self.body or "").strip()
        self.chars = len(b)
        self.line_count = len(b.splitlines()) if b else 0
        self.math_blocks = len(re.findall(r"\$\$", b)) // 2
        self.table_rows = len(re.findall(r"(?m)^\|[^\n]+\|", b))
        self.figure_markers = len(re.findall(r"PDF2MD:FIGURE", b))


def split_pages(md: str) -> dict[int, PageSlice]:
    """按 PAGE 开头标记拆分；识别 PAGE_END。"""
    text = md or ""
    found_end: set[int] = set()
    for m in PAGE_END_RE.finditer(text):
        found_end.add(int(m.group(1)))

    parts = PAGE_MARKER_RE.split(text)
    out: dict[int, PageSlice] = {}
    if len(parts) < 3:
        return out

    for i in range(1, len(parts), 2):
        page_no = int(parts[i])
        body = parts[i + 1] if i + 1 < len(parts) else ""
        body = PAGE_END_RE.sub("", body)
        body = PAGE_MARKER_RE.sub("", body)
        out[page_no] = PageSlice(
            page=page_no,
            body=body.strip(),
            has_begin=True,
            has_end=page_no in found_end,
        )
    return out
