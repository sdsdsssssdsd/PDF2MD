"""格式修正 Worker：Qt 纯桥。业务在 RepairService。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMutex, QThread, Signal

from app.core.service.repair import RepairService
from app.format_repair.file_io import FileSnapshot
from app.format_repair.models import RepairConfig


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
        self._cancel = False
        self._mutex = QMutex()

    def request_cancel(self) -> None:
        self._mutex.lock()
        self._cancel = True
        self._mutex.unlock()

    def run(self) -> None:
        try:
            result, _artifact = RepairService().run(
                self._text,
                self._config,
                source_path=self._source_path,
                snapshot=self._snapshot,
            )
            self.finished_result.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))
