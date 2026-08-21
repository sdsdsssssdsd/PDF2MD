"""Figure Asset Pipeline：从 parser 候选图恢复论文语义 Figure 资产。"""
from __future__ import annotations

from app.assets.models import AssetConfig, AssetPipelineResult
from app.assets.pipeline import AssetPipeline

__all__ = ["AssetConfig", "AssetPipeline", "AssetPipelineResult"]
