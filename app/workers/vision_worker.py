"""高保真视觉转换 Worker（QThread）：只调度 VisionPipeline，不含 DOM 逻辑。"""
from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QMutex, QThread, Signal, QWaitCondition

from app.task_model import ConvertTask, TaskStatus, WorkflowChoice
from app.utils.logger import get_logger
from app.utils.paths import vision_task_output_dir
from app.vision_transcribe.config import VisionConfig
from app.vision_transcribe.manifest import vision_dir
from app.vision_transcribe.models import BatchStatus, PipelineState
from app.vision_transcribe.pipeline import VisionPipeline
from app.vision_transcribe.browser.manual_clipboard import ManualClipboardAdapter


class VisionConversionWorker(QThread):
    task_status = Signal(str, str, str)  # task_id, status, message
    task_finished = Signal(str, bool, str, str, str, float)
    log_line = Signal(str)
    stage = Signal(str)
    pipeline_stage = Signal(str)  # render|transcribe|validate|merge|figures|idle
    # GUI：需要粘贴本批结果 / 人工处理浏览器
    needs_clipboard = Signal(str, int, int, int, str)  # task_id, batch_id, start, end, hint
    needs_user = Signal(str, str)  # task_id, message
    needs_figures = Signal(str, str)  # task_id, output_dir

    def __init__(
        self,
        tasks: list[ConvertTask],
        *,
        output_root: Path,
        per_folder: bool,
        config: VisionConfig | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._tasks = list(tasks)
        self._output_root = Path(output_root)
        self._per_folder = per_folder
        self._config = config or VisionConfig()
        self._cancel = False
        self._mutex = QMutex()
        self._wait = QWaitCondition()
        self._clipboard_text: str | None = None
        self._resume_flag = False
        self._current_pipeline: VisionPipeline | None = None
        self._current_batch_id: int | None = None
        self._batch_auto_retries: dict[int, int] = {}

    def _is_auto_browser(self) -> bool:
        return self._config.browser_mode in ("playwright", "deepseek", "auto")

    def _emit_log(self, msg: str) -> None:
        """子进程/Pipeline 状态 → GUI 信号 + 落盘（后台可监察）。"""
        text = str(msg or "").rstrip()
        if not text:
            return
        self.log_line.emit(text)
        try:
            from app.utils.paths import APP_ROOT

            log_path = Path(APP_ROOT) / "logs" / "vision_pw_status.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%H:%M:%S')} {text}\n")
        except Exception:
            pass

    def request_cancel(self) -> None:
        self._mutex.lock()
        self._cancel = True
        self._wait.wakeAll()
        self._mutex.unlock()

    def submit_clipboard(self, text: str) -> None:
        self._mutex.lock()
        self._clipboard_text = text
        self._wait.wakeAll()
        self._mutex.unlock()

    def resume_after_user(self) -> None:
        self._mutex.lock()
        self._resume_flag = True
        self._wait.wakeAll()
        self._mutex.unlock()

    def _cancelled(self) -> bool:
        self._mutex.lock()
        v = self._cancel
        self._mutex.unlock()
        return v

    def _wait_for_clipboard(self) -> str | None:
        self._mutex.lock()
        self._clipboard_text = None
        while self._clipboard_text is None and not self._cancel:
            self._wait.wait(self._mutex, 500)
        text = self._clipboard_text
        self._clipboard_text = None
        self._mutex.unlock()
        return text

    def _wait_for_resume(self) -> bool:
        self._mutex.lock()
        self._resume_flag = False
        while not self._resume_flag and not self._cancel:
            self._wait.wait(self._mutex, 500)
        ok = self._resume_flag and not self._cancel
        self._resume_flag = False
        self._mutex.unlock()
        return ok

    def run(self) -> None:
        for task in self._tasks:
            if self._cancelled():
                self.task_status.emit(task.id, TaskStatus.CANCELLED.value, "已取消")
                continue
            t0 = time.perf_counter()
            try:
                self._run_one(task)
                elapsed = time.perf_counter() - t0
                out_md = str(task.output_md or "")
                out_dir = str(task.output_dir or "")
                self.task_finished.emit(task.id, True, out_md, out_dir, "", elapsed)
            except Exception as e:  # noqa: BLE001
                elapsed = time.perf_counter() - t0
                msg = f"[vision] 失败: {e}"
                self.log_line.emit(msg)
                try:
                    get_logger().error(msg)
                except Exception:
                    pass
                self.task_finished.emit(
                    task.id,
                    False,
                    "",
                    str(task.output_dir or ""),
                    str(e),
                    elapsed,
                )
            finally:
                if self._current_pipeline:
                    self._current_pipeline.close()
                    self._current_pipeline = None

    def _run_one(self, task: ConvertTask) -> None:
        task.workflow = WorkflowChoice.VISION.value
        out = vision_task_output_dir(self._output_root, task.pdf_path)
        task.output_dir = out
        self.task_status.emit(task.id, TaskStatus.RUNNING.value, "页面渲染")
        self.pipeline_stage.emit("render")
        self.stage.emit("页面渲染")

        pipe = VisionPipeline(
            task.pdf_path,
            out,
            replace(self._config, force_rerun=bool(task.vision_force_rerun)),
            log=self._emit_log,
        )
        self._current_pipeline = pipe

        def _prog(label: str, cur: int, total: int) -> None:
            self.task_status.emit(
                task.id, TaskStatus.RUNNING.value, f"{label} {cur}/{total}"
            )

        pipe.prepare(progress=_prog, cancelled=self._cancelled)
        if self._cancelled():
            raise RuntimeError("cancelled")

        self._batch_auto_retries = {}
        pipe.resume_received_batches()

        max_auto_retry = 3

        while True:
            if self._cancelled():
                raise RuntimeError("cancelled")
            batch = pipe.next_pending_batch()
            if batch is None:
                m = pipe._ensure_manifest()
                if not m.all_batches_accepted():
                    stuck = [
                        f"#{b.id}:{b.status}" for b in m.get_batches() if b.status != "accepted"
                    ]
                    raise RuntimeError(
                        "没有可继续的批次，但仍有未完成项: "
                        + ", ".join(stuck)
                        + "。请重新开始转换（将自动重置未完成批次）。"
                    )
                break
            # 已有 raw 会在 resume 里处理；此处 pending/needs_retry
            if batch.status == BatchStatus.RECEIVED.value:
                raw_path = out / ".vision" / "batches" / f"batch_{batch.id:04d}" / "response.raw.md"
                if raw_path.exists():
                    pipe.ingest_and_validate(batch.id, raw_path.read_text(encoding="utf-8"))
                    continue

            self.pipeline_stage.emit("transcribe")
            self.task_status.emit(
                task.id,
                TaskStatus.RUNNING.value,
                f"视觉转录 {batch.start_page}–{batch.end_page}",
            )
            self._current_batch_id = batch.id

            if self._is_auto_browser():
                if batch.status == BatchStatus.NEEDS_RETRY.value:
                    tries = self._batch_auto_retries.get(batch.id, 0)
                    if tries >= max_auto_retry:
                        raise RuntimeError(
                            f"批次 PAGE {batch.start_page:04d}–{batch.end_page:04d} "
                            f"自动重试已达 {max_auto_retry} 次仍校验失败，"
                            "请查看 logs/vision_pw_status.log"
                        )
                    self._batch_auto_retries[batch.id] = tries + 1
                    self.log_line.emit(
                        f"批次 {batch.start_page}–{batch.end_page} 校验未通过，"
                        f"自动重新提交浏览器（{tries + 1}/{max_auto_retry}）…"
                    )
                    pipe.reset_batch_for_browser_retry(batch.id)
                    refreshed = {
                        b.id: b for b in pipe._ensure_manifest().get_batches()
                    }.get(batch.id)
                    if refreshed is not None:
                        batch = refreshed

                self.task_status.emit(
                    task.id, TaskStatus.RUNNING.value, "启动浏览器（子进程）…"
                )
                result = pipe.try_auto_submit(batch)
                while result and result.needs_user:
                    hint = result.message or "需要人工处理浏览器"
                    if any(k in hint for k in ("登录", "验证", "验证码")):
                        self.log_line.emit(
                            "等待人工登录/验证：请勿关闭 DeepSeek 浏览器窗口"
                        )
                    else:
                        self.log_line.emit(f"浏览器需处理：{hint}")
                    self.needs_user.emit(
                        task.id, result.message or "需要人工处理浏览器"
                    )
                    self.pipeline_stage.emit("transcribe")
                    if not self._wait_for_resume():
                        raise RuntimeError("cancelled")
                    self.task_status.emit(
                        task.id, TaskStatus.RUNNING.value, "继续自动识别…"
                    )
                    result = pipe.resume_pending_submit()
                if result and not result.needs_user:
                    still = pipe.next_pending_batch()
                    if still and still.id == batch.id:
                        err = still.error or "校验未通过"
                        self.log_line.emit(
                            f"自动批次校验失败：{err}；将自动重试浏览器"
                        )
                    continue
                continue

            # 仅「剪贴板半自动」模式才弹视觉转录对话框
            prep = pipe.prepare_batch(batch)
            self.needs_clipboard.emit(
                task.id,
                batch.id,
                batch.start_page,
                batch.end_page,
                prep.hint,
            )
            text = self._wait_for_clipboard()
            if text is None:
                raise RuntimeError("cancelled")
            if not text.strip():
                # 允许 GUI 传空时再读系统剪贴板
                text = ManualClipboardAdapter.read_clipboard()
            self.pipeline_stage.emit("validate")
            ok = pipe.ingest_and_validate(batch.id, text)
            if not ok:
                self.log_line.emit(
                    f"批次 {batch.start_page}–{batch.end_page} 校验失败，将重试（可缩小批次后重贴）"
                )
                # 保持 needs_retry，下一轮再要剪贴板
                continue

        self.pipeline_stage.emit("merge")
        self.task_status.emit(task.id, TaskStatus.RUNNING.value, "合并与格式清理")
        cleaned = pipe.merge_and_clean()
        pending = pipe.pending_figures()
        if not pending:
            from app.vision_transcribe.vision_structure_repair import (
                has_deepseek_placeholder_images,
            )

            cleaned_path = vision_dir(out) / "document.cleaned.md"
            if cleaned_path.is_file() and has_deepseek_placeholder_images(
                cleaned_path.read_text(encoding="utf-8")
            ):
                self.log_line.emit(
                    "警告：文中仍有 example.com 假图 URL，FIGURE 占位符未生成，"
                    "已跳过 Docling 裁图（请更新程序后重跑合并）"
                )
        if pending:
            self.pipeline_stage.emit("figures")
            self.task_status.emit(
                task.id,
                TaskStatus.RUNNING.value,
                f"Docling 自动裁图 0/{len(pending)}",
            )
            filled = pipe.auto_extract_figures()
            still = pipe.pending_figures()
            if still:
                self.log_line.emit(
                    f"仍有 {len(still)} 个 Figure 未匹配到 Docling 图片，"
                    "占位符将保留在 Markdown 中"
                )
            elif filled:
                self.log_line.emit(f"Figure 自动写入完成（{filled} 张）")
        final = pipe.finalize(stem=task.pdf_path.stem)
        task.output_md = final
        task.vision_force_rerun = False
        self.pipeline_stage.emit("idle")
        self.task_status.emit(task.id, TaskStatus.RUNNING.value, "完成")
        self.log_line.emit(f"高保真完成: {final}")


class VisionFigureRebuildWorker(QThread):
    """仅重合并 + Docling 裁图 + 写回（不重跑浏览器）。"""

    finished_ok = Signal(str, str)  # task_id, final_md
    failed = Signal(str, str)  # task_id, error
    log_line = Signal(str)

    def __init__(
        self,
        task_id: str,
        pdf_path: Path,
        output_dir: Path,
        *,
        config: VisionConfig | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._task_id = task_id
        self._pdf_path = Path(pdf_path)
        self._output_dir = Path(output_dir)
        self._config = config or VisionConfig()

    def run(self) -> None:
        try:
            pipe = VisionPipeline(
                self._pdf_path,
                self._output_dir,
                self._config,
                log=lambda m: self.log_line.emit(str(m)),
            )
            final = pipe.rebuild_figures_and_finalize(stem=self._pdf_path.stem)
            self.finished_ok.emit(self._task_id, str(final))
        except Exception as e:  # noqa: BLE001
            self.failed.emit(self._task_id, str(e))
