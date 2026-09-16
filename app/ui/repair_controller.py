"""RepairController：格式修正的 Qt 编排。业务在 RepairService。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, Signal

from app.format_repair.file_io import FileSnapshot
from app.format_repair.models import RepairConfig
from app.workers.format_repair_worker import FormatRepairWorker

WorkerFactory = Callable[..., Any]


@dataclass(frozen=True)
class RepairUiInputs:
    text: str
    config: RepairConfig
    source_path: Path | None = None
    snapshot: FileSnapshot | None = None


@dataclass(frozen=True)
class RepairViewState:
    running: bool
    message: str
    result_status: str | None


class RepairController(QObject):
    view_state_changed = Signal(object)
    finished_result = Signal(object)
    failed = Signal(str)
    batch_finished = Signal()

    def __init__(self, parent=None, *, worker_factory: WorkerFactory | None = None) -> None:
        super().__init__(parent)
        self._worker_factory = worker_factory or FormatRepairWorker
        self._worker = None
        self._inputs_snapshot: RepairUiInputs | None = None
        self._cancelled = False

    @property
    def inputs_snapshot(self) -> RepairUiInputs | None:
        return self._inputs_snapshot

    def is_running(self) -> bool:
        worker = self._worker
        if worker is None:
            return False
        running = getattr(worker, "isRunning", lambda: False)
        return bool(running())

    def start(self, inputs: RepairUiInputs) -> bool:
        if self.is_running():
            return False
        if not str(inputs.text or "").strip():
            return False
        self._inputs_snapshot = inputs
        self._cancelled = False
        worker = self._worker_factory(
            inputs.text,
            inputs.config,
            source_path=inputs.source_path,
            snapshot=inputs.snapshot,
            parent=self,
        )
        self._worker = worker
        worker.finished_result.connect(self._on_result)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(self._on_worker_finished)
        self._emit_state(
            RepairViewState(running=True, message="正在修正格式…", result_status=None)
        )
        worker.start()
        return True

    def cancel(self) -> None:
        if not self.is_running():
            return
        self._cancelled = True
        worker = self._worker
        if worker is not None and hasattr(worker, "request_cancel"):
            worker.request_cancel()

    def shutdown(self, timeout_ms: int = 3000) -> None:
        worker = self._worker
        if worker is None:
            return
        if self.is_running() and hasattr(worker, "request_cancel"):
            self._cancelled = True
            worker.request_cancel()
        wait = getattr(worker, "wait", None)
        if callable(wait):
            wait(timeout_ms)

    def _on_result(self, result) -> None:
        self.finished_result.emit(result)
        ok = bool(getattr(result, "ok", True))
        self._emit_state(
            RepairViewState(
                running=True,
                message="修正完成" if ok else "修正未通过完整性门",
                result_status="verified" if ok else "failed",
            )
        )

    def _on_failed(self, message: str) -> None:
        self.failed.emit(message)
        self._emit_state(
            RepairViewState(running=True, message=message or "失败", result_status="failed")
        )

    def _on_worker_finished(self) -> None:
        shown = "cancelled" if self._cancelled else None
        self._emit_state(
            RepairViewState(running=False, message="空闲", result_status=shown)
        )
        self._worker = None
        self.batch_finished.emit()

    def _emit_state(self, state: RepairViewState) -> None:
        self.view_state_changed.emit(state)
