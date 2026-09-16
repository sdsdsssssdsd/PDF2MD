"""高保真视觉转换 Worker：Qt 纯桥。业务在 VisionService。"""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QMutex, QThread, Signal, QWaitCondition

from app.core.service.vision import VisionHooks, VisionService
from app.task_model import ConvertTask, TaskStatus
from app.utils.logger import get_logger
from app.vision_transcribe.config import VisionConfig


class VisionConversionWorker(QThread):
    task_status = Signal(str, str, str)  # task_id, status, message
    task_finished = Signal(str, bool, str, str, str, float)
    log_line = Signal(str)
    stage = Signal(str)
    pipeline_stage = Signal(str)  # render|transcribe|validate|merge|figures|idle
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
        self._service: VisionService | None = None

    def _is_auto_browser(self) -> bool:
        backend = self._config.effective_backend()
        return backend in ("playwright", "deepseek", "auto", "api")

    def _is_api_mode(self) -> bool:
        return self._config.effective_backend() == "api"

    def request_cancel(self) -> None:
        self._mutex.lock()
        self._cancel = True
        self._wait.wakeAll()
        self._mutex.unlock()
        if self._service is not None:
            self._service.request_cancel()

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

    def _make_hooks(self) -> VisionHooks:
        return VisionHooks(
            cancelled=self._cancelled,
            wait_clipboard=self._wait_for_clipboard,
            wait_resume=self._wait_for_resume,
            on_status=lambda tid, st, msg: self.task_status.emit(tid, st, msg),
            on_stage=self.stage.emit,
            on_pipeline_stage=self.pipeline_stage.emit,
            on_log=self.log_line.emit,
            on_needs_clipboard=lambda tid, bid, start, end, hint: self.needs_clipboard.emit(
                tid, bid, start, end, hint
            ),
            on_needs_user=self.needs_user.emit,
            on_needs_figures=self.needs_figures.emit,
        )

    def run(self) -> None:
        service = VisionService(
            self._config,
            self._output_root,
            self._per_folder,
            hooks=self._make_hooks(),
        )
        self._service = service
        if self._cancelled():
            service.request_cancel()
        try:
            for task in self._tasks:
                if self._cancelled():
                    self.task_status.emit(task.id, TaskStatus.CANCELLED.value, "已取消")
                    continue
                t0 = time.perf_counter()
                try:
                    service.run_task(task)
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
                    service.close()
        finally:
            self._service = None


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
        self._service: VisionService | None = None
        self._cancel = False
        self._mutex = QMutex()

    def request_cancel(self) -> None:
        self._mutex.lock()
        self._cancel = True
        self._mutex.unlock()
        if self._service is not None:
            self._service.request_cancel()

    def run(self) -> None:
        try:
            service = VisionService(
                self._config,
                self._output_dir,
                True,
                hooks=VisionHooks(on_log=lambda m: self.log_line.emit(str(m))),
            )
            self._service = service
            final = service.rebuild_figures(
                self._pdf_path, self._output_dir, stem=self._pdf_path.stem
            )
            self.finished_ok.emit(self._task_id, str(final))
        except Exception as e:  # noqa: BLE001
            self.failed.emit(self._task_id, str(e))
        finally:
            self._service = None
