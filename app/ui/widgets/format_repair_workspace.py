"""格式修正模式：整篇交给 DeepSeek。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.format_repair.file_io import FileSnapshot, read_text_file
from app.format_repair.models import FormatRepairResult, RepairConfig


class FormatRepairWorkspace(QWidget):
    repair_requested = Signal(str, bool)
    import_requested = Signal(Path)
    save_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._source_path: Path | None = None
        self._snapshot = FileSnapshot()
        self._last_result: FormatRepairResult | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 8, 0)
        lay.setSpacing(8)

        self.input = QPlainTextEdit()
        self.input.setPlaceholderText("粘贴已有 Markdown，或导入 .md / .txt。整篇交给 DeepSeek 修格式。")
        self.input.setMinimumHeight(160)
        lay.addWidget(self.input, 1)

        mid = QHBoxLayout()
        self.btn_import = QPushButton("导入文件")
        self.btn_paste = QPushButton("粘贴")
        self.btn_repair = QPushButton("修正格式")
        self.btn_repair.setToolTip("调用 DeepSeek API，返回完整修正版 Markdown")
        for b in (self.btn_import, self.btn_paste, self.btn_repair):
            mid.addWidget(b)
        mid.addStretch(1)
        lay.addLayout(mid)

        self.output = QPlainTextEdit()
        self.output.setPlaceholderText("DeepSeek 修正结果")
        self.output.setReadOnly(True)
        self.output.setMinimumHeight(160)
        lay.addWidget(self.output, 1)

        bottom = QHBoxLayout()
        self.btn_copy = QPushButton("复制结果")
        self.btn_save = QPushButton("保存修复版")
        self.btn_clear = QPushButton("清空")
        for b in (self.btn_copy, self.btn_save, self.btn_clear):
            bottom.addWidget(b)
        bottom.addStretch(1)
        lay.addLayout(bottom)

        self.lbl_status = QLabel("整篇交给 DeepSeek · 行内 $...$ · 行间 $$ · 不新增 ---")
        self.lbl_status.setProperty("role", "subtle")
        lay.addWidget(self.lbl_status)

        self.btn_import.clicked.connect(self._import_file)
        self.btn_paste.clicked.connect(self._paste_clipboard)
        self.btn_repair.clicked.connect(self._repair)
        self.btn_copy.clicked.connect(self._copy)
        self.btn_save.clicked.connect(self.save_requested.emit)
        self.btn_clear.clicked.connect(self.clear)

    def _config(self) -> RepairConfig:
        return RepairConfig()

    def _import_file(self) -> None:
        file, _ = QFileDialog.getOpenFileName(
            self,
            "导入 Markdown / Text",
            "",
            "Markdown/Text (*.md *.markdown *.txt)",
        )
        if not file:
            return
        path = Path(file)
        try:
            text, snapshot = read_text_file(path)
        except Exception as exc:
            self.set_status(f"导入失败：{exc}")
            return
        self._source_path = path
        self._snapshot = snapshot
        self.input.setPlainText(text)
        self.import_requested.emit(path)

    def _paste_clipboard(self) -> None:
        text = QGuiApplication.clipboard().text()
        if text:
            self.input.setPlainText(text)

    def _repair(self) -> None:
        text = self.input.toPlainText()
        if not text.strip():
            self.set_status("没有可修正的内容")
            return
        self.repair_requested.emit(text, True)

    def _copy(self) -> None:
        text = self.output.toPlainText()
        if text:
            QGuiApplication.clipboard().setText(text)
            self.set_status("已复制到剪贴板")

    def set_result(self, result: FormatRepairResult) -> None:
        self._last_result = result
        self.output.setPlainText(result.output_text or "")
        if result.ok:
            saved = result.report.get("saved_path")
            chunks = result.report.get("chunks", 1)
            status = f"DeepSeek 已修正 · {chunks} 段"
            if saved:
                status += f" · 已保存 {Path(saved).name}"
            self.set_status(status)
        else:
            self.set_status("修复失败：" + "；".join(result.errors))

    def set_busy(self, busy: bool) -> None:
        self.btn_repair.setEnabled(not busy)
        self.btn_import.setEnabled(not busy)
        self.btn_paste.setEnabled(not busy)

    def set_status(self, text: str) -> None:
        self.lbl_status.setText(text or "")

    def source_snapshot(self) -> tuple[Path | None, FileSnapshot]:
        return self._source_path, self._snapshot

    def clear(self) -> None:
        self._source_path = None
        self._snapshot = FileSnapshot()
        self._last_result = None
        self.input.clear()
        self.output.clear()
        self.lbl_status.setText("整篇交给 DeepSeek · 行内 $...$ · 行间 $$ · 不新增 ---")
