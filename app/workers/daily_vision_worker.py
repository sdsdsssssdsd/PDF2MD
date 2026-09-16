"""日常识图 Worker：Qt 纯桥。业务在 DailyVisionService。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMutex, QThread, Signal

from app.core.service.daily_vision import DailyVisionService


class DailyVisionWorker(QThread):
    finished_ok = Signal(str, str)  # markdown, error(empty if ok)
    finished_archive = Signal(str, str)  # md_path, error
    log_line = Signal(str)

    def __init__(
        self,
        image_paths: list[Path],
        *,
        archive: bool = False,
        archive_dir: Path | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._paths = list(image_paths)
        self._archive = archive
        self._archive_dir = archive_dir
        self._cancel = False
        self._mutex = QMutex()

    def request_cancel(self) -> None:
        self._mutex.lock()
        self._cancel = True
        self._mutex.unlock()

    def run(self) -> None:
        outcome = DailyVisionService().run(
            self._paths,
            archive=self._archive,
            archive_dir=self._archive_dir,
            log=lambda m: self.log_line.emit(m),
        )
        if self._archive:
            if outcome.ok:
                self.finished_archive.emit(outcome.archive_path, "")
            else:
                self.finished_archive.emit("", outcome.error)
            return
        if outcome.ok:
            self.finished_ok.emit(outcome.markdown, "")
        else:
            self.finished_ok.emit("", outcome.error)
