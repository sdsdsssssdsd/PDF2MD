"""后台转换 Worker：Qt 纯桥。业务在 ConversionService / JobRunner。"""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QMutex, QThread, Signal

from app.core.service.conversion import ConversionOptions, ConversionService, format_task_error
from app.task_model import ConvertTask, TaskStatus
from app.ui.pipeline_classify import classify_deepseek_state, classify_pipeline_stage
from app.utils.logger import get_logger, new_run_id, write_task_log
from app.utils.paths import task_output_dir


class ConversionWorker(QThread):
    task_status = Signal(str, str, str)  # task_id, status, message
    task_finished = Signal(str, bool, str, str, str, float)  # id, ok, md, out_dir, err, elapsed
    quality_status = Signal(str, str)  # task_id, QualityReport.status
    log_line = Signal(str)
    stage = Signal(str)
    pipeline_stage = Signal(str)  # parse|assets|repair|mirror|idle · 只读 UI
    deepseek_state = Signal(str)  # cold|warming|warm|unavailable · 只读 UI

    def __init__(
        self,
        tasks: list[ConvertTask],
        *,
        output_root: Path,
        per_folder: bool,
        ocr_mode: str,
        keep_images: bool = True,
        keep_tables: bool = True,
        keep_formulas: bool = True,
        formula_recovery_preset: str = "balanced",
        deepseek_limited_production: bool = False,
        images_scale: float = 2.0,
        image_path_mode: str = "relative",
        export_md: bool = True,
        export_raw_md: bool = False,
        export_repair_json: bool = False,
        export_conversion_log: bool = False,
        export_manifest: bool = False,
        export_formula_qa: bool = False,
        export_timings: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._tasks = tuple(tasks)
        self._options_snapshot = ConversionOptions(
            output_root=output_root,
            per_folder=per_folder,
            ocr_mode=ocr_mode,
            keep_images=keep_images,
            keep_tables=keep_tables,
            keep_formulas=keep_formulas,
            formula_recovery_preset=formula_recovery_preset,
            deepseek_limited_production=deepseek_limited_production,
            images_scale=images_scale,
            image_path_mode=image_path_mode,
            export_md=export_md,
            export_raw_md=export_raw_md,
            export_repair_json=export_repair_json,
            export_conversion_log=export_conversion_log,
            export_manifest=export_manifest,
            export_formula_qa=export_formula_qa,
            export_timings=export_timings,
        )
        self._service: ConversionService | None = None
        self._mutex = QMutex()
        self._cancel = False

    @property
    def _docling_formula_enrich(self) -> bool:
        return bool(self._options_snapshot.docling_formula_enrich)

    @property
    def _repair_keep_formulas(self) -> bool:
        return bool(self._options_snapshot.repair_keep_formulas)

    @property
    def _keep_formulas(self) -> bool:
        return self._docling_formula_enrich

    def _parse_keep_formulas(self) -> bool:
        return self._options_snapshot.parse_keep_formulas()

    def request_cancel(self) -> None:
        self._mutex.lock()
        self._cancel = True
        self._mutex.unlock()
        if self._service is not None:
            self._service.request_cancel()

    def _cancelled(self) -> bool:
        self._mutex.lock()
        v = self._cancel
        self._mutex.unlock()
        return v

    def run(self) -> None:
        log = get_logger()
        snapshot = self._options_snapshot
        tasks = tuple(self._tasks)
        service = ConversionService(snapshot)
        self._service = service
        if self._cancelled():
            service.request_cancel()
        batch_id = new_run_id()
        batch_client = service.prepare_batch_client()

        for batch_idx, task in enumerate(tasks):
            if self._cancelled():
                self.task_status.emit(task.id, TaskStatus.CANCELLED.value, "已取消")
                continue

            self.task_status.emit(task.id, TaskStatus.RUNNING.value, "开始转换")
            self.stage.emit(f"正在转换：{task.name}")
            self.pipeline_stage.emit("parse")
            self.log_line.emit(f"开始转换 {task.name}（引擎 {task.engine}）")
            log.info("开始转换 %s 引擎=%s", task.name, task.engine)

            out_dir = task_output_dir(snapshot.output_root, task.pdf_path, snapshot.per_folder)
            out_dir.mkdir(parents=True, exist_ok=True)
            t0 = time.time()
            run_id = new_run_id()

            def progress(msg: str, _out=out_dir, _run=run_id) -> None:
                self.stage.emit(msg)
                self.log_line.emit(msg)
                kind = classify_pipeline_stage(msg)
                if kind:
                    self.pipeline_stage.emit(kind)
                ds = classify_deepseek_state(msg)
                if ds:
                    self.deepseek_state.emit(ds)
                if snapshot.export_conversion_log:
                    write_task_log(_out, msg, run_id=_run)
                    write_task_log(_out, f"[{_run}] {msg}")

            try:
                result = service.run_task(
                    task,
                    progress=progress,
                    batch_idx=batch_idx,
                    batch_id=batch_id,
                    batch_client=batch_client,
                    run_id=run_id,
                )
                elapsed = float((result.metrics or {}).get("elapsed") or (time.time() - t0))
                done_dir = Path(result.output_dir or out_dir)
                qstatus = ""
                if result.quality is not None:
                    qstatus = str(getattr(result.quality, "status", "") or "")
                if qstatus:
                    self.quality_status.emit(task.id, qstatus)
                if result.ok:
                    md_str = ""
                    if snapshot.export_md and result.markdown_path:
                        md_path = Path(result.markdown_path)
                        if md_path.exists():
                            md_str = str(md_path)
                    self.task_finished.emit(task.id, True, md_str, str(done_dir), "", elapsed)
                    self.log_line.emit(f"完成 {task.name}")
                    log.info("完成 %s -> %s", task.name, done_dir)
                else:
                    err = result.error or "conversion failed"
                    if snapshot.export_conversion_log:
                        write_task_log(done_dir, f"[{run_id}] FAILED: {err}", run_id=run_id)
                    self.task_finished.emit(task.id, False, "", str(done_dir), err, elapsed)
                    self.log_line.emit(f"失败 {task.name}: {err}")
                    log.error("失败 %s: %s", task.name, err)
            except Exception as e:
                elapsed = time.time() - t0
                err = format_task_error(e)
                if snapshot.export_conversion_log:
                    write_task_log(out_dir, err, run_id=run_id)
                    write_task_log(out_dir, f"[{run_id}] FAILED: {e}")
                self.task_finished.emit(task.id, False, "", str(out_dir), str(e), elapsed)
                self.log_line.emit(f"失败 {task.name}: {e}")
                log.exception("失败 %s", task.name)

        self.stage.emit("空闲")
        self.pipeline_stage.emit("idle")
