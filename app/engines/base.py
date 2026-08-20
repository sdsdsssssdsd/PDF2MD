"""Parser 引擎统一返回类型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ConversionResult:
    """解析器只负责产出原始 Markdown，不做智能修复。"""

    markdown_path: Path
    parser: str
    artifacts_dir: Path | None = None
    pages: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
