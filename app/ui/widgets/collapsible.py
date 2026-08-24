# -*- coding: utf-8 -*-
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QToolButton, QVBoxLayout, QWidget


class CollapsibleSection(QFrame):
    """默认收起的高级参数区。"""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("uiCard", True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 6, 10, 8)
        outer.setSpacing(6)
        self._toggle = QToolButton()
        self._toggle.setText(f"▸  {title}")
        self._toggle.setCheckable(True)
        self._toggle.setChecked(False)
        self._toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self._toggle.setAutoRaise(True)
        self._toggle.toggled.connect(self._on_toggled)
        outer.addWidget(self._toggle)
        self.body_widget = QWidget()
        self.body = QVBoxLayout(self.body_widget)
        self.body.setContentsMargins(8, 0, 4, 4)
        self.body.setSpacing(8)
        self.body_widget.setVisible(False)
        outer.addWidget(self.body_widget)
        self._title = title

    def _on_toggled(self, opened: bool) -> None:
        self.body_widget.setVisible(opened)
        mark = "▾" if opened else "▸"
        self._toggle.setText(f"{mark}  {self._title}")
