# -*- coding: utf-8 -*-
"""高保真模式：Playwright / 视觉转录实时状态面板。"""
from __future__ import annotations

import re
from datetime import datetime

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui.fonts import mono_font
from app.ui.widgets.status_badge import StatusBadge

_PW_STEP_RE = re.compile(r"\[PW\]\s*(.+)")
_UI_STEP_RE = re.compile(r"\[UI L\d\]\s*(.+)")
_VISION_RE = re.compile(r"\[vision\]\s*(.+)", re.I)
_RECORD_RE = re.compile(r"\[录制\]\s*(.+)")


class VisionStatusPanel(QWidget):
    """嵌入高保真侧栏：当前步骤 + 滚动日志（专看 PW 在干什么）。"""

    MAX_LINES = 600

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        head = QHBoxLayout()
        self.badge = StatusBadge("空闲", "neutral")
        self.lbl_step = QLabel("等待开始转换")
        self.lbl_step.setWordWrap(True)
        self.lbl_step.setProperty("role", "muted")
        head.addWidget(self.badge)
        head.addWidget(self.lbl_step, 1)
        root.addLayout(head)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(mono_font())
        self.log.setMinimumHeight(220)
        self.log.setMaximumHeight(320)
        self.log.setPlaceholderText(
            "高保真全流程状态会显示在这里（生成 / 继续生成 / 滚底 / 复制 / 剪贴板）…"
        )
        root.addWidget(self.log)

        row = QHBoxLayout()
        self.btn_clear = QPushButton("清空")
        self.btn_clear.clicked.connect(self.clear)
        row.addStretch(1)
        row.addWidget(self.btn_clear)
        root.addLayout(row)

        self._active = False

    def set_active(self, active: bool) -> None:
        self._active = active
        if not active:
            self.badge.set_status("空闲", "neutral")
            self.lbl_step.setText("等待开始转换")

    def clear(self) -> None:
        self.log.clear()

    def set_pipeline_stage(self, stage: str) -> None:
        labels = {
            "render": "页面渲染",
            "transcribe": "视觉转录",
            "validate": "批次校验",
            "merge": "合并清理",
            "figures": "Docling 裁图",
            "idle": "完成",
        }
        text = labels.get(stage, stage or "—")
        self.lbl_step.setText(text)
        if stage == "idle":
            self.badge.set_status("完成", "success")
        elif stage:
            self.badge.set_status("运行中", "info")

    def set_task_message(self, message: str) -> None:
        if message:
            self.lbl_step.setText(message)

    def append_line(self, line: str) -> None:
        if not line:
            return
        # 调用方已决定写入；运行中或显式 append 一律显示（不再二次过滤丢行）
        self._active = True

        step = None
        for rx in (_PW_STEP_RE, _UI_STEP_RE, _VISION_RE, _RECORD_RE):
            m = rx.search(line)
            if m:
                step = m.group(1).strip()
                break
        # 无前缀时也尽量把整行提为顶栏（便于看到「自动提交 batch…」等）
        if not step and len(line) <= 80:
            step = line.strip()

        if step:
            self.lbl_step.setText(step)
            if any(k in step for k in ("复制", "剪贴板", "操作栏")):
                self.badge.set_status("复制", "info")
            elif any(k in step for k in ("生成中", "继续生成", "收尾", "等待")):
                self.badge.set_status("生成", "info")
            elif "步骤" in step:
                self.badge.set_status("PW", "info")
            elif "失败" in step or "未找到" in step or "超时" in step:
                self.badge.set_status("异常", "danger")
            else:
                self.badge.set_status("运行中", "info")

        if "失败" in line or "ERROR" in line.upper() or "Traceback" in line:
            self.badge.set_status("异常", "danger")
        elif "等待人工" in line or "需要登录" in line:
            self.badge.set_status("需人工", "warning")
        elif "复制成功" in line or "已获取回答" in line:
            self.badge.set_status("完成", "success")

        ts = datetime.now().strftime("%H:%M:%S")
        self.log.appendPlainText(f"[{ts}] {line}")
        doc = self.log.document()
        if doc.blockCount() > self.MAX_LINES:
            cursor = self.log.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            cursor.movePosition(
                cursor.MoveOperation.Down,
                cursor.MoveMode.KeepAnchor,
                doc.blockCount() - self.MAX_LINES,
            )
            cursor.removeSelectedText()
        sb = self.log.verticalScrollBar()
        sb.setValue(sb.maximum())
