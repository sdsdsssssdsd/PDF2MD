"""长文安全分块：不切开公式围栏、代码块、YAML front matter。"""
from __future__ import annotations

import re

DEFAULT_CHUNK_CHARS = 8000

_FENCE_LINE = re.compile(r"^```")
_HR = re.compile(r"^---\s*$")


def split_markdown_chunks(text: str, *, max_chars: int = DEFAULT_CHUNK_CHARS) -> list[str]:
    src = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not src.strip():
        return []
    if len(src) <= max_chars:
        return [src]

    lines = src.split("\n")
    chunks: list[str] = []
    buf: list[str] = []
    size = 0
    in_fence = False
    in_display = False
    i = 0

    def flush() -> None:
        nonlocal buf, size
        if buf:
            chunks.append("\n".join(buf).strip("\n") + "\n")
            buf = []
            size = 0

    # 保护 YAML front matter
    if lines and _HR.match(lines[0] or ""):
        end = 1
        while end < len(lines) and not _HR.match(lines[end] or ""):
            end += 1
        if end < len(lines):
            fm = "\n".join(lines[: end + 1]) + "\n"
            chunks.append(fm)
            i = end + 1

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if _FENCE_LINE.match(stripped):
            in_fence = not in_fence
        if not in_fence and stripped == "$$":
            in_display = not in_display
        piece = line + "\n"
        would = size + len(piece)
        can_break = (not in_fence) and (not in_display) and (not stripped)
        if buf and would > max_chars and can_break:
            flush()
        buf.append(line)
        size += len(piece)
        i += 1
    flush()
    return [c for c in chunks if c.strip()]


def unwrap_markdown_fence(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        first_nl = t.find("\n")
        if first_nl > 0:
            t = t[first_nl + 1 :]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3].rstrip()
    return t + ("\n" if t and not t.endswith("\n") else "")
