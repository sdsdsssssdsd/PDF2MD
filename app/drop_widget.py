"""PDF 拖放区域。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


class DropWidget(QFrame):
    files_dropped = Signal(list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setObjectName("dropZone")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._compact = False

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title = QLabel("拖入学术 PDF")
        self.title.setProperty("role", "sectionTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label = QLabel("支持多文件 / 文件夹 · 或点击选择")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setProperty("role", "muted")
        layout.addWidget(self.title)
        layout.addWidget(self.label)
        self.set_compact(False)

    def set_compact(self, compact: bool) -> None:
        self._compact = compact
        if compact:
            self.setMinimumHeight(56)
            self.setMaximumHeight(64)
            self.title.setText("继续添加 PDF")
            self.label.hide()
        else:
            self.setMaximumHeight(16777215)
            self.setMinimumHeight(148)
            self.title.setText("拖入学术 PDF")
            self.label.setText("支持多文件 / 文件夹 · 或点击选择")
            self.label.show()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.files_dropped.emit([])  # 空列表 = 打开文件对话框
        super().mousePressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls() and self._pdf_urls(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        paths = self._pdf_urls(event)
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
        else:
            event.ignore()

    @staticmethod
    def _pdf_urls(event) -> list[str]:
        out: list[str] = []
        for url in event.mimeData().urls():
            local = url.toLocalFile()
            if not local:
                continue
            p = Path(local)
            if p.is_file() and p.suffix.lower() == ".pdf":
                out.append(str(p))
            elif p.is_dir():
                for f in p.rglob("*.pdf"):
                    out.append(str(f))
                for f in p.rglob("*.PDF"):
                    if str(f) not in out:
                        out.append(str(f))
        return out
