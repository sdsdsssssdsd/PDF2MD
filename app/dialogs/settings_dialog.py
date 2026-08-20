"""设置对话框 + QSettings。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from app.utils.paths import OUTPUT_DIR
from app.workers.env_worker import EnvProbeWorker


ORG = "PDF2MD"
APP = "PDF2MD"


def settings() -> QSettings:
    return QSettings(ORG, APP)


def load_defaults() -> dict:
    s = settings()
    return {
        "engine": s.value("engine", "Docling"),
        "output_dir": s.value("output_dir", str(OUTPUT_DIR)),
        "per_folder": s.value("per_folder", True, type=bool),
        "ocr_mode": s.value("ocr_mode", "auto"),
        "parallel": int(s.value("parallel", 1)),
        "notify": s.value("notify", True, type=bool),
        "auto_open": s.value("auto_open", False, type=bool),
        "theme": s.value("theme", "跟随系统"),
        "keep_images": s.value("keep_images", True, type=bool),
        "keep_tables": s.value("keep_tables", True, type=bool),
        "keep_formulas": s.value("keep_formulas", True, type=bool),
        "keep_refs": s.value("keep_refs", True, type=bool),
        "images_scale": float(s.value("images_scale", 2.0)),
        "image_path_mode": s.value("image_path_mode", "relative"),
    }


class SettingsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.resize(520, 560)
        cfg = load_defaults()

        root = QVBoxLayout(self)

        form = QFormLayout()
        self.engine = QComboBox()
        self.engine.addItems(["Docling", "MinerU", "自动"])
        self.engine.setCurrentText(str(cfg["engine"]))
        form.addRow("默认引擎：", self.engine)

        out_row = QHBoxLayout()
        self.output = QLineEdit(str(cfg["output_dir"]))
        browse = QPushButton("选择...")
        browse.clicked.connect(self._browse)
        out_row.addWidget(self.output)
        out_row.addWidget(browse)
        form.addRow("默认导出目录：", out_row)

        self.ocr = QComboBox()
        self.ocr.addItems(["自动", "强制 OCR", "禁用 OCR"])
        ocr_map = {"auto": "自动", "force": "强制 OCR", "disable": "禁用 OCR"}
        self.ocr.setCurrentText(ocr_map.get(str(cfg["ocr_mode"]), "自动"))
        form.addRow("OCR：", self.ocr)

        self.img_quality = QComboBox()
        self.img_quality.addItems(["快速 (1x)", "标准 (2x)", "高清 (3x)"])
        scale = float(cfg.get("images_scale", 2.0))
        if scale <= 1.0:
            self.img_quality.setCurrentIndex(0)
        elif scale >= 3.0:
            self.img_quality.setCurrentIndex(2)
        else:
            self.img_quality.setCurrentIndex(1)
        form.addRow("图片质量：", self.img_quality)

        self.img_path_mode = QComboBox()
        self.img_path_mode.addItems(["相对路径", "绝对路径"])
        mode = str(cfg.get("image_path_mode", "relative"))
        self.img_path_mode.setCurrentIndex(1 if mode == "absolute" else 0)
        form.addRow("图片路径：", self.img_path_mode)

        self.parallel = QSpinBox()
        self.parallel.setRange(1, 2)
        self.parallel.setValue(int(cfg["parallel"]))
        form.addRow("同时任务数：", self.parallel)

        self.theme = QComboBox()
        self.theme.addItems(["跟随系统", "浅色", "深色"])
        self.theme.setCurrentText(str(cfg["theme"]))
        form.addRow("外观：", self.theme)

        root.addLayout(form)

        self.per_folder = QCheckBox("每篇论文建立独立文件夹")
        self.per_folder.setChecked(bool(cfg["per_folder"]))
        self.notify = QCheckBox("转换完成时 Windows 通知")
        self.notify.setChecked(bool(cfg["notify"]))
        self.auto_open = QCheckBox("自动打开导出目录")
        self.auto_open.setChecked(bool(cfg["auto_open"]))
        root.addWidget(self.per_folder)
        root.addWidget(self.notify)
        root.addWidget(self.auto_open)

        env_box = QGroupBox("环境状态")
        env_layout = QVBoxLayout(env_box)
        self.env_label = QLabel("正在检测...")
        self.env_label.setWordWrap(True)
        env_layout.addWidget(self.env_label)
        root.addWidget(env_box)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._probe = EnvProbeWorker()
        self._probe.finished_info.connect(self._show_env)
        self._probe.start()

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "选择导出目录", self.output.text())
        if d:
            self.output.setText(d)

    def _show_env(self, info: dict) -> None:
        def ok(v: str) -> str:
            return "✓" if "不可用" not in v else "❌"

        lines = [
            f"Python       {ok(info.get('python',''))} {info.get('python')}",
            f"Docling      {ok(info.get('docling',''))} {info.get('docling')}",
            f"MinerU       {ok(info.get('mineru',''))} {info.get('mineru')}",
            f"PyTorch      {ok(info.get('torch',''))} {info.get('torch')}",
            f"CUDA         {ok(info.get('cuda',''))} {info.get('cuda')}",
            f"GPU          ✓ {info.get('gpu')}",
            f"VRAM         ✓ {info.get('vram')}",
        ]
        self.env_label.setText("\n".join(lines))

    def _save(self) -> None:
        ocr_rev = {"自动": "auto", "强制 OCR": "force", "禁用 OCR": "disable"}
        s = settings()
        s.setValue("engine", self.engine.currentText())
        s.setValue("output_dir", self.output.text().strip())
        s.setValue("per_folder", self.per_folder.isChecked())
        s.setValue("ocr_mode", ocr_rev.get(self.ocr.currentText(), "auto"))
        scale_map = {0: 1.0, 1: 2.0, 2: 3.0}
        s.setValue("images_scale", scale_map.get(self.img_quality.currentIndex(), 2.0))
        s.setValue(
            "image_path_mode",
            "absolute" if self.img_path_mode.currentIndex() == 1 else "relative",
        )
        s.setValue("parallel", self.parallel.value())
        s.setValue("notify", self.notify.isChecked())
        s.setValue("auto_open", self.auto_open.isChecked())
        s.setValue("theme", self.theme.currentText())
        Path(self.output.text().strip()).mkdir(parents=True, exist_ok=True)
        self.accept()
