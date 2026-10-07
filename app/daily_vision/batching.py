"""日常识图分批合并：marker / source_image 序号平移。

每批请求里模型都从 1 开始编号（source_image=1..批内张数，marker=i0001:f01）。
合并回整批图片时，必须按批偏移量平移，否则跨批 marker 撞名、裁图会取错源图。
"""
from __future__ import annotations

import re

from app.daily_vision.models import DailyVisionResult, FigureRegion
from app.daily_vision.exporter import IMAGE_MARKER_RE

_KEY_RE = re.compile(r"^i(\d+)(.*)$")


def renumber_marker(marker: str, offset: int) -> str:
    """i0001:f01 + offset(6) → i0007:f01。"""
    text = (marker or "").strip()
    if offset <= 0:
        return text
    m = _KEY_RE.match(text)
    if not m:
        return text
    return f"i{int(m.group(1)) + offset:04d}{m.group(2)}"


def renumber_markdown(markdown: str, offset: int) -> str:
    """把正文里的 <!-- PDF2MD:IMAGE:i0001:f01 --> 序号按批偏移平移。"""
    if offset <= 0 or not markdown:
        return markdown

    def _repl(match: re.Match) -> str:
        return f"<!-- PDF2MD:IMAGE:{renumber_marker(match.group(1), offset)} -->"

    return IMAGE_MARKER_RE.sub(_repl, markdown)


def merge_batch(merged: DailyVisionResult, batch: DailyVisionResult, offset: int) -> None:
    """把一批结果按偏移并入总结果（markdown 顺序拼接）。"""
    body = renumber_markdown(batch.markdown, offset).strip()
    if body:
        merged.markdown = f"{merged.markdown}\n\n{body}".strip() if merged.markdown else body
    for reg in batch.regions:
        merged.regions.append(
            FigureRegion(
                marker=renumber_marker(reg.marker, offset),
                source_image=max(1, int(reg.source_image)) + offset,
                region_type=reg.region_type,
                bbox=list(reg.bbox),
            )
        )
