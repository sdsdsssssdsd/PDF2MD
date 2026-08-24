# -*- coding: utf-8 -*-
"""半自动批次：提示用户操作 DeepSeek，并从剪贴板导入结果。"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.vision_transcribe.browser.manual_clipboard import ManualClipboardAdapter


class VisionClipboardDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None,
        *,
        start_page: int,
        end_page: int,
        hint: str = "",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"视觉转录 · PAGE {start_page:04d}–{end_page:04d}")
        self.resize(640, 480)
        root = QVBoxLayout(self)
        intro = QLabel(
            hint
            or (
                f"1. 点最右侧「识图模式」（快速 | 专家 | 识图）\n"
                f"2. 上传 PAGE {start_page:04d}–{end_page:04d} 的页面图\n"
                f"3. 粘贴 Prompt → 复制完整回答 → 点「从剪贴板导入」"
            )
        )
        intro.setWordWrap(True)
        root.addWidget(intro)
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("也可直接粘贴 Markdown 到此处…")
        root.addWidget(self.editor, 1)
        buttons = QDialogButtonBox()
        self.btn_clip = buttons.addButton(
            "从剪贴板导入", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.btn_use = buttons.addButton(
            "使用上方文本", QDialogButtonBox.ButtonRole.AcceptRole
        )
        cancel = buttons.addButton("取消本批", QDialogButtonBox.ButtonRole.RejectRole)
        self.btn_clip.clicked.connect(self._from_clipboard)
        self.btn_use.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        root.addWidget(buttons)
        self._text = ""

    def _from_clipboard(self) -> None:
        self._text = ManualClipboardAdapter.read_clipboard()
        if not self._text.strip():
            self._text = self.editor.toPlainText()
        self.accept()

    def result_text(self) -> str:
        if self._text.strip():
            return self._text
        return self.editor.toPlainText()
