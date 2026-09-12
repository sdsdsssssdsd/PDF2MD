"""格式修正后台 Worker。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from app.format_repair.file_io import FileSnapshot
from app.format_repair.models import RepairConfig
from app.format_repair.pipeline import repair_text


class FormatRepairWorker(QThread):
    finished_result = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        text: str,
        config: RepairConfig,
        *,
        source_path: Path | None = None,
        snapshot: FileSnapshot | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._text = text
        self._config = config
        self._source_path = source_path
        self._snapshot = snapshot

    def run(self) -> None:
        try:
            result = repair_text(
                self._text,
                config=self._config,
                source_path=self._source_path,
                snapshot=self._snapshot,
            )
            self.finished_result.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))

