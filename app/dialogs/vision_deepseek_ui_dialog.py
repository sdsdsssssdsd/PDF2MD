# -*- coding: utf-8 -*-
"""DeepSeek 网页 UI：截图模板 + 坐标校准设置。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.utils.paths import APP_ROOT, PYTHON_EXE
from app.vision_transcribe.browser.deepseek_ui import (
    DEFAULT_TEMPLATES_DIR,
    DEFAULT_UI_CONFIG,
    load_ui_config,
    save_ui_config,
)


def _subprocess_env() -> dict[str, str]:
    import os

    env = dict(os.environ)
    env["PYTHONPATH"] = str(APP_ROOT) + (
        (";" + env["PYTHONPATH"]) if env.get("PYTHONPATH") else ""
    )
    env["PYTHONUNBUFFERED"] = "1"
    return env


class VisionDeepSeekUiDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("DeepSeek 网页 UI")
        self.setModal(True)
        self.resize(480, 320)
        self._cfg = load_ui_config()

        root = QVBoxLayout(self)
        hint = QLabel(
            "三层定位（a2-2）：录制演示 → DOM → 截图模板 → 人工\n"
            "「录制演示」：在真实浏览器点一遍，保存定位；运行时图片仍按 batch 索引上传。\n"
            f"配置：{DEFAULT_UI_CONFIG}"
        )
        hint.setWordWrap(True)
        hint.setProperty("role", "muted")
        root.addWidget(hint)

        form = QFormLayout()
        self.cmb_strategy = QComboBox()
        for label, val in (
            ("自动（录制 → DOM → 截图 → 人工）", "auto"),
            ("仅录制演示", "recorded"),
            ("仅 DOM", "dom"),
            ("仅截图模板", "template"),
            ("仅固定坐标（调试）", "coord"),
        ):
            self.cmb_strategy.addItem(label, val)
        cur = str(self._cfg.get("click_strategy", "auto"))
        idx = max(0, self.cmb_strategy.findData(cur))
        self.cmb_strategy.setCurrentIndex(idx)

        self.spin_threshold = QDoubleSpinBox()
        self.spin_threshold.setRange(0.5, 0.99)
        self.spin_threshold.setSingleStep(0.02)
        self.spin_threshold.setValue(float(self._cfg.get("match_threshold", 0.72)))
        form.addRow("点击策略", self.cmb_strategy)
        form.addRow("模板匹配阈值", self.spin_threshold)
        root.addLayout(form)

        row = QHBoxLayout()
        btn_rec = QPushButton("录制操作演示…")
        btn_rec.clicked.connect(self._run_record)
        btn_cal = QPushButton("从截图校准坐标…")
        btn_cal.clicked.connect(self._run_calibrate)
        btn_send = QPushButton("校准发送箭头模板…")
        btn_send.clicked.connect(self._run_calibrate_send)
        btn_tpl = QPushButton("打开模板目录")
        btn_tpl.clicked.connect(self._open_templates)
        btn_img = QPushButton("选择参考截图…")
        btn_img.clicked.connect(self._pick_ref_image)
        row.addWidget(btn_rec)
        row.addWidget(btn_cal)
        row.addWidget(btn_send)
        row.addWidget(btn_tpl)
        row.addWidget(btn_img)
        root.addLayout(row)

        wf = self._cfg.get("recorded_workflow") or {}
        steps = wf.get("steps") or []
        if wf.get("enabled") and steps:
            self._lbl_recorded = QLabel(
                f"已录制 {len(steps)} 步（{wf.get('recorded_at', '')[:19]}）"
            )
            self._lbl_recorded.setProperty("role", "muted")
            root.addWidget(self._lbl_recorded)

        buttons = QDialogButtonBox()
        buttons.addButton("保存", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton("取消", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _save(self) -> None:
        self._cfg["click_strategy"] = self.cmb_strategy.currentData()
        self._cfg["match_threshold"] = float(self.spin_threshold.value())
        save_ui_config(self._cfg)
        self.accept()

    def _run_record(self) -> None:
        script = APP_ROOT / "scripts" / "record_deepseek_dom.py"
        if not script.exists():
            QMessageBox.warning(self, "录制", f"找不到 {script}")
            return
        QMessageBox.information(
            self,
            "录制操作演示",
            "将打开 DeepSeek 浏览器。\n\n"
            "请按终端提示依次点击：\n"
            "必填：新对话 → 识图模式 → 输入框\n"
            "可选：输入 test 后点蓝色发送箭头（30 秒内；跳过则用 send.png 图识别）\n\n"
            "跑转换时自动：键入 Prompt → 上传图 → 图识别点发送。",
        )
        subprocess.Popen(
            [str(PYTHON_EXE), str(script)],
            cwd=str(APP_ROOT),
            env=_subprocess_env(),
            creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0,
        )

    def _run_calibrate_send(self) -> None:
        script = APP_ROOT / "scripts" / "calibrate_deepseek_send.py"
        if not script.exists():
            QMessageBox.warning(self, "校准", f"找不到 {script}")
            return
        subprocess.Popen(
            [str(PYTHON_EXE), str(script)],
            cwd=str(APP_ROOT),
            creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0,
        )
        QMessageBox.information(
            self,
            "校准发送箭头",
            "已打开校准窗口。\n在 DeepSeek 截图上拖拽框选右下角蓝色圆形发送箭头。\n"
            "保存为 data/deepseek_templates/send.png",
        )

    def _run_calibrate(self) -> None:
        script = APP_ROOT / "scripts" / "calibrate_deepseek_ui.py"
        if not script.exists():
            QMessageBox.warning(self, "校准", f"找不到 {script}")
            return
        subprocess.Popen(
            [str(PYTHON_EXE), str(script)],
            cwd=str(APP_ROOT),
            creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0,
        )
        QMessageBox.information(
            self,
            "校准",
            "已打开校准窗口。\n在参考截图上依次点击：\n"
            "识图模式（最右）→ 开启新对话 → 回形针（可 Esc 跳过）",
        )

    def _open_templates(self) -> None:
        DEFAULT_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
        import os

        os.startfile(str(DEFAULT_TEMPLATES_DIR))

    def _pick_ref_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "参考截图", str(APP_ROOT / "浏览器页面"), "Images (*.png *.jpg)"
        )
        if not path:
            return
        subprocess.Popen(
            [str(PYTHON_EXE), str(APP_ROOT / "scripts" / "calibrate_deepseek_ui.py"), "--image", path],
            cwd=str(APP_ROOT),
            creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0,
        )
