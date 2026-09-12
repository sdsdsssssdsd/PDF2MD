"""四模式 2×2 选择器。"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGridLayout, QPushButton, QVBoxLayout, QWidget


MODES: list[tuple[str, str, str]] = [
    ("daily", "日常识图", "截图 → Markdown"),
    ("vision_api", "API 高精度", "PDF · Vision API"),
    ("structured", "快速自动", "Docling / MinerU"),
    ("vision_web", "网页高保真", "Playwright 备用"),
    ("format_repair", "格式修正", "Markdown / Text"),
]

DEFAULT_MODE = "daily"


class WorkflowPicker(QWidget):
    value_changed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._buttons: dict[str, QPushButton] = {}
        self._value = DEFAULT_MODE

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)
        grid = QGridLayout()
        grid.setSpacing(6)
        for i, (mode_id, title, subtitle) in enumerate(MODES):
            btn = QPushButton(f"{title}\n{subtitle}")
            btn.setCheckable(True)
            btn.setProperty("workflowMode", mode_id)
            btn.clicked.connect(lambda checked=False, m=mode_id: self.set_value(m))
            self._buttons[mode_id] = btn
            if mode_id == "format_repair":
                grid.addWidget(btn, i // 2, 0, 1, 2)
            else:
                grid.addWidget(btn, i // 2, i % 2)
        root.addLayout(grid)
        self.set_value(DEFAULT_MODE, emit=False)

    def value(self) -> str:
        return self._value

    def set_value(self, mode_id: str, *, emit: bool = True) -> None:
        mode_id = mode_id if mode_id in self._buttons else DEFAULT_MODE
        if mode_id == self._value and self._buttons[mode_id].isChecked():
            return
        self._value = mode_id
        for mid, btn in self._buttons.items():
            btn.setChecked(mid == mode_id)
        if emit:
            self.value_changed.emit(mode_id)
