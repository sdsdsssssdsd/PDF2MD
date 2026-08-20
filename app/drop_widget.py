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
        self.setMinimumHeight(160)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label = QLabel(
            "将 PDF 拖到这里\n\n或点击这里选择 PDF 文件\n\n支持一次拖入多个 PDF"
        )
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("color: #444; font-size: 15px;")
        layout.addWidget(self.label)

        self.setStyleSheet(
            """
            QFrame#dropZone {
                border: 2px dashed #8a8a8a;
                border-radius: 10px;
                background: #f7f7f7;
            }
            QFrame#dropZone:hover {
                border-color: #2b6cb0;
                background: #eef5fc;
            }
            """
        )

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
