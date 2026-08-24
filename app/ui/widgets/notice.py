# -*- coding: utf-8 -*-
from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


class Notice(QFrame):
    def __init__(
        self,
        title: str,
        body: str = "",
        tone: str = "info",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("notice", True)
        self.setProperty("noticeTone", tone)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(3)
        title_label = QLabel(title)
        title_label.setProperty("role", "sectionTitle")
        lay.addWidget(title_label)
        if body:
            body_label = QLabel(body)
            body_label.setWordWrap(True)
            body_label.setProperty("role", "muted")
            lay.addWidget(body_label)
        self._title = title_label
        self._body = body_label if body else None

    def set_text(self, title: str, body: str = "") -> None:
        self._title.setText(title)
        if self._body is not None:
            self._body.setText(body)
