# -*- coding: utf-8 -*-
"""高保真 Figure 人工框选对话框。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.vision_transcribe.figure_store import (
    bookfigure_path,
    crop_and_save,
    load_figures_json,
    save_figures_json,
)
from app.vision_transcribe.models import FigureRecord


class _CropCanvas(QLabel):
    selection_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self._pixmap: QPixmap | None = None
        self._origin: QPoint | None = None
        self._current: QRect | None = None
        self.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

    def set_page_image(self, path: Path) -> None:
        pm = QPixmap(str(path))
        self._pixmap = pm
        self.setPixmap(pm)
        self.resize(pm.size())
        self._origin = None
        self._current = None

    def selection_rect(self) -> QRect | None:
        return self._current

    def clear_selection(self) -> None:
        self._origin = None
        self._current = None
        self.update()
        self.selection_changed.emit()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._pixmap:
            self._origin = event.position().toPoint()
            self._current = QRect(self._origin, self._origin)
            self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._origin is not None and self._pixmap:
            pos = event.position().toPoint()
            self._current = QRect(self._origin, pos).normalized()
            self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._current:
            self.selection_changed.emit()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if self._current and self._current.width() > 2:
            p = QPainter(self)
            p.setPen(QPen(QColor(0, 120, 215), 2, Qt.PenStyle.DashLine))
            p.setBrush(QColor(0, 120, 215, 40))
            p.drawRect(self._current)


class VisionFigureDialog(QDialog):
    """逐张框选 bookfigures 页图，写入 figures/ 并更新 figures.json。"""

    finished_all = Signal()

    def __init__(self, output_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.output_dir = Path(output_dir)
        self.setWindowTitle("高保真 · 图片录入")
        self.resize(960, 720)
        self._figures: list[FigureRecord] = load_figures_json(self.output_dir)
        self._queue = [i for i, f in enumerate(self._figures) if f.status not in ("done", "skipped")]
        self._qi = 0

        root = QVBoxLayout(self)
        self.lbl = QLabel()
        self.lbl.setProperty("role", "sectionTitle")
        root.addWidget(self.lbl)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(False)
        self.canvas = _CropCanvas()
        self.scroll.setWidget(self.canvas)
        root.addWidget(self.scroll, 1)

        row = QHBoxLayout()
        self.btn_skip = QPushButton("跳过")
        self.btn_reset = QPushButton("重置选区")
        self.btn_save = QPushButton("保存并下一张")
        self.btn_save.setProperty("variant", "primary")
        self.btn_skip.clicked.connect(self._skip)
        self.btn_reset.clicked.connect(self.canvas.clear_selection)
        self.btn_save.clicked.connect(self._save)
        row.addWidget(self.btn_skip)
        row.addWidget(self.btn_reset)
        row.addStretch(1)
        row.addWidget(self.btn_save)
        root.addLayout(row)

        if not self._queue:
            self.lbl.setText("没有待录入的 Figure")
            self.btn_save.setEnabled(False)
            self.btn_skip.setEnabled(False)
        else:
            self._load_current()

    def _current(self) -> FigureRecord | None:
        if self._qi >= len(self._queue):
            return None
        return self._figures[self._queue[self._qi]]

    def _load_current(self) -> None:
        rec = self._current()
        if rec is None:
            self.accept()
            self.finished_all.emit()
            return
        total = len(self._queue)
        self.lbl.setText(
            f"Figure {self._qi + 1} / {total} · Page {rec.page:04d} · {rec.marker}"
        )
        path = bookfigure_path(self.output_dir, rec.page)
        if not path.exists():
            QMessageBox.warning(self, "缺页图", f"找不到 {path}")
            return
        self.canvas.set_page_image(path)

    def _skip(self) -> None:
        rec = self._current()
        if rec is None:
            return
        rec.status = "skipped"
        save_figures_json(self.output_dir, self._figures)
        self._qi += 1
        self._load_current()

    def _save(self) -> None:
        rec = self._current()
        if rec is None:
            return
        rect = self.canvas.selection_rect()
        if rect is None or rect.width() < 4 or rect.height() < 4:
            QMessageBox.information(self, "框选", "请先在页面上拖拽框选图片区域。")
            return
        bbox = (rect.left(), rect.top(), rect.right(), rect.bottom())
        try:
            crop_and_save(self.output_dir, rec, bbox)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "保存失败", str(e))
            return
        save_figures_json(self.output_dir, self._figures)
        self._qi += 1
        self._load_current()
