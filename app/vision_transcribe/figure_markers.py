"""FIGURE 占位符：补全缺失标记、从题注解析 Figure 编号。"""
from __future__ import annotations

import re

from app.vision_transcribe.models import FIGURE_MARKER_RE, PAGE_MARKER_RE

_FIGURE_CAPTION_LINE = re.compile(
    r"^(?:\*\*)?Figure\s+(\d+)\s*:(?:\*\*)?",
    re.I,
)


def figure_numbers_by_marker(md: str) -> dict[str, int]:
    """从每个 FIGURE 标记后题注解析 Figure 编号 → marker key。"""
    out: dict[str, int] = {}
    text = md or ""
    for m in FIGURE_MARKER_RE.finditer(text):
        key = f"p{int(m.group(1)):04d}:f{int(m.group(2)):02d}"
        tail = text[m.end() : m.end() + 600]
        cap = _FIGURE_CAPTION_LINE.search(tail.lstrip())
        if cap:
            out[key] = int(cap.group(1))
    return out


def repair_missing_figure_markers(md: str) -> str:
    """题注 `Figure N:` 前无占位符时插入 FIGURE 标记（按最近 PAGE）。"""
    if not md:
        return md
    lines = md.splitlines(keepends=True)
    out: list[str] = []
    last_page = 1
    fig_on_page: dict[int, int] = {}
    for i, line in enumerate(lines):
        pm = PAGE_MARKER_RE.search(line)
        if pm:
            last_page = int(pm.group(1))
        stripped = line.strip()
        cap = _FIGURE_CAPTION_LINE.match(stripped)
        if cap:
            prefix = "".join(lines[max(0, i - 5) : i])
            if "PDF2MD:FIGURE" not in prefix:
                fig_on_page[last_page] = fig_on_page.get(last_page, 0) + 1
                idx = fig_on_page[last_page]
                out.append(
                    f"<!-- PDF2MD:FIGURE:p{last_page:04d}:f{idx:02d} -->\n\n"
                )
        out.append(line)
    return "".join(out)
