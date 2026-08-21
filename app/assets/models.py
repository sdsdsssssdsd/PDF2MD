"""Asset 数据模型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AssetConfig:
    """Figure Asset Pipeline 配置。"""

    enabled: bool = True
    # 是否尝试子图拆分（V1：默认关，仅在证据充分时才拆）
    enable_subfigure_split: bool = True
    # 子图：要么全部通过验证，要么一个都不拆
    require_all_subfigures: bool = True
    min_subfigure_confidence: float = 0.85
    # Markdown 路径：relative | absolute
    image_path_mode: str = "relative"
    write_manifest: bool = False  # 默认不导出 images/manifest.json
    # 是否删除已重命名的 parser 原始文件
    cleanup_parser_files: bool = True


@dataclass
class SubfigureAsset:
    index: int  # Y，从 1 起
    original_label: str  # a / b / i / A ...
    file: str  # 文件名（相对 images/）
    bbox: list[float] | None = None  # 相对主图 0..1 或像素
    confidence: float = 0.0
    path: Path | None = None


@dataclass
class FigureAsset:
    asset_id: str  # fig_0001
    asset_index: int  # X，阅读顺序
    file: str
    figure_label: str | None = None  # 原文 "Fig. 1" / "Figure 3" / "Figure S1"
    caption: str | None = None  # 完整 caption 文本（含 label）
    caption_body: str | None = None  # 去掉 label 后的正文
    page: int | None = None
    bbox: list[float] | None = None
    parser_source: str | None = None
    parser_file: str | None = None
    confidence: float = 1.0
    subfigures: list[SubfigureAsset] = field(default_factory=list)
    subfigure_status: str = "none"  # none | extracted | uncertain | skipped
    path: Path | None = None


@dataclass
class AssetPipelineResult:
    markdown_path: Path
    images_dir: Path
    manifest_path: Path | None
    figures: list[FigureAsset] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
