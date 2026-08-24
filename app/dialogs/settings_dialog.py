"""设置对话框 + QSettings。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.ui.widgets.section_card import SectionCard
from app.ui.widgets.status_badge import StatusBadge
from app.utils.paths import OUTPUT_DIR
from app.workers.env_worker import EnvProbeWorker


ORG = "PDF2MD"
APP = "PDF2MD"

_NAV = ("常规", "转换", "输出", "外观", "环境")


def settings() -> QSettings:
    return QSettings(ORG, APP)


def deepseek_ocr2_load_enabled() -> bool:
    """是否加载 DeepSeek-OCR-2（公式恢复 Worker / 模型暖机）。"""
    return bool(settings().value("deepseek_limited_production", False, type=bool))


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
        "keep_images": True,  # 始终导出图片
        "export_md": s.value("export_md", True, type=bool),
        "export_raw_md": s.value("export_raw_md", False, type=bool),
        "export_repair_json": s.value("export_repair_json", False, type=bool),
        "export_conversion_log": s.value("export_conversion_log", False, type=bool),
        "export_manifest": s.value("export_manifest", False, type=bool),
        "export_formula_qa": s.value("export_formula_qa", False, type=bool),
        "export_timings": s.value("export_timings", False, type=bool),
        "keep_tables": s.value("keep_tables", True, type=bool),
        "keep_formulas": s.value("keep_formulas", False, type=bool),
        "formula_recovery_preset": s.value("formula_recovery_preset", "balanced"),
        "deepseek_limited_production": s.value(
            "deepseek_limited_production", False, type=bool
        ),
        "keep_refs": s.value("keep_refs", True, type=bool),
        "images_scale": float(s.value("images_scale", 3.0)),
        "image_path_mode": s.value("image_path_mode", "relative"),
    }


def _env_tone(status: str) -> str:
    s = (status or "").lower()
    if status in ("Ready", "Warm") or s.startswith("ready") or s.startswith("warm"):
        return "success"
    if status in ("Optional", "Cold", "Warming"):
        return "warning"
    if status in ("Unavailable", "Error") or "不可用" in (status or ""):
        return "danger"
    return "neutral"


class SettingsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.resize(760, 620)
        cfg = load_defaults()

        root = QVBoxLayout(self)
        body = QHBoxLayout()
        body.setSpacing(16)

        self.nav = QListWidget()
        self.nav.setObjectName("settingsNav")
        self.nav.setFixedWidth(150)
        self.nav.setSpacing(2)
        for name in _NAV:
            QListWidgetItem(name, self.nav)
        self.nav.setCurrentRow(0)
        body.addWidget(self.nav)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._page_general(cfg))
        self.stack.addWidget(self._page_convert(cfg))
        self.stack.addWidget(self._page_output(cfg))
        self.stack.addWidget(self._page_look(cfg))
        self.stack.addWidget(self._page_env())
        self.nav.currentRowChanged.connect(self._on_nav)
        body.addWidget(self.stack, 1)
        root.addLayout(body, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._probe: EnvProbeWorker | None = None
        self._env_probed = False

    def _on_nav(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        if index == 4:
            self._ensure_env_probe()

    def _ensure_env_probe(self) -> None:
        if self._env_probed:
            return
        self._env_probed = True
        self._probe = EnvProbeWorker()
        self._probe.finished_info.connect(self._show_env)
        self._probe.start()

    def _page_general(self, cfg: dict) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        card = SectionCard("常规", "完成时的提示，不改变转换算法。")
        self.auto_open = QCheckBox("自动打开导出目录")
        self.auto_open.setChecked(bool(cfg["auto_open"]))
        card.body.addWidget(self.auto_open)
        self.notify = QCheckBox("转换完成时 Windows 通知（实验性）")
        self.notify.setChecked(bool(cfg["notify"]))
        self.notify.setToolTip("当前实现不保证系统托盘气泡；可关。")
        card.body.addWidget(self.notify)
        hint = QLabel("通知依赖系统托盘，失败时静默忽略。")
        hint.setProperty("role", "subtle")
        hint.setWordWrap(True)
        card.body.addWidget(hint)
        lay.addWidget(card)
        lay.addStretch(1)
        return page

    def _page_convert(self, cfg: dict) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        card = SectionCard("转换", "默认引擎与文档 OCR。公式恢复在主窗口「识别 · …」。")
        form = QFormLayout()
        self.engine = QComboBox()
        self.engine.addItems(["Docling", "MinerU", "自动"])
        self.engine.setCurrentText(str(cfg["engine"]))
        form.addRow("默认引擎：", self.engine)
        self.ocr = QComboBox()
        self.ocr.addItems(["自动", "强制 OCR", "禁用 OCR"])
        ocr_map = {"auto": "自动", "force": "强制 OCR", "disable": "禁用 OCR"}
        self.ocr.setCurrentText(ocr_map.get(str(cfg["ocr_mode"]), "自动"))
        ocr_hint = QLabel("文档 OCR ≠ 公式恢复所用的 DeepSeek OCR。")
        ocr_hint.setProperty("role", "subtle")
        form.addRow("文档 OCR：", self.ocr)
        form.addRow("", ocr_hint)
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
        self.cb_deepseek_ocr2 = QCheckBox("启用 DeepSeek-OCR-2 公式恢复（启动时加载模型）")
        self.cb_deepseek_ocr2.setChecked(bool(cfg.get("deepseek_limited_production", False)))
        self.cb_deepseek_ocr2.setToolTip(
            "关闭后不会拉起 dsocr2 Worker、不占用 GPU 显存。"
            "高保真视觉转录不依赖此项；需要公式恢复时再打开即可。"
        )
        ds_hint = QLabel(
            "当前实验若只做高保真视觉转录，可保持关闭。"
            "与主窗口「DeepSeek 高置信公式恢复」同步。"
        )
        ds_hint.setProperty("role", "subtle")
        ds_hint.setWordWrap(True)
        form.addRow(self.cb_deepseek_ocr2)
        form.addRow("", ds_hint)
        self.parallel = QSpinBox()
        self.parallel.setRange(1, 1)
        self.parallel.setValue(1)
        self.parallel.setEnabled(False)
        self.parallel.setToolTip("当前 Worker 为串行；并行尚未接入。")
        form.addRow("同时任务数：", self.parallel)
        lock_hint = QLabel("当前为串行转换（GPU 友好），不可调整。")
        lock_hint.setProperty("role", "subtle")
        form.addRow("", lock_hint)
        card.body.addLayout(form)
        lay.addWidget(card)
        lay.addStretch(1)
        return page

    def _page_output(self, cfg: dict) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        card = SectionCard("输出", "默认导出位置。")
        form = QFormLayout()
        out_row = QHBoxLayout()
        self.output = QLineEdit(str(cfg["output_dir"]))
        browse = QPushButton("选择...")
        browse.clicked.connect(self._browse)
        out_row.addWidget(self.output, 1)
        out_row.addWidget(browse)
        form.addRow("默认导出目录：", out_row)
        self.per_folder = QCheckBox("每篇论文建立独立文件夹")
        self.per_folder.setChecked(bool(cfg["per_folder"]))
        form.addRow(self.per_folder)
        card.body.addLayout(form)
        lay.addWidget(card)
        lay.addStretch(1)
        return page

    def _page_look(self, cfg: dict) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        card = SectionCard("外观", "保存后立即应用到全部已打开窗口。")
        form = QFormLayout()
        self.theme = QComboBox()
        self.theme.addItems(["跟随系统", "浅色", "深色"])
        self.theme.setCurrentText(str(cfg["theme"]))
        form.addRow("主题：", self.theme)
        card.body.addLayout(form)
        lay.addWidget(card)
        lay.addStretch(1)
        return page

    def _page_env(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        card = SectionCard(
            "环境状态",
            "只读探测。DeepSeek daemon 比 MinerU 是否安装更影响主路径。",
        )
        self.env_table = QTableWidget(0, 3)
        self.env_table.setHorizontalHeaderLabels(["组件", "状态", "详情"])
        self.env_table.verticalHeader().setVisible(False)
        self.env_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.env_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.env_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.env_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self.env_table.setMinimumHeight(280)
        card.body.addWidget(self.env_table)
        self._add_env_row("—", "…", "切换到此页后开始探测，不拉起 DeepSeek Worker。")
        lay.addWidget(card)
        return page

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "选择导出目录", self.output.text())
        if d:
            self.output.setText(d)

    def _add_env_row(self, name: str, status: str, detail: str) -> None:
        row = self.env_table.rowCount()
        self.env_table.insertRow(row)
        self.env_table.setItem(row, 0, QTableWidgetItem(name))
        self.env_table.setCellWidget(row, 1, StatusBadge(status, _env_tone(status)))
        item = QTableWidgetItem(detail)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.env_table.setItem(row, 2, item)

    def _show_env(self, info: dict) -> None:
        def status_of(v: str, *, optional: bool = False) -> str:
            text = str(v or "")
            if "不可用" in text:
                return "Optional" if optional else "Unavailable"
            return "Ready"

        self.env_table.setRowCount(0)
        self._add_env_row("Python", "Ready", str(info.get("python") or "?"))
        self._add_env_row("Docling", status_of(str(info.get("docling"))), str(info.get("docling")))
        self._add_env_row(
            "MinerU",
            status_of(str(info.get("mineru")), optional=True),
            str(info.get("mineru")),
        )
        self._add_env_row("PyTorch", status_of(str(info.get("torch"))), str(info.get("torch")))
        self._add_env_row("CUDA", status_of(str(info.get("cuda"))), str(info.get("cuda")))
        gpu = str(info.get("gpu") or "未知")
        vram = str(info.get("vram") or "")
        self._add_env_row("GPU", "Ready" if gpu != "未知" else "—", f"{gpu}  {vram}".strip())
        ds = str(info.get("deepseek") or "不可用")
        ds_state = str(info.get("deepseek_state") or ("Unavailable" if "不可用" in ds else "Ready"))
        self._add_env_row("DeepSeek daemon", ds_state, ds)

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
        s.setValue("deepseek_limited_production", self.cb_deepseek_ocr2.isChecked())
        s.setValue("parallel", 1)
        s.setValue("notify", self.notify.isChecked())
        s.setValue("auto_open", self.auto_open.isChecked())
        theme_value = self.theme.currentText()
        s.setValue("theme", theme_value)
        try:
            from app.ui.theme import theme_manager

            mgr = theme_manager()
            if mgr is not None:
                mgr.apply(theme_value)
        except Exception:
            pass
        Path(self.output.text().strip()).mkdir(parents=True, exist_ok=True)
        self.accept()
