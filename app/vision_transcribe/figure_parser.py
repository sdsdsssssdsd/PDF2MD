"""扫描 FIGURE 机器标记。"""
from __future__ import annotations

from app.vision_transcribe.models import FIGURE_MARKER_RE, FigureRecord


def parse_figure_markers(md: str) -> list[FigureRecord]:
    records: list[FigureRecord] = []
    seen: set[str] = set()
    for m in FIGURE_MARKER_RE.finditer(md or ""):
        page = int(m.group(1))
        idx = int(m.group(2))
        key = f"p{page:04d}:f{idx:02d}"
        if key in seen:
            continue
        seen.add(key)
        records.append(
            FigureRecord(
                marker=key,
                page=page,
                index=idx,
                status="pending",
            )
        )
    return records
