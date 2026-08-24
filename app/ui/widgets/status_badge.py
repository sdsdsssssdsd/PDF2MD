# -*- coding: utf-8 -*-
from __future__ import annotations

from PySide6.QtWidgets import QLabel, QWidget


class StatusBadge(QLabel):
    def __init__(
        self,
        text: str = "",
        tone: str = "neutral",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self.setProperty("statusBadge", True)
        self.set_tone(tone)

    def set_tone(self, tone: str) -> None:
        self.setProperty("tone", tone)
        sty = self.style()
        if sty is not None:
            sty.unpolish(self)
            sty.polish(self)

    def set_status(self, text: str, tone: str) -> None:
        self.setText(text)
        self.set_tone(tone)
