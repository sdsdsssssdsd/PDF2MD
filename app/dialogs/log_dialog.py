# -*- coding: utf-8 -*-
"""转换日志。"""
from __future__ import annotations

from PySide6.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from app.ui.fonts import mono_font
from app.ui.tokens import LIGHT


class _LogHighlighter(QSyntaxHighlighter):
    """仅给 ERROR / WARNING 轻微语义色。"""

    def __init__(self, parent) -> None:
        super().__init__(parent)
        try:
            from app.ui.theme import theme_manager

            mgr = theme_manager()
            t = mgr.tokens if mgr is not None else LIGHT
        except Exception:
            t = LIGHT
        self._err = QTextCharFormat()
        self._err.setForeground(QColor(t.danger))
        self._warn = QTextCharFormat()
        self._warn.setForeground(QColor(t.warning))

    def highlightBlock(self, text: str) -> None:  # noqa: N802
        up = text.upper()
        if "ERROR" in up or "FAIL" in up or "TRACEBACK" in up:
            self.setFormat(0, len(text), self._err)
        elif "WARNING" in up or "WARN" in up:
            self.setFormat(0, len(text), self._warn)


class LogDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("转换日志")
        self.resize(900, 560)
        layout = QVBoxLayout(self)
        tools = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索日志…")
        self.search.textChanged.connect(self._on_search)
        self.cb_autoscroll = QCheckBox("自动滚动")
        self.cb_autoscroll.setChecked(True)
        tools.addWidget(self.search, 1)
        tools.addWidget(self.cb_autoscroll)
        layout.addLayout(tools)

        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setFont(mono_font())
        self._hi = _LogHighlighter(self.text.document())
        layout.addWidget(self.text)
        try:
            from app.ui.theme import theme_manager

            mgr = theme_manager()
            if mgr is not None:
                mgr.theme_changed.connect(self._rehighlight)
        except Exception:
            pass

        row = QHBoxLayout()
        copy_btn = QPushButton("复制")
        clear_btn = QPushButton("清空")
        close_btn = QPushButton("关闭")
        copy_btn.clicked.connect(self._copy)
        clear_btn.clicked.connect(self.text.clear)
        close_btn.clicked.connect(self.accept)
        row.addStretch(1)
        row.addWidget(copy_btn)
        row.addWidget(clear_btn)
        row.addWidget(close_btn)
        layout.addLayout(row)

    def append_line(self, line: str) -> None:
        self.text.appendPlainText(line)
        if self.cb_autoscroll.isChecked():
            cursor = self.text.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.text.setTextCursor(cursor)

    def _on_search(self, text: str) -> None:
        if not text:
            return
        self.text.find(text)

    def _rehighlight(self, *_args) -> None:
        self._hi.setDocument(None)
        self._hi = _LogHighlighter(self.text.document())

    def _copy(self) -> None:
        self.text.selectAll()
        self.text.copy()
        cursor = self.text.textCursor()
        cursor.clearSelection()
        self.text.setTextCursor(cursor)
