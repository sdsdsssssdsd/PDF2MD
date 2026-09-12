"""日常识图工作区。"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.drop_widget import DropWidget


class DailyVisionWorkspace(QWidget):
    images_added = Signal(list)
    request_recognize = Signal(list, bool)  # paths, archive
    request_save_markdown = Signal(str)
    request_open_output = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._image_paths: list[Path] = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 8, 0)

        self.drop = DropWidget()
        self.drop.set_mode("images")
        self.drop.files_dropped.connect(self._on_drop)
        lay.addWidget(self.drop)

        self.lbl_images = QLabel("尚未添加图片 · 支持 Ctrl+V 粘贴")
        self.lbl_images.setProperty("role", "muted")
        lay.addWidget(self.lbl_images)

        self.result = QPlainTextEdit()
        self.result.setPlaceholderText("识别结果将显示在这里，可直接编辑后复制…")
        self.result.setMinimumHeight(200)
        lay.addWidget(self.result, 1)

        btn_row = QHBoxLayout()
        self.btn_copy = QPushButton("复制 Markdown")
        self.btn_copy.clicked.connect(self._copy_md)
        self.btn_save_md = QPushButton("保存 Markdown")
        self.btn_save_md.clicked.connect(self._save_md)
        self.btn_save = QPushButton("图文归档")
        self.btn_save.setToolTip("保存 Markdown + 裁图到输出目录")
        self.btn_save.clicked.connect(self._archive)
        self.btn_open_out = QPushButton("打开输出目录")
        self.btn_open_out.clicked.connect(self.request_open_output.emit)
        self.btn_clear = QPushButton("清空")
        self.btn_clear.clicked.connect(self.clear)
        self.btn_retry = QPushButton("重新识别")
        self.btn_retry.clicked.connect(self._retry)
        for b in (
            self.btn_copy,
            self.btn_save_md,
            self.btn_save,
            self.btn_open_out,
            self.btn_retry,
            self.btn_clear,
        ):
            btn_row.addWidget(b)
        btn_row.addStretch(1)
        lay.addLayout(btn_row)

        self.lbl_status = QLabel("")
        self.lbl_status.setProperty("role", "subtle")
        lay.addWidget(self.lbl_status)

    def _on_drop(self, paths: list[str]) -> None:
        if not paths:
            files, _ = QFileDialog.getOpenFileNames(
                self,
                "选择图片",
                "",
                "Images (*.png *.jpg *.jpeg *.webp *.gif *.bmp)",
            )
            paths = files
        self.add_image_paths([Path(p) for p in paths if p])

    def add_image_paths(self, paths: list[Path]) -> None:
        new_paths: list[Path] = []
        for path in paths:
            path = Path(path)
            if path.is_file():
                new_paths.append(path)
            elif path.is_dir():
                for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp", "*.gif", "*.bmp"):
                    new_paths.extend(path.glob(ext))
                    new_paths.extend(path.glob(ext.upper()))
        if not new_paths:
            return
        self._image_paths = new_paths
        self.lbl_images.setText(f"已选 {len(self._image_paths)} 张图片")
        self.images_added.emit([str(p) for p in self._image_paths])
        self.request_recognize.emit(self._image_paths, False)

    def paste_from_clipboard(self) -> bool:
        mime = QGuiApplication.clipboard().mimeData()
        if mime is None or not mime.hasImage():
            return False
        from PySide6.QtGui import QImage

        image = mime.imageData()
        if not isinstance(image, QImage) or image.isNull():
            img = QGuiApplication.clipboard().image()
            if img.isNull():
                return False
            image = img
        temp_dir = Path(__file__).resolve().parents[2] / "logs" / "daily_paste"
        temp_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = temp_dir / f"paste_{stamp}.png"
        if not image.save(str(path), "PNG"):
            return False
        self.add_image_paths([path])
        return True

    def _retry(self) -> None:
        if self._image_paths:
            self.request_recognize.emit(self._image_paths, False)

    def _archive(self) -> None:
        if self._image_paths:
            self.request_recognize.emit(self._image_paths, True)

    def _save_md(self) -> None:
        text = self.result.toPlainText().strip()
        if not text:
            self.set_status("没有可保存的内容")
            return
        self.request_save_markdown.emit(text)

    def _copy_md(self) -> None:
        text = self.result.toPlainText().strip()
        if text:
            QGuiApplication.clipboard().setText(text)
            self.set_status("已复制到剪贴板")

    def set_result(self, markdown: str) -> None:
        self.result.setPlainText(markdown or "")

    def set_status(self, text: str) -> None:
        self.lbl_status.setText(text or "")

    def set_busy(self, busy: bool) -> None:
        self.drop.setEnabled(not busy)
        self.btn_retry.setEnabled(not busy)
        self.btn_save.setEnabled(not busy)

    def clear(self) -> None:
        self._image_paths.clear()
        self.result.clear()
        self.lbl_images.setText("尚未添加图片 · 支持 Ctrl+V 粘贴")
        self.lbl_status.clear()

    def image_paths(self) -> list[Path]:
        return list(self._image_paths)
