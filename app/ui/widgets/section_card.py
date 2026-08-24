# -*- coding: utf-8 -*-
from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


class SectionCard(QFrame):
    def __init__(
        self,
        title: str,
        description: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("uiCard", True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 16)
        outer.setSpacing(10)
        title_label = QLabel(title)
        title_label.setProperty("role", "sectionTitle")
        outer.addWidget(title_label)
        if description:
            desc = QLabel(description)
            desc.setProperty("role", "muted")
            desc.setWordWrap(True)
            outer.addWidget(desc)
        self.body = QVBoxLayout()
        self.body.setSpacing(8)
        outer.addLayout(self.body)
