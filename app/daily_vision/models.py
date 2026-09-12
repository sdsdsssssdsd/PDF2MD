"""日常识图数据模型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


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
