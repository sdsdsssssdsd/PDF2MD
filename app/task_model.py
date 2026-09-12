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


class WorkflowChoice(str, Enum):
    DAILY = "日常识图"
    VISION_API = "API高精度视觉"
    STRUCTURED = "快速自动"
    VISION_WEB = "网页高保真视觉"
    FORMAT_REPAIR = "格式修正"
    VISION = "高保真视觉"  # 兼容旧任务 / 设置


# 内部 picker ID → WorkflowChoice
WORKFLOW_PICKER_MAP: dict[str, str] = {
    "daily": WorkflowChoice.DAILY.value,
    "vision_api": WorkflowChoice.VISION_API.value,
    "structured": WorkflowChoice.STRUCTURED.value,
    "vision_web": WorkflowChoice.VISION_WEB.value,
    "format_repair": WorkflowChoice.FORMAT_REPAIR.value,
    "vision": WorkflowChoice.VISION_WEB.value,
}


def normalize_workflow(workflow: str) -> str:
    """旧值 vision / 高保真视觉 → 网页高保真。"""
    w = (workflow or "").strip()
    if w in (WorkflowChoice.VISION.value, "vision", "vision_web"):
        return WorkflowChoice.VISION_WEB.value
    if w in WORKFLOW_PICKER_MAP:
        return WORKFLOW_PICKER_MAP[w]
    for choice in WorkflowChoice:
        if w == choice.value:
            return choice.value
    return WorkflowChoice.STRUCTURED.value


def is_daily_workflow(workflow: str) -> bool:
    return normalize_workflow(workflow) == WorkflowChoice.DAILY.value


def is_structured_workflow(workflow: str) -> bool:
    return normalize_workflow(workflow) == WorkflowChoice.STRUCTURED.value


def is_vision_api_workflow(workflow: str) -> bool:
    return normalize_workflow(workflow) == WorkflowChoice.VISION_API.value


def is_vision_web_workflow(workflow: str) -> bool:
    return normalize_workflow(workflow) == WorkflowChoice.VISION_WEB.value


def is_format_repair_workflow(workflow: str) -> bool:
    return normalize_workflow(workflow) == WorkflowChoice.FORMAT_REPAIR.value


def is_vision_workflow(workflow: str) -> bool:
    w = normalize_workflow(workflow)
    return w in (WorkflowChoice.VISION_WEB.value, WorkflowChoice.VISION_API.value)


@dataclass
class DailyVisionJob:
    """日常识图会话（非 PDF ConvertTask）。"""

    image_paths: list[Path] = field(default_factory=list)
    markdown: str = ""
    status: str = TaskStatus.WAITING.value
    error: str = ""
    output_dir: Path | None = None
    archive_mode: bool = False


@dataclass
class ConvertTask:
    pdf_path: Path
    engine: str = EngineChoice.DOCLING.value
    workflow: str = WorkflowChoice.STRUCTURED.value
    status: str = TaskStatus.WAITING.value
    pages: int | None = None
    size_bytes: int = 0
    elapsed_sec: float | None = None
    output_md: Path | None = None
    output_dir: Path | None = None
    error: str = ""
    message: str = ""
    formula_recognized: int | None = None
    formula_post_ok: int | None = None
    formula_total: int | None = None
    vision_force_rerun: bool = False
    vision_final_chars: int | None = None
    vision_ds_chars: int | None = None
    vision_fidelity_ratio: float | None = None
    id: str = field(default="")

    def __post_init__(self) -> None:
        if not self.id:
            self.id = str(self.pdf_path.resolve())
        if not self.size_bytes and self.pdf_path.exists():
            self.size_bytes = self.pdf_path.stat().st_size
        self.workflow = normalize_workflow(self.workflow)

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
