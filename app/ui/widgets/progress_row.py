"""确定进度行：进度条 + 百分比 + 阶段文本（含耗时）。

日常识图 / 格式修正共用——条只按真实完成度推进，不做不确定动画。
"""
from __future__ import annotations

from PySide6.QtCore import QElapsedTimer, QTimer, Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget


class ProgressRow(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(8)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        self.bar.setMaximumHeight(3)
        self.percent_label = QLabel("")
        self.percent_label.setProperty("role", "muted")
        self.percent_label.setMinimumWidth(44)
        self.percent_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        top.addWidget(self.bar, 1)
        top.addWidget(self.percent_label)
        lay.addLayout(top)

        self.status_label = QLabel("")
        self.status_label.setProperty("role", "subtle")
        lay.addWidget(self.status_label)

        self._busy = False
        self._status_base = ""
        self._elapsed = QElapsedTimer()
        self._ticker = QTimer(self)
        self._ticker.setInterval(250)
        self._ticker.timeout.connect(self._render)
        self.setVisible(False)

    def set_progress(self, percent: int | None, text: str = "") -> None:
        """percent 为 0–100 的真实完成度（None = 数值不变，只更新文本）。"""
        if percent is not None:
            value = max(0, min(100, int(percent)))
            self.bar.setValue(value)
            self.percent_label.setText(f"{value}%")
        if text:
            self._status_base = text
        self._render()

    def set_status(self, text: str) -> None:
        self._status_base = text or ""
        self._render()

    def set_busy(self, busy: bool) -> None:
        self._busy = bool(busy)
        if busy:
            self.bar.setValue(0)
            self.percent_label.setText("0%")
            self.setVisible(True)
            self._elapsed.start()
            self._ticker.start()
        else:
            self._ticker.stop()
            self.setVisible(False)
        self._render()

    def is_busy(self) -> bool:
        return self._busy

    def status_text(self) -> str:
        return self.status_label.text()

    def _render(self) -> None:
        text = self._status_base
        if self._busy and self._elapsed.isValid():
            spent = f"已用 {self._format_elapsed()}"
            text = f"{text} · {spent}" if text else spent
        self.status_label.setText(text)

    def _format_elapsed(self) -> str:
        total = max(0.0, self._elapsed.elapsed() / 1000.0)
        if total < 60:
            return f"{total:.0f}s"
        return f"{int(total // 60)}m{int(total % 60):02d}s"
