"""批次 Markdown 逐页替换（Level-2/3 恢复）。"""
from __future__ import annotations

import re

from app.vision_transcribe.capture.page_split import PageSlice, split_pages
from app.vision_transcribe.models import (
    BATCH_END_RE,
    PAGE_END_RE,
    PAGE_MARKER_RE,
    page_end_marker,
    page_marker,
)


def _strip_page_wrappers(text: str) -> str:
    t = (text or "").strip()
    t = PAGE_MARKER_RE.sub("", t)
    t = PAGE_END_RE.sub("", t)
    t = BATCH_END_RE.sub("", t)
    return t.strip()


def page_block_markdown(page_no: int, body: str, *, with_end: bool = True) -> str:
    b = _strip_page_wrappers(body)
    lines = [page_marker(page_no), b]
    if with_end:
        lines.append(page_end_marker(page_no))
    return "\n\n".join(lines) + "\n"


def rebuild_batch_markdown(pages: dict[int, PageSlice]) -> str:
    parts: list[str] = []
    for p in sorted(pages):
        sl = pages[p]
        parts.append(page_block_markdown(p, sl.body, with_end=sl.has_end or True))
    return "\n".join(parts).rstrip() + "\n"


def replace_page_in_batch(md: str, page_no: int, replacement: str) -> str:
    """用单页重跑结果替换 batch 中指定页（保留其余页）。"""
    pages = split_pages(md)
    if not pages and md.strip():
        pages = {}
    body = _strip_page_wrappers(replacement)
    has_end = bool(PAGE_END_RE.search(replacement or ""))
    pages[page_no] = PageSlice(
        page=page_no,
        body=body,
        has_begin=True,
        has_end=has_end,
    )
    return rebuild_batch_markdown(pages)


def replace_pages_in_batch(md: str, replacements: dict[int, str]) -> str:
    out = md
    for p, rep in sorted(replacements.items()):
        out = replace_page_in_batch(out, p, rep)
    return out
