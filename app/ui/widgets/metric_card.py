# -*- coding: utf-8 -*-
from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


class MetricCard(QFrame):
    def __init__(
        self,
        caption: str,
        value: str = "—",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("uiCard", True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(2)
        self._value = QLabel(value)
        self._value.setProperty("role", "title")
        cap = QLabel(caption)
        cap.setProperty("role", "muted")
        lay.addWidget(self._value)
        lay.addWidget(cap)

    def set_value(self, value: str) -> None:
        self._value.setText(value)
