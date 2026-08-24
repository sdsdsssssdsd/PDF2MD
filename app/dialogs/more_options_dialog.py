# -*- coding: utf-8 -*-
"""主界面「…」更多选项弹窗：主行只留常用项，次要选项收入对话框。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui.widgets.notice import Notice


class MoreOptionsDialog(QDialog):
    """承载一批次要控件的模态弹窗；即时状态，无 rollback。"""

    def __init__(
        self,
        parent: QWidget | None,
        *,
        title: str,
        hint: str = "",
        widgets: list[QWidget] | None = None,
        groups: list[tuple[str, list[QWidget]]] | None = None,
        banner_title: str = "",
        banner_body: str = "",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(480, 360)
        root = QVBoxLayout(self)
        root.setSpacing(12)
        if banner_title:
            root.addWidget(Notice(banner_title, banner_body, tone="info"))
        elif hint:
            lbl = QLabel(hint)
            lbl.setWordWrap(True)
            lbl.setProperty("role", "muted")
            root.addWidget(lbl)
        if groups:
            for name, items in groups:
                box = QGroupBox(name)
                bl = QVBoxLayout(box)
                for w in items:
                    bl.addWidget(w)
                root.addWidget(box)
        else:
            for w in widgets or []:
                root.addWidget(w)
        root.addStretch(1)
        buttons = QDialogButtonBox()
        done = buttons.addButton("完成", QDialogButtonBox.ButtonRole.AcceptRole)
        done.clicked.connect(self.accept)
        root.addWidget(buttons)


def make_ellipsis_button(
    parent: QWidget,
    dialog: QDialog,
    *,
    tooltip: str = "更多选项",
) -> QPushButton:
    """主行右侧「…」按钮，点击打开次要选项对话框。"""
    from app.ui.icons import icon

    btn = QPushButton("…", parent)
    btn.setIcon(icon("more"))
    btn.setFixedWidth(36)
    btn.setToolTip(tooltip)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.clicked.connect(dialog.exec)
    return btn


def extras_summary(checkboxes: list[QCheckBox]) -> str:
    """已开启的次要项摘要，供主行旁提示。"""
    on = [c.text() for c in checkboxes if c.isChecked() and c.isEnabled()]
    if not on:
        return "无额外项"
    if len(on) <= 2:
        return "已开：" + "、".join(on)
    return f"已开 {len(on)} 项"
