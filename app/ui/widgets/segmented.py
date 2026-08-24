# -*- coding: utf-8 -*-
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QPushButton, QWidget


class SegmentedControl(QWidget):
    value_changed = Signal(str)

    def __init__(
        self,
        items: list[tuple[str, str]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._buttons: dict[str, QPushButton] = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        last = len(items) - 1
        for i, (label, value) in enumerate(items):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setProperty("segment", True)
            if i == 0:
                button.setProperty("segmentPosition", "first")
            elif i == last:
                button.setProperty("segmentPosition", "last")
            else:
                button.setProperty("segmentPosition", "middle")
            button.clicked.connect(
                lambda checked=False, v=value: self.value_changed.emit(v) if checked else None
            )
            self._group.addButton(button)
            self._buttons[value] = button
            lay.addWidget(button, 1)
        if items:
            self._buttons[items[0][1]].setChecked(True)

    def value(self) -> str:
        for value, btn in self._buttons.items():
            if btn.isChecked():
                return value
        return next(iter(self._buttons), "")

    def set_value(self, value: str) -> None:
        btn = self._buttons.get(value)
        if btn is not None:
            btn.setChecked(True)
