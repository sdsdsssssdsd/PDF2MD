"""日志对话框。"""
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QTextEdit, QVBoxLayout


class LogDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("转换日志")
        self.resize(720, 420)
        layout = QVBoxLayout(self)
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        layout.addWidget(self.text)
        row = QHBoxLayout()
        clear_btn = QPushButton("清空")
        close_btn = QPushButton("关闭")
        clear_btn.clicked.connect(self.text.clear)
        close_btn.clicked.connect(self.accept)
        row.addStretch(1)
        row.addWidget(clear_btn)
        row.addWidget(close_btn)
        layout.addLayout(row)

    def append_line(self, line: str) -> None:
        self.text.append(line)
