"""PAGE 标记规范化与去重。"""
from __future__ import annotations

import re

from app.vision_transcribe.models import PAGE_MARKER_RE
from app.vision_transcribe.vision_structure_repair import repair_page_marker_breaks

_EXACT_PAGE_LINE = re.compile(r"^\s*<!--\s*PDF2MD:PAGE:\d{4}\s*-->\s*$")


def repair_page_marker(md: str) -> str:
    text = repair_page_marker_breaks(md or "")
    seen: set[int] = set()
    out: list[str] = []
    for line in text.splitlines():
        match = _EXACT_PAGE_LINE.match(line)
        if match:
            marker = PAGE_MARKER_RE.search(line)
            if marker is None:
                out.append(line)
                continue
            page = int(marker.group(1))
            if page in seen:
                continue
            seen.add(page)
            out.append(marker.group(0))
            continue
        out.append(line)
    return "\n".join(out) + "\n"
