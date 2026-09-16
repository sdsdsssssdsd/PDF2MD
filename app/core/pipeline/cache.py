"""Stage cache 预留。现有 Vision file_id 缓存与公式 crop cache 仍为权威实现。"""
from __future__ import annotations

from pathlib import Path


def cache_dir(output_dir: Path) -> Path:
    return Path(output_dir) / ".pdf2md" / "cache"
