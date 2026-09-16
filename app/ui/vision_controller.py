"""VisionController：视觉任务的 Qt 编排。业务在 VisionService。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, Signal

from app.core.service.vision import VisionOptions
from app.task_model import ConvertTask
from app.workers.vision_worker import VisionConversionWorker, VisionFigureRebuildWorker

WorkerFactory = Callable[..., Any]


@dataclass(frozen=True)
class VisionUiInputs:
    output_root: Path
    api: bool = False
    api_precision: str = "standard"
    browser_mode: str = "clipboard"
    images_scale: float = 2.0
    image_path_mode: str = "relative"


@dataclass(frozen=True)
class VisionViewState:
    running: bool
    progress: int
    stage: str | None
    message: str
    can_cancel: bool
    result_status: str | None
    rebuild: bool = False


def compile_vision_options(inputs: VisionUiInputs) -> VisionOptions:
    return VisionOptions(
        output_root=Path(inputs.output_root),
        per_folder=True,
        api=bool(inputs.api),
        api_precision=str(inputs.api_precision or "standard"),
        browser_mode=str(inputs.browser_mode or "clipboard"),
        images_scale=float(inputs.images_scale),
        image_path_mode=str(inputs.image_path_mode or "relative"),
    )


class VisionController(QObject):
    view_state_changed = Signal(object)
    task_status = Signal(str, str, str)
    task_finished = Signal(str, bool, str, str, str, float)
    log_line = Signal(str)
    stage = Signal(str)
    pipeline_stage = Signal(str)
    needs_clipboard = Signal(str, int, int, int, str)
    needs_user = Signal(str, str)
    needs_figures = Signal(str, str)
    rebuild_finished = Signal(str, str)
    rebuild_failed = Signal(str, str)
    batch_finished = Signal()

    def __init__(
        self,
        parent=None,
        *,
        worker_factory: WorkerFactory | None = None,
        rebuild_factory: WorkerFactory | None = None,
    ) -> None:
        super().__init__(parent)
        self._worker_factory = worker_factory or VisionConversionWorker
        self._rebuild_factory = rebuild_factory or VisionFigureRebuildWorker
        self._worker = None
        self._rebuild = None
        self._options_snapshot: VisionOptions | None = None
        self._cancelled = False
        self._done = 0
        self._total = 0

    @property
    def options_snapshot(self) -> VisionOptions | None:
        return self._options_snapshot

    def is_running(self) -> bool:
        return _running(self._worker) or _running(self._rebuild)

    def start(self, tasks: list[ConvertTask], inputs: VisionUiInputs) -> bool:
        if self.is_running():
            return False
        waiting = list(tasks)
        if not waiting:
            return False
        options = compile_vision_options(inputs)
        self._options_snapshot = options
        self._cancelled = False
        self._done = 0
        self._total = len(waiting)
        worker = self._worker_factory(waiting, parent=self, **options.worker_kwargs())
        self._worker = worker
        worker.task_status.connect(self._on_worker_task_status)
        worker.task_finished.connect(self._on_worker_task_finished)
        worker.log_line.connect(self.log_line.emit)
        worker.stage.connect(self.stage.emit)
        worker.pipeline_stage.connect(self._on_worker_pipeline)
        worker.needs_clipboard.connect(self.needs_clipboard.emit)
        worker.needs_user.connect(self.needs_user.emit)
        worker.needs_figures.connect(self.needs_figures.emit)
        worker.finished.connect(self._on_worker_finished)
        self._emit_state(
            VisionViewState(
                running=True,
                progress=0,
                stage="render",
                message="开始视觉转换",
                can_cancel=True,
                result_status=None,
            )
        )
        worker.start()
        return True

    def start_rebuild(
        self,
        task_id: str,
        pdf_path: Path,
        output_dir: Path,
        inputs: VisionUiInputs,
    ) -> bool:
        if self.is_running():
            return False
        options = compile_vision_options(inputs)
        self._options_snapshot = options
        self._cancelled = False
        worker = self._rebuild_factory(
            task_id,
            Path(pdf_path),
            Path(output_dir),
            config=options.to_config(),
            parent=self,
        )
        self._rebuild = worker
        worker.log_line.connect(self.log_line.emit)
        worker.finished_ok.connect(self._on_rebuild_ok)
        worker.failed.connect(self._on_rebuild_failed)
        worker.finished.connect(self._on_rebuild_thread_finished)
        self._emit_state(
            VisionViewState(
                running=True,
                progress=0,
                stage="figures",
                message="仅重合并与裁图",
                can_cancel=True,
                result_status=None,
                rebuild=True,
            )
        )
        worker.start()
        return True

    def submit_clipboard(self, text: str) -> None:
        worker = self._worker
        if worker is not None and hasattr(worker, "submit_clipboard"):
            worker.submit_clipboard(text)

    def resume_after_user(self) -> None:
        worker = self._worker
        if worker is not None and hasattr(worker, "resume_after_user"):
            worker.resume_after_user()

    def cancel(self) -> None:
        if not self.is_running():
            return
        self._cancelled = True
        for w in (self._worker, self._rebuild):
            if w is not None and hasattr(w, "request_cancel"):
                w.request_cancel()
        self._emit_state(
            VisionViewState(
                running=True,
                progress=_progress(self._done, self._total),
                stage=None,
                message="正在取消…",
                can_cancel=False,
                result_status="cancelled",
            )
        )

    def shutdown(self, timeout_ms: int = 3000) -> None:
        self._cancelled = True
        for w in (self._worker, self._rebuild):
            if w is None:
                continue
            if _running(w) and hasattr(w, "request_cancel"):
                w.request_cancel()
            wait = getattr(w, "wait", None)
            if callable(wait):
                wait(timeout_ms)

    def _on_worker_task_status(self, task_id: str, status: str, message: str) -> None:
        self.task_status.emit(task_id, status, message)
        self._emit_state(
            VisionViewState(
                running=True,
                progress=_progress(self._done, self._total),
                stage=None,
                message=message or "",
                can_cancel=not self._cancelled,
                result_status="cancelled" if self._cancelled else None,
            )
        )

    def _on_worker_task_finished(
        self,
        task_id: str,
        ok: bool,
        md: str,
        out_dir: str,
        err: str,
        elapsed: float,
    ) -> None:
        self._done += 1
        shown = "cancelled" if self._cancelled else ("verified" if ok else "failed")
        self.task_finished.emit(task_id, ok, md, out_dir, err, elapsed)
        self._emit_state(
            VisionViewState(
                running=True,
                progress=_progress(self._done, self._total),
                stage=None,
                message="" if ok else (err or "失败"),
                can_cancel=not self._cancelled,
                result_status=shown,
            )
        )

    def _on_worker_pipeline(self, stage: str) -> None:
        self.pipeline_stage.emit(stage)
        self._emit_state(
            VisionViewState(
                running=self.is_running() or bool(stage and stage != "idle"),
                progress=_progress(self._done, self._total),
                stage=stage or None,
                message="",
                can_cancel=self.is_running() and not self._cancelled,
                result_status="cancelled" if self._cancelled else None,
            )
        )

    def _on_worker_finished(self) -> None:
        shown = "cancelled" if self._cancelled else None
        self._emit_state(
            VisionViewState(
                running=False,
                progress=100 if self._total and self._done >= self._total else _progress(self._done, self._total),
                stage="idle",
                message="空闲",
                can_cancel=False,
                result_status=shown,
            )
        )
        self._worker = None
        self.batch_finished.emit()

    def _on_rebuild_ok(self, task_id: str, final_md: str) -> None:
        self.rebuild_finished.emit(task_id, final_md)
        self._emit_state(
            VisionViewState(
                running=False,
                progress=100,
                stage="idle",
                message="裁图完成",
                can_cancel=False,
                result_status="verified",
                rebuild=True,
            )
        )

    def _on_rebuild_failed(self, task_id: str, err: str) -> None:
        self.rebuild_failed.emit(task_id, err)
        self._emit_state(
            VisionViewState(
                running=False,
                progress=0,
                stage="idle",
                message=err or "裁图失败",
                can_cancel=False,
                result_status="failed",
                rebuild=True,
            )
        )

    def _on_rebuild_thread_finished(self) -> None:
        self._rebuild = None

    def _emit_state(self, state: VisionViewState) -> None:
        self.view_state_changed.emit(state)


def _running(worker) -> bool:
    if worker is None:
        return False
    running = getattr(worker, "isRunning", lambda: False)
    return bool(running())


def _progress(done: int, total: int) -> int:
    if total <= 0:
        return 0
    return max(0, min(100, int(round(100.0 * done / total))))
