# -*- coding: utf-8 -*-
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget

from app.ui.widgets.pipeline_status import PipelineStatusWidget
from app.ui.widgets.status_badge import StatusBadge


class CommandBar(QFrame):
    start_clicked = Signal()
    cancel_clicked = Signal()
    clear_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("commandBar")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 6, 12, 8)
        outer.setSpacing(4)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        self.progress.setTextVisible(False)
        self.progress.setMaximumHeight(3)
        outer.addWidget(self.progress)

        row = QHBoxLayout()
        row.setSpacing(10)
        left = QVBoxLayout()
        left.setSpacing(4)
        self.current = QLabel("就绪")
        self.current.setProperty("role", "sectionTitle")
        self.pipeline = PipelineStatusWidget()
        left.addWidget(self.current)
        left.addWidget(self.pipeline)
        row.addLayout(left, 1)

        self.deepseek = StatusBadge("DeepSeek · Cold", "neutral")
        self.count = QLabel("已完成 0 / 0")
        self.count.setProperty("role", "muted")
        self.clear = QPushButton("清空列表")
        self.clear.setAutoDefault(False)
        self.clear.setDefault(False)
        self.cancel = QPushButton("取消")
        self.cancel.setProperty("variant", "danger")
        self.cancel.setEnabled(False)
        self.cancel.setAutoDefault(False)
        self.cancel.setDefault(False)
        self.start = QPushButton("开始转换")
        self.start.setProperty("variant", "primary")
        self.start.setDefault(True)
        self.start.setAutoDefault(True)
        self.start.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.cancel.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.clear.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setTabOrder(self.start, self.cancel)
        self.setTabOrder(self.cancel, self.clear)
        self.start.clicked.connect(self.start_clicked)
        self.cancel.clicked.connect(self.cancel_clicked)
        self.clear.clicked.connect(self.clear_clicked)
        row.addWidget(self.deepseek)
        row.addWidget(self.count)
        row.addWidget(self.clear)
        row.addWidget(self.cancel)
        row.addWidget(self.start)
        outer.addLayout(row)

    def set_running(self, running: bool) -> None:
        self.start.setEnabled(not running)
        self.cancel.setEnabled(running)
        self.clear.setEnabled(not running)
        self.progress.setVisible(running)

    def set_count(self, done: int, total: int) -> None:
        self.count.setText(f"已完成 {done} / {total}")
