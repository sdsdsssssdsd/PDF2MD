"""视觉转录数据模型与机器标记约定。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


PAGE_MARKER_RE = re.compile(r"<!--\s*PDF2MD:PAGE:(\d{4})\s*-->")
FIGURE_MARKER_RE = re.compile(r"<!--\s*PDF2MD:FIGURE:p(\d{4}):f(\d{2})\s*-->")
BATCH_BEGIN_RE = re.compile(r"<!--\s*PDF2MD:BATCH_BEGIN:(\d{4})\s*-->")
BATCH_END_RE = re.compile(r"<!--\s*PDF2MD:BATCH_END:(\d{4})\s*-->")


class BatchStatus(str, Enum):
    PENDING = "pending"
    UPLOADING = "uploading"
    WAITING_RESPONSE = "waiting_response"
    RECEIVED = "received"
    VALIDATING = "validating"
    ACCEPTED = "accepted"
    NEEDS_RETRY = "needs_retry"
    FAILED = "failed"


class PipelineState(str, Enum):
    INIT = "INIT"
    RENDERING = "RENDERING"
    READY_TO_TRANSCRIBE = "READY_TO_TRANSCRIBE"
    TRANSCRIBING = "TRANSCRIBING"
    VALIDATING_BATCH = "VALIDATING_BATCH"
    MERGING = "MERGING"
    CLEANING = "CLEANING"
    VALIDATING_DOCUMENT = "VALIDATING_DOCUMENT"
    WAITING_FIGURES = "WAITING_FIGURES"
    FIGURE_REVIEW = "FIGURE_REVIEW"
    FINALIZING = "FINALIZING"
    DONE = "DONE"
    PAUSED = "PAUSED"
    NEEDS_USER = "NEEDS_USER"  # a2-1：登录/验证码等人工作业
    NEEDS_RETRY = "NEEDS_RETRY"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class PageInfo:
    page: int
    file: str  # relative to output dir, e.g. bookfigures/page_0001.png


@dataclass
class BatchInfo:
    id: int
    start_page: int
    end_page: int
    status: str = BatchStatus.PENDING.value
    error: str = ""


@dataclass
class FigureRecord:
    marker: str  # p0008:f01
    page: int
    index: int
    file: str = ""
    bbox: list[float] = field(default_factory=list)
    status: str = "pending"  # pending | done | skipped


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "errors": self.errors, "warnings": self.warnings}


def page_marker(page: int) -> str:
    return f"<!-- PDF2MD:PAGE:{page:04d} -->"


def figure_marker(page: int, fig_index: int) -> str:
    return f"<!-- PDF2MD:FIGURE:p{page:04d}:f{fig_index:02d} -->"


def page_png_name(page: int) -> str:
    return f"page_{page:04d}.png"


def figure_png_name(page: int, fig_index: int) -> str:
    return f"p{page:04d}_fig{fig_index:02d}.png"


def batch_dir_name(batch_id: int) -> str:
    return f"batch_{batch_id:04d}"


def parse_figure_marker(token: str) -> tuple[int, int] | None:
    m = FIGURE_MARKER_RE.search(token)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))
