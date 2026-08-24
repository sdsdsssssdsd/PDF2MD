"""高保真视觉转录 Pipeline（与 Docling Lean 路线平行，互不调用）。"""
from __future__ import annotations

from app.vision_transcribe.config import VisionConfig
from app.vision_transcribe.pipeline import VisionPipeline

__all__ = ["VisionConfig", "VisionPipeline"]
