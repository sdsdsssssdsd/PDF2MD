# -*- coding: utf-8 -*-
"""识别 · 公式选项：专用窗口，含 Lean 身份与只读 Safety Gate。"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from app.ui.identity import formula_profile_tone
from app.ui.widgets.notice import Notice
from app.ui.widgets.status_badge import StatusBadge


class FormulaOptionsDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None,
        *,
        cmb_formula_recovery: QComboBox,
        cb_formulas: QCheckBox,
        cb_deepseek_lp: QCheckBox,
        identity_label: QLabel,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("识别 · 公式选项")
        self.setModal(True)
        self.resize(520, 500)
        root = QVBoxLayout(self)
        root.setSpacing(12)

        head = QLabel("当前配置身份")
        head.setProperty("role", "sectionTitle")
        root.addWidget(head)
        identity_label.setWordWrap(True)
        root.addWidget(identity_label)
        self.badge = StatusBadge("Lean Balanced", "info")
        root.addWidget(self.badge)

        row_cap = QLabel("公式恢复档位")
        row_cap.setProperty("role", "muted")
        root.addWidget(row_cap)
        root.addWidget(cmb_formula_recovery)

        cb_formulas.setToolTip(
            "开启后 Docling 跑公式 enrich（很慢）。"
            "Lean Balanced 默认关闭，由 DeepSeek crop 主修公式。"
        )
        root.addWidget(cb_formulas)
        hint_en = QLabel("增加运行时间；Lean Balanced 默认关闭。")
        hint_en.setProperty("role", "subtle")
        hint_en.setWordWrap(True)
        root.addWidget(hint_en)

        cb_deepseek_lp.setToolTip(
            "仅对受控 crop 做恢复；不承诺全公式正确。"
            "需本机 GPU + DeepSeek Worker。"
        )
        root.addWidget(cb_deepseek_lp)
        hint_ds = QLabel("仅对受控 crop 做恢复；不承诺全公式正确。")
        hint_ds.setProperty("role", "subtle")
        hint_ds.setWordWrap(True)
        root.addWidget(hint_ds)

        root.addWidget(
            Notice(
                "Safety Gate",
                "ocr_context_conflict → HARD REJECT\n"
                "Equation identity 在 OCR 前绑定 · 不依据上下文发明公式",
                tone="danger",
            )
        )

        buttons = QDialogButtonBox()
        done = buttons.addButton("完成", QDialogButtonBox.ButtonRole.AcceptRole)
        done.clicked.connect(self.accept)
        root.addStretch(1)
        root.addWidget(buttons)

    def set_identity(self, name: str) -> None:
        suffix = "　Recommended" if name == "Lean Balanced" else ""
        self.badge.set_status(name + suffix, formula_profile_tone(name))
