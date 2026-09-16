"""DailyVisionController：日常识图的 Qt 编排。业务在 DailyVisionService。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, Signal

from app.workers.daily_vision_worker import DailyVisionWorker

WorkerFactory = Callable[..., Any]


@dataclass(frozen=True)
class DailyVisionUiInputs:
    image_paths: tuple[Path, ...]
    archive: bool = False
    archive_dir: Path | None = None


@dataclass(frozen=True)
class DailyVisionViewState:
    running: bool
    message: str
    archive: bool
    result_status: str | None


class DailyVisionController(QObject):
    view_state_changed = Signal(object)
    finished_ok = Signal(str, str)
    finished_archive = Signal(str, str)
    log_line = Signal(str)
    batch_finished = Signal()

    def __init__(self, parent=None, *, worker_factory: WorkerFactory | None = None) -> None:
        super().__init__(parent)
        self._worker_factory = worker_factory or DailyVisionWorker
        self._worker = None
        self._inputs_snapshot: DailyVisionUiInputs | None = None
        self._cancelled = False

    @property
    def inputs_snapshot(self) -> DailyVisionUiInputs | None:
        return self._inputs_snapshot

    def is_running(self) -> bool:
        worker = self._worker
        if worker is None:
            return False
        running = getattr(worker, "isRunning", lambda: False)
        return bool(running())

    def start(self, inputs: DailyVisionUiInputs) -> bool:
        if self.is_running():
            return False
        paths = [Path(p) for p in inputs.image_paths]
        if not paths:
            return False
        self._inputs_snapshot = DailyVisionUiInputs(
            image_paths=tuple(paths),
            archive=bool(inputs.archive),
            archive_dir=Path(inputs.archive_dir) if inputs.archive_dir else None,
        )
        self._cancelled = False
        worker = self._worker_factory(
            paths,
            archive=bool(inputs.archive),
            archive_dir=Path(inputs.archive_dir) if inputs.archive_dir else None,
            parent=self,
        )
        self._worker = worker
        worker.finished_ok.connect(self._on_ok)
        worker.finished_archive.connect(self._on_archive)
        worker.log_line.connect(self.log_line.emit)
        worker.finished.connect(self._on_worker_finished)
        self._emit_state(
            DailyVisionViewState(
                running=True,
                message="识别中…",
                archive=bool(inputs.archive),
                result_status=None,
            )
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

    def _on_ok(self, markdown: str, error: str) -> None:
        self.finished_ok.emit(markdown, error)
        self._emit_state(
            DailyVisionViewState(
                running=True,
                message=error or "识别完成",
                archive=False,
                result_status="failed" if error else "verified",
            )
        )

    def _on_archive(self, md_path: str, error: str) -> None:
        self.finished_archive.emit(md_path, error)
        self._emit_state(
            DailyVisionViewState(
                running=True,
                message=error or "已归档",
                archive=True,
                result_status="failed" if error else "verified",
            )
        )

    def _on_worker_finished(self) -> None:
        shown = "cancelled" if self._cancelled else None
        self._emit_state(
            DailyVisionViewState(
                running=False,
                message="空闲",
                archive=bool(self._inputs_snapshot and self._inputs_snapshot.archive),
                result_status=shown,
            )
        )
        self._worker = None
        self.batch_finished.emit()

    def _emit_state(self, state: DailyVisionViewState) -> None:
        self.view_state_changed.emit(state)
