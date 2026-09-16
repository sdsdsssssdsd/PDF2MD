"""ConversionController：Qt 应用编排。文档业务仍在 ConversionService / Core。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, Signal

from app.core.domain.quality import QualityVerdict
from app.core.service.conversion import ConversionOptions
from app.task_model import ConvertTask
from app.workers.docling_worker import ConversionWorker

WorkerFactory = Callable[..., Any]


@dataclass(frozen=True)
class ConversionUiInputs:
    """MainWindow 当前控件值。不含 Docling/MinerU/QA 规则。"""

    output_root: Path
    per_folder: bool = True
    ocr_mode: str = "auto"
    keep_tables: bool = True
    formulas_checked: bool = True
    formula_recovery_preset: str = "balanced"
    deepseek_lp_checked: bool = False
    images_scale: float = 2.0
    image_path_mode: str = "relative"
    export_md: bool = True
    export_raw_md: bool = False
    export_repair_json: bool = False
    export_conversion_log: bool = False
    export_manifest: bool = False
    export_formula_qa: bool = False
    export_timings: bool = False


@dataclass(frozen=True)
class ConversionViewState:
    running: bool
    progress: int
    stage: str | None
    message: str
    can_cancel: bool
    result_status: str | None


def compile_options(inputs: ConversionUiInputs) -> ConversionOptions:
    """控件值 → 冻结 ConversionOptions。Lean Balanced 规则只在这里编译一次。"""
    preset = inputs.formula_recovery_preset or "balanced"
    deepseek_lp = preset == "balanced" and bool(inputs.deepseek_lp_checked)
    keep_formulas = False if deepseek_lp else bool(inputs.formulas_checked)
    return ConversionOptions(
        output_root=Path(inputs.output_root),
        per_folder=bool(inputs.per_folder),
        ocr_mode=str(inputs.ocr_mode or "auto"),
        keep_tables=bool(inputs.keep_tables),
        keep_formulas=keep_formulas,
        formula_recovery_preset=preset,
        deepseek_limited_production=deepseek_lp,
        images_scale=float(inputs.images_scale),
        image_path_mode=str(inputs.image_path_mode or "relative"),
        export_md=bool(inputs.export_md),
        export_raw_md=bool(inputs.export_raw_md),
        export_repair_json=bool(inputs.export_repair_json),
        export_conversion_log=bool(inputs.export_conversion_log),
        export_manifest=bool(inputs.export_manifest),
        export_formula_qa=bool(inputs.export_formula_qa),
        export_timings=bool(inputs.export_timings),
    )


def present_result_status(
    *,
    cancelled: bool,
    ok: bool,
    quality_status: str | None,
) -> str:
    """JobRunner / QualityReport 终态 → UI 展示。不重新判定质量。"""
    if cancelled:
        return "cancelled"
    if quality_status:
        return quality_status
    return QualityVerdict.VERIFIED.value if ok else QualityVerdict.FAILED.value


class ConversionController(QObject):
    view_state_changed = Signal(object)
    task_status = Signal(str, str, str)
    task_finished = Signal(str, bool, str, str, str, float)
    log_line = Signal(str)
    stage = Signal(str)
    pipeline_stage = Signal(str)
    deepseek_state = Signal(str)
    batch_finished = Signal()

    def __init__(self, parent=None, *, worker_factory: WorkerFactory | None = None) -> None:
        super().__init__(parent)
        self._worker_factory = worker_factory or ConversionWorker
        self._worker = None
        self._options_snapshot: ConversionOptions | None = None
        self._cancelled = False
        self._done = 0
        self._total = 0
        self._last_quality: str | None = None

    @property
    def options_snapshot(self) -> ConversionOptions | None:
        return self._options_snapshot

    def is_running(self) -> bool:
        worker = self._worker
        if worker is None:
            return False
        running = getattr(worker, "isRunning", lambda: False)
        return bool(running())

    def start(self, tasks: list[ConvertTask], inputs: ConversionUiInputs) -> bool:
        if self.is_running():
            return False
        waiting = list(tasks)
        if not waiting:
            return False
        options = compile_options(inputs)
        self._options_snapshot = options
        self._cancelled = False
        self._done = 0
        self._total = len(waiting)
        self._last_quality = None
        worker = self._worker_factory(waiting, parent=self, **options.worker_kwargs())
        self._worker = worker
        worker.task_status.connect(self._on_worker_task_status)
        worker.task_finished.connect(self._on_worker_task_finished)
        worker.log_line.connect(self.log_line.emit)
        worker.stage.connect(self._on_worker_stage)
        worker.pipeline_stage.connect(self._on_worker_pipeline)
        worker.deepseek_state.connect(self.deepseek_state.emit)
        if hasattr(worker, "quality_status"):
            worker.quality_status.connect(self._on_worker_quality)
        worker.finished.connect(self._on_worker_finished)
        self._emit_state(
            ConversionViewState(
                running=True,
                progress=0,
                stage="parse",
                message="开始转换",
                can_cancel=True,
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
        if worker is not None:
            worker.request_cancel()
        self._emit_state(
            ConversionViewState(
                running=True,
                progress=_progress(self._done, self._total),
                stage=None,
                message="正在取消…",
                can_cancel=False,
                result_status="cancelled",
            )
        )

    def shutdown(self, timeout_ms: int = 3000) -> None:
        worker = self._worker
        if worker is None:
            return
        if self.is_running():
            self._cancelled = True
            worker.request_cancel()
            wait = getattr(worker, "wait", None)
            if callable(wait):
                wait(timeout_ms)

    def _on_worker_quality(self, _task_id: str, status: str) -> None:
        self._last_quality = status or self._last_quality

    def _on_worker_task_status(self, task_id: str, status: str, message: str) -> None:
        self.task_status.emit(task_id, status, message)
        if not self.is_running() and not self._cancelled:
            return
        self._emit_state(
            ConversionViewState(
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
        shown = present_result_status(
            cancelled=self._cancelled,
            ok=ok,
            quality_status=self._last_quality,
        )
        self.task_finished.emit(task_id, ok, md, out_dir, err, elapsed)
        self._emit_state(
            ConversionViewState(
                running=True,
                progress=_progress(self._done, self._total),
                stage=None,
                message="" if ok else (err or "失败"),
                can_cancel=not self._cancelled,
                result_status=shown,
            )
        )

    def _on_worker_stage(self, text: str) -> None:
        self.stage.emit(text)
        self._emit_state(
            ConversionViewState(
                running=self.is_running() or self._cancelled,
                progress=_progress(self._done, self._total),
                stage=None,
                message=text or "",
                can_cancel=self.is_running() and not self._cancelled,
                result_status="cancelled" if self._cancelled else self._last_quality,
            )
        )

    def _on_worker_pipeline(self, stage: str) -> None:
        self.pipeline_stage.emit(stage)
        self._emit_state(
            ConversionViewState(
                running=self.is_running() or bool(stage and stage != "idle"),
                progress=_progress(self._done, self._total),
                stage=stage or None,
                message="",
                can_cancel=self.is_running() and not self._cancelled,
                result_status="cancelled" if self._cancelled else self._last_quality,
            )
        )

    def _on_worker_finished(self) -> None:
        shown = present_result_status(
            cancelled=self._cancelled,
            ok=not self._cancelled,
            quality_status=self._last_quality,
        )
        if self._cancelled:
            shown = "cancelled"
        self._emit_state(
            ConversionViewState(
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

    def _emit_state(self, state: ConversionViewState) -> None:
        self.view_state_changed.emit(state)


def _idle() -> ConversionViewState:
    return ConversionViewState(
        running=False,
        progress=0,
        stage=None,
        message="空闲",
        can_cancel=False,
        result_status=None,
    )


def _progress(done: int, total: int) -> int:
    if total <= 0:
        return 0
    return max(0, min(100, int(round(100.0 * done / total))))
