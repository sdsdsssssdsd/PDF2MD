"""日常识图异步 Worker。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from app.daily_vision.exporter import export_archive
from app.daily_vision.pipeline import DailyVisionPipeline
from app.task_model import TaskStatus


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

    def run(self) -> None:
        try:
            pipe = DailyVisionPipeline(log=lambda m: self.log_line.emit(m))
            result = pipe.transcribe(self._paths)
            md = result.markdown
            if self._archive and self._archive_dir:
                md_path = export_archive(self._paths, result, self._archive_dir)
                self.finished_archive.emit(str(md_path), "")
            else:
                self.finished_ok.emit(md, "")
        except Exception as e:
            msg = str(e)
            if self._archive:
                self.finished_archive.emit("", msg)
            else:
                self.finished_ok.emit("", msg)
