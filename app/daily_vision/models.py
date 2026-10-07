"""日常识图数据模型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.utils.progress import PipelineCancelled, ProgressFn

__all__ = [
    "DailyVisionResult",
    "FigureRegion",
    "DailyVisionCancelled",
    "ProgressFn",
]


@dataclass
class FigureRegion:
    marker: str
    source_image: int
    region_type: str = "figure"
    bbox: list[float] = field(default_factory=list)


@dataclass
class DailyVisionResult:
    markdown: str = ""
    regions: list[FigureRegion] = field(default_factory=list)
    raw_json: str = ""
    warnings: list[str] = field(default_factory=list)


class DailyVisionCancelled(PipelineCancelled):
    """用户取消日常识图（分批之间 / 流式接收中检查）。"""
