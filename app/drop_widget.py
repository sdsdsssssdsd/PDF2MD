"""PDF / 图片拖放区域。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


class DropWidget(QFrame):
    files_dropped = Signal(list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setObjectName("dropZone")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._compact = False
        self._mode = "pdf"

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

    def set_mode(self, mode: str) -> None:
        self._mode = "images" if mode == "images" else "pdf"
        if not self._compact:
            if self._mode == "images":
                self.title.setText("拖入图片或 Ctrl+V")
                self.label.setText("PNG / JPG / WebP · 多文件 / 文件夹 · 或点击选择")
            else:
                self.title.setText("拖入学术 PDF")
                self.label.setText("支持多文件 / 文件夹 · 或点击选择")

    def set_compact(self, compact: bool) -> None:
        self._compact = compact
        if compact:
            self.setMinimumHeight(56)
            self.setMaximumHeight(64)
            if self._mode == "images":
                self.title.setText("继续添加图片")
            else:
                self.title.setText("继续添加 PDF")
            self.label.hide()
        else:
            self.setMaximumHeight(16777215)
            self.setMinimumHeight(148)
            self.set_mode(self._mode)
            self.label.show()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.files_dropped.emit([])  # 空列表 = 打开文件对话框
        super().mousePressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls() and self._collect_urls(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        paths = self._collect_urls(event)
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
        else:
            event.ignore()

    def _collect_urls(self, event) -> list[str]:
        if self._mode == "images":
            return self._image_urls(event)
        return self._pdf_urls(event)

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

    @staticmethod
    def _image_urls(event) -> list[str]:
        out: list[str] = []
        for url in event.mimeData().urls():
            local = url.toLocalFile()
            if not local:
                continue
            p = Path(local)
            if p.is_file() and p.suffix.lower() in _IMAGE_EXTS:
                out.append(str(p))
            elif p.is_dir():
                for f in p.rglob("*"):
                    if f.is_file() and f.suffix.lower() in _IMAGE_EXTS:
                        s = str(f)
                        if s not in out:
                            out.append(s)
        return out
