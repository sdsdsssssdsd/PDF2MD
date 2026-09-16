"""ConversionRequest / Job：UI 工作流编译后的统一任务句柄。"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class JobStatus:
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CancellationToken:
    """跨 Service 共享的取消令牌。不绑定 Qt。"""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def reset(self) -> None:
        self._event.clear()


@dataclass
class ConversionRequest:
    source_path: Path
    output_dir: Path
    workflow: str
    engine: str = "自动"
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def source_name(self) -> str:
        return Path(self.source_path).name


@dataclass
class PipelinePlan:
    profile: str
    parser: str | None = None
    stages: list[str] = field(default_factory=list)
    recovery: dict[str, Any] = field(default_factory=dict)
    page_overrides: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "parser": self.parser,
            "stages": list(self.stages),
            "recovery": dict(self.recovery),
            "page_overrides": dict(self.page_overrides),
            "notes": list(self.notes),
        }


@dataclass
class Job:
    id: str
    request: ConversionRequest
    plan: PipelinePlan
    status: str = "pending"
    markdown_path: str = ""
    error: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, request: ConversionRequest, plan: PipelinePlan) -> Job:
        return cls(id=uuid.uuid4().hex[:12], request=request, plan=plan)


@dataclass
class JobResult:
    job: Job
    ok: bool
    markdown_path: Path | None = None
    output_dir: Path | None = None
    error: str = ""
    stage_results: list[Any] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    quality: Any = None
    artifact: Any = None
