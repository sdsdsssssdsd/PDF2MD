"""转换任务数据模型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class TaskStatus(str, Enum):
    WAITING = "等待"
    RUNNING = "转换中"
    DONE = "完成"
    FAILED = "失败"
    CANCELLED = "取消"


class EngineChoice(str, Enum):
    DOCLING = "Docling"
    MINERU = "MinerU"
    AUTO = "自动"


@dataclass
class ConvertTask:
    pdf_path: Path
    engine: str = EngineChoice.DOCLING.value
    status: str = TaskStatus.WAITING.value
    pages: int | None = None
    size_bytes: int = 0
    elapsed_sec: float | None = None
    output_md: Path | None = None
    output_dir: Path | None = None
    error: str = ""
    message: str = ""
    id: str = field(default="")

    def __post_init__(self) -> None:
        if not self.id:
            self.id = str(self.pdf_path.resolve())
        if not self.size_bytes and self.pdf_path.exists():
            self.size_bytes = self.pdf_path.stat().st_size

    @property
    def name(self) -> str:
        return self.pdf_path.name

    @property
    def size_label(self) -> str:
        b = self.size_bytes
        if b < 1024:
            return f"{b} B"
        if b < 1024 * 1024:
            return f"{b / 1024:.1f} KB"
        return f"{b / (1024 * 1024):.1f} MB"
