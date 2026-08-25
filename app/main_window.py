"""主窗口。"""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.dialogs.formula_options_dialog import FormulaOptionsDialog
from app.dialogs.log_dialog import LogDialog
from app.dialogs.more_options_dialog import (
    MoreOptionsDialog,
    extras_summary,
    make_ellipsis_button,
)
from app.dialogs.settings_dialog import load_defaults, settings, SettingsDialog
from app.diagnostics.formula_task_summary import (
    TOOLTIP_FORMULA_POSTCHECK,
    TOOLTIP_FORMULA_RECOGNITION,
    formula_column_labels,
    formula_metrics_from_qa,
    load_formula_qa_for_task,
)
from app.diagnostics.vision_fidelity_summary import (
    TOOLTIP_VISION_FIDELITY,
    fidelity_metrics_from_stats,
    format_fidelity_label,
    load_fidelity_stats,
    vision_fidelity_column_label,
)
from app.drop_widget import DropWidget
from app.dialogs.vision_clipboard_dialog import VisionClipboardDialog
from app.dialogs.vision_deepseek_ui_dialog import VisionDeepSeekUiDialog
from app.dialogs.vision_figure_dialog import VisionFigureDialog
from app.task_model import ConvertTask, EngineChoice, TaskStatus, WorkflowChoice
from app.ui.icons import icon
from app.ui.identity import formula_profile_identity, formula_profile_tone
from app.ui.pipeline_classify import STAGE_LABELS, classify_pipeline_stage
from app.ui.task_table_markdown import format_task_table_markdown
from app.ui.widgets.collapsible import CollapsibleSection
from app.ui.widgets.command_bar import CommandBar
from app.ui.widgets.section_card import SectionCard
from app.ui.widgets.segmented import SegmentedControl
from app.ui.widgets.status_badge import StatusBadge
from app.ui.widgets.vision_status_panel import VisionStatusPanel
from app.utils.logger import add_listener, get_logger, remove_listener
from app.utils.paths import ensure_dirs
from app.vision_transcribe.config import VisionConfig
from app.workers.docling_worker import ConversionWorker
from app.workers.vision_worker import VisionConversionWorker, VisionFigureRebuildWorker

try:
    from pypdf import PdfReader
except Exception:  # noqa: BLE001
    PdfReader = None  # type: ignore


class MainWindow(QMainWindow):
    COLS = ["文件", "页数", "方式", "阶段", "状态", "恢复覆盖", "成功写回", "耗时", "操作"]
    # 复制 Markdown 时不含「操作」列（按钮列无文本）
    COLS_MARKDOWN = COLS[:-1]

    def __init__(self) -> None:
        super().__init__()
        ensure_dirs()
        self.setWindowTitle("PDF2MD")
        self.resize(1180, 760)
        self.setMinimumSize(1024, 700)

        self._tasks: dict[str, ConvertTask] = {}
        self._worker: ConversionWorker | VisionConversionWorker | None = None
        self._log_dialog = LogDialog(self)
        self._bench_dialog = None
        self._experiment_dialog = None
        self._done_count = 0
        self._total_count = 0

        self._vision_run_active = False
        self._figure_rebuild_worker: VisionFigureRebuildWorker | None = None

        self._build_ui()
        self._apply_settings_to_ui()
        self._kick_deepseek_background_warmup()

        get_logger()
        add_listener(self._on_log)
        get_logger().info("GUI 启动")

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 12, 16, 0)
        root.setSpacing(12)
        root.addWidget(self._build_app_header())
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        split.addWidget(self._build_workspace())
        split.addWidget(self._build_profile_panel())
        split.setStretchFactor(0, 7)
        split.setStretchFactor(1, 3)
        split.setSizes([790, 330])
        root.addWidget(split, 1)
        root.addWidget(self._build_command_bar())
        self._install_shortcuts()
        self._install_tab_order()
        self._sync_deepseek_lp_enabled()
        self._refresh_export_extras_label()
        self._refresh_recognize_extras_label()
        self._refresh_ds_badge()
        self._refresh_empty_state()

    def _header_button(self, text: str, slot, tip: str, icon_name: str = "") -> QPushButton:
        btn = QPushButton(text)
        btn.setToolTip(tip)
        if icon_name:
            btn.setIcon(icon(icon_name))
        btn.clicked.connect(slot)
        return btn

    def _build_app_header(self) -> QWidget:
        w = QWidget()
        header = QHBoxLayout(w)
        header.setContentsMargins(0, 0, 0, 0)
        title = QLabel("PDF2MD")
        title.setProperty("role", "title")
        ver = QLabel("v0.1.0-alpha")
        ver.setProperty("role", "subtle")
        self.badge_profile = StatusBadge("Lean Balanced", "info")
        header.addWidget(title)
        header.addWidget(ver)
        header.addWidget(self.badge_profile)
        header.addStretch(1)
        self.badge_ds = StatusBadge("DeepSeek · Cold", "neutral")
        header.addWidget(self.badge_ds)
        header.addWidget(self._header_button("设置", self._open_settings, "Ctrl+,  应用设置", "settings"))
        header.addWidget(self._header_button("日志", self._log_dialog.show, "Ctrl+L  转换日志", "log"))
        header.addWidget(self._header_button("公式实验室", self._open_formula_lab, "实验工作台（诊断）", "flask"))
        header.addWidget(self._header_button("实验结果", self._open_experiment_results, "诊断 dashboard", "chart"))
        header.addWidget(self._header_button("诊断缓存", self._open_experiment_cache, "logs/experiment 镜像", "database"))
        return w

    def _build_workspace(self) -> QWidget:
        left = QWidget()
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(0, 0, 8, 0)
        self.drop = DropWidget()
        self.drop.files_dropped.connect(self._on_drop)
        left_l.addWidget(self.drop)
        self.empty_hint = QLabel("队列为空。拖入或点击上方添加学术 PDF。")
        self.empty_hint.setProperty("role", "muted")
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_l.addWidget(self.empty_hint)
        table_toolbar = QHBoxLayout()
        table_toolbar.addStretch(1)
        self.btn_copy_tasks_md = QPushButton("复制为 Markdown")
        self.btn_copy_tasks_md.setToolTip("将下方任务列表复制为 Markdown 表格")
        self.btn_copy_tasks_md.setEnabled(False)
        self.btn_copy_tasks_md.clicked.connect(self._copy_task_table_markdown)
        table_toolbar.addWidget(self.btn_copy_tasks_md)
        left_l.addLayout(table_toolbar)
        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table.cellDoubleClicked.connect(self._on_double_click)
        self.table.cellClicked.connect(self._on_cell_clicked)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.horizontalHeader().setSectionResizeMode(8, QHeaderView.ResizeMode.ResizeToContents)
        left_l.addWidget(self.table, 1)
        return left

    def _build_profile_panel(self) -> QWidget:
        profile = QWidget()
        profile.setObjectName("profilePane")
        profile.setMinimumWidth(300)
        pr = QVBoxLayout(profile)
        pr.setContentsMargins(4, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        pane = QWidget()
        pl = QVBoxLayout(pane)
        pl.setSpacing(10)

        self.seg_workflow = SegmentedControl(
            [("快速自动", "structured"), ("高保真视觉", "vision")]
        )
        self.seg_workflow.value_changed.connect(self._on_workflow_changed)
        wf_card = SectionCard("转换模式")
        wf_card.body.addWidget(self.seg_workflow)
        self.lbl_workflow_hint = QLabel("Docling Lean + DeepSeek 公式恢复")
        self.lbl_workflow_hint.setWordWrap(True)
        self.lbl_workflow_hint.setProperty("role", "muted")
        wf_card.body.addWidget(self.lbl_workflow_hint)
        pl.addWidget(wf_card)

        self.rb_docling = QRadioButton("Docling", self)
        self.rb_mineru = QRadioButton("MinerU", self)
        self.rb_auto = QRadioButton("自动", self)
        self.rb_docling.setChecked(True)
        self.rb_docling.hide()
        self.rb_mineru.hide()
        self.rb_auto.hide()
        self._eng_group = QButtonGroup(self)
        for b in (self.rb_docling, self.rb_mineru, self.rb_auto):
            self._eng_group.addButton(b)
        self.seg_engine = SegmentedControl(
            [("Docling", "Docling"), ("MinerU", "MinerU"), ("自动", "自动")]
        )
        self.seg_engine.value_changed.connect(self._on_engine_segment)
        self.eng_card = SectionCard("解析引擎")
        self.eng_card.body.addWidget(self.seg_engine)
        pl.addWidget(self.eng_card)

        # 高保真视觉选项（默认隐藏）
        self.vision_card = SectionCard("高保真视觉")
        self.cmb_vision_browser = QComboBox()
        self.cmb_vision_browser.addItem("Playwright 自动（推荐）", "playwright")
        self.cmb_vision_browser.addItem("剪贴板半自动", "clipboard")
        vision_row = QHBoxLayout()
        vision_row.addWidget(QLabel("浏览器"))
        vision_row.addWidget(self.cmb_vision_browser, 1)
        self.vision_card.body.addLayout(vision_row)
        self.cb_vision_force_rerun = QCheckBox("强制重跑浏览器转录")
        self.cb_vision_force_rerun.setToolTip(
            "已完成的任务再次点「转换」默认就会整篇重跑，不必勾选。"
            "未完成但已有 accepted 批次时，勾选才会丢掉已接受结果从头转；"
            "不勾选则断点续跑。仅重合并/裁图请用右键。"
        )
        force_row = QHBoxLayout()
        force_row.addWidget(self.cb_vision_force_rerun)
        force_row.addStretch(1)
        self.vision_card.body.addLayout(force_row)
        self.lbl_vision_hint = QLabel(
            "Playwright 自动识图 · 渲染 3× · 每批 10 页 · 输出到「Pdf名_高保真」"
        )
        self.lbl_vision_hint.setWordWrap(True)
        self.lbl_vision_hint.setProperty("role", "muted")
        self.vision_card.body.addWidget(self.lbl_vision_hint)
        ui_row = QHBoxLayout()
        self.btn_vision_ui = QPushButton("DeepSeek UI…")
        self.btn_vision_ui.setToolTip("截图模板匹配 / 坐标校准（识图模式在最右侧）")
        self.btn_vision_ui.clicked.connect(self._open_vision_deepseek_ui)
        ui_row.addWidget(self.btn_vision_ui)
        ui_row.addStretch(1)
        self.vision_card.body.addLayout(ui_row)
        self.vision_status = VisionStatusPanel()
        self.vision_card.body.addWidget(self.vision_status)
        self.vision_card.setVisible(False)
        pl.addWidget(self.vision_card)

        self._structured_cards: list[QWidget] = []

        rec_card = SectionCard("识别")
        rec_row = QHBoxLayout()
        self.cb_tables = QCheckBox("表格")
        self.cb_tables.setChecked(True)
        rec_row.addWidget(self.cb_tables)
        rec_row.addStretch(1)
        rec_card.body.addLayout(rec_row)
        refs_row = QHBoxLayout()
        refs_row.addWidget(QLabel("参考文献"))
        refs_row.addStretch(1)
        refs_row.addWidget(StatusBadge("固定保留", "neutral"))
        rec_card.body.addLayout(refs_row)
        refs_hint = QLabel("当前执行器未提供独立关闭能力")
        refs_hint.setProperty("role", "subtle")
        rec_card.body.addWidget(refs_hint)
        self.cb_refs = QCheckBox("参考文献", self)
        self.cb_refs.setChecked(True)
        self.cb_refs.hide()
        self.cb_formulas = QCheckBox("Docling 公式 enrich")
        self.cb_formulas.setChecked(False)
        self.cmb_formula_recovery = QComboBox()
        self.cmb_formula_recovery.addItem("快速", "fast")
        self.cmb_formula_recovery.addItem("均衡（推荐）", "balanced")
        self.cmb_formula_recovery.addItem("精细", "quality")
        self.cmb_formula_recovery.setCurrentIndex(1)
        self.cb_deepseek_lp = QCheckBox("DeepSeek 高置信公式恢复")
        self.cb_deepseek_lp.setChecked(False)
        self.lbl_formula_identity = QLabel(
            "Lean Balanced：Docling 导出 LaTeX 种子 · DeepSeek 主修"
        )
        self.lbl_formula_identity.setWordWrap(True)
        self.lbl_formula_identity.setProperty("role", "muted")
        self._recognize_more = FormulaOptionsDialog(
            self,
            cmb_formula_recovery=self.cmb_formula_recovery,
            cb_formulas=self.cb_formulas,
            cb_deepseek_lp=self.cb_deepseek_lp,
            identity_label=self.lbl_formula_identity,
        )
        rec_extra = QHBoxLayout()
        self.lbl_recognize_extras = QLabel()
        self.lbl_recognize_extras.setProperty("role", "muted")
        self.btn_recognize_more = make_ellipsis_button(
            self, self._recognize_more, tooltip="公式恢复选项"
        )
        rec_extra.addWidget(self.lbl_recognize_extras, 1)
        rec_extra.addWidget(self.btn_recognize_more)
        rec_card.body.addLayout(rec_extra)
        self.cb_formulas.toggled.connect(self._refresh_recognize_extras_label)
        self.cmb_formula_recovery.currentIndexChanged.connect(self._sync_deepseek_lp_enabled)
        self.cmb_formula_recovery.currentIndexChanged.connect(self._refresh_recognize_extras_label)
        self.cb_deepseek_lp.toggled.connect(self._on_deepseek_lp_toggled)
        self.cb_deepseek_lp.toggled.connect(self._refresh_recognize_extras_label)
        self._recognize_more.finished.connect(self._refresh_recognize_extras_label)
        pl.addWidget(rec_card)
        self.rec_card = rec_card

        self.cb_images = QCheckBox("图片")
        self.cb_images.setChecked(True)
        self.cb_images.setVisible(False)
        self.cb_md = QCheckBox("Markdown")
        self.cb_md.setChecked(True)
        self.cb_raw_md = QCheckBox("原始解析 .raw.md")
        self.cb_repair_json = QCheckBox("修复报告 .repair.json")
        self.cb_conversion_log = QCheckBox("conversion.log")
        self.cb_manifest = QCheckBox("manifest.json")
        self.cb_formula_qa = QCheckBox("公式 QA")
        self.cb_timings = QCheckBox("计时 JSON")
        self._export_extra_cbs = [
            self.cb_raw_md,
            self.cb_repair_json,
            self.cb_conversion_log,
            self.cb_manifest,
            self.cb_formula_qa,
            self.cb_timings,
        ]
        self._export_more = MoreOptionsDialog(
            self,
            title="导出组件 · 更多",
            groups=[
                (
                    "中间产物",
                    [self.cb_raw_md, self.cb_repair_json, self.cb_conversion_log, self.cb_manifest],
                ),
                ("诊断副本", [self.cb_formula_qa, self.cb_timings]),
            ],
            banner_title="诊断始终镜像",
            banner_body="formula_qa / timings 始终写入 logs/experiment；此处只控制是否额外写进论文目录。",
        )
        exp_card = SectionCard("导出")
        exp_row = QHBoxLayout()
        lock = QLabel("图片 🔒")
        lock.setToolTip("图片为必要组件，始终导出")
        exp_row.addWidget(lock)
        exp_row.addWidget(self.cb_md)
        exp_row.addStretch(1)
        exp_card.body.addLayout(exp_row)
        extra_row = QHBoxLayout()
        self.lbl_export_extras = QLabel()
        self.lbl_export_extras.setProperty("role", "muted")
        self.btn_export_more = make_ellipsis_button(
            self, self._export_more, tooltip="更多导出组件（中间产物 / 诊断）"
        )
        extra_row.addWidget(self.lbl_export_extras, 1)
        extra_row.addWidget(self.btn_export_more)
        exp_card.body.addLayout(extra_row)
        for c in self._export_extra_cbs:
            c.toggled.connect(self._refresh_export_extras_label)
        self._export_more.finished.connect(self._refresh_export_extras_label)
        pl.addWidget(exp_card)
        self.exp_card = exp_card

        out_card = SectionCard("输出")
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("导出目录")
        self.output_edit.editingFinished.connect(self._persist_output_dir)
        out_dir_row = QHBoxLayout()
        out_dir_row.addWidget(self.output_edit, 1)
        btn_out = QPushButton("浏览")
        btn_out.clicked.connect(self._pick_output)
        btn_open_out = QPushButton("打开")
        btn_open_out.clicked.connect(self._open_output_root)
        out_dir_row.addWidget(btn_out)
        out_dir_row.addWidget(btn_open_out)
        out_card.body.addLayout(out_dir_row)
        self.cb_per_folder = QCheckBox("每篇独立文件夹")
        self.cb_per_folder.setChecked(True)
        out_card.body.addWidget(self.cb_per_folder)
        pl.addWidget(out_card)

        adv = CollapsibleSection("高级转换参数")
        self.rb_img_fast = QRadioButton("快速")
        self.rb_img_std = QRadioButton("标准")
        self.rb_img_hq = QRadioButton("高清")
        self.rb_img_hq.setChecked(True)
        self._img_group = QButtonGroup(self)
        img_row = QHBoxLayout()
        img_row.addWidget(QLabel("图片质量"))
        for b in (self.rb_img_fast, self.rb_img_std, self.rb_img_hq):
            self._img_group.addButton(b)
            img_row.addWidget(b)
        adv.body.addLayout(img_row)
        self.rb_path_rel = QRadioButton("相对路径")
        self.rb_path_abs = QRadioButton("绝对路径")
        self.rb_path_rel.setChecked(True)
        self._path_group = QButtonGroup(self)
        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("图片路径"))
        for b in (self.rb_path_rel, self.rb_path_abs):
            self._path_group.addButton(b)
            path_row.addWidget(b)
        adv.body.addLayout(path_row)
        self.rb_ocr_auto = QRadioButton("自动")
        self.rb_ocr_force = QRadioButton("强制")
        self.rb_ocr_off = QRadioButton("禁用")
        self.rb_ocr_auto.setChecked(True)
        self._ocr_group = QButtonGroup(self)
        ocr_row = QHBoxLayout()
        ocr_lbl = QLabel("文档 OCR")
        ocr_lbl.setToolTip(
            "文档 OCR 控制 PDF 页面文本识别策略；"
            "与公式恢复所使用的 DeepSeek OCR 是两个独立概念。"
        )
        ocr_row.addWidget(ocr_lbl)
        for b in (self.rb_ocr_auto, self.rb_ocr_force, self.rb_ocr_off):
            self._ocr_group.addButton(b)
            ocr_row.addWidget(b)
        adv.body.addLayout(ocr_row)
        pl.addWidget(adv)
        self.adv_section = adv
        self._structured_cards = [self.eng_card, self.rec_card, self.exp_card, self.adv_section]
        pl.addStretch(1)
        scroll.setWidget(pane)
        pr.addWidget(scroll)
        return profile

    def _build_command_bar(self) -> QWidget:
        bar = CommandBar()
        self.command_bar = bar
        self.progress = bar.progress
        self.stage_label = bar.current
        self.count_label = bar.count
        self.btn_start = bar.start
        self.btn_cancel = bar.cancel
        self.btn_clear = bar.clear
        self.btn_open_md = QPushButton("打开 Markdown", self)
        self.btn_open_dir = QPushButton("打开文件夹", self)
        self.btn_open_md.hide()
        self.btn_open_dir.hide()
        bar.start_clicked.connect(self._start)
        bar.cancel_clicked.connect(self._cancel)
        bar.clear_clicked.connect(self._clear)
        self.btn_open_md.clicked.connect(self._open_selected_md)
        self.btn_open_dir.clicked.connect(self._open_selected_dir)
        return bar

    def _install_shortcuts(self) -> None:
        def add(seq: str, slot, tip: str = "") -> None:
            act = QAction(self)
            act.setShortcut(QKeySequence(seq))
            act.triggered.connect(slot)
            if tip:
                act.setToolTip(tip)
            self.addAction(act)

        add("Ctrl+Return", self._start)
        add("Ctrl+Enter", self._start)
        add("Esc", self._cancel)
        add("Ctrl+,", self._open_settings)
        add("Ctrl+L", self._log_dialog.show)
        add("F5", self._open_experiment_results)

    def _install_tab_order(self) -> None:
        QWidget.setTabOrder(self.drop, self.table)
        QWidget.setTabOrder(self.table, self.seg_workflow)
        QWidget.setTabOrder(self.seg_workflow, self.seg_engine)
        QWidget.setTabOrder(self.seg_engine, self.cb_tables)
        QWidget.setTabOrder(self.cb_tables, self.cb_md)
        QWidget.setTabOrder(self.cb_md, self.output_edit)
        QWidget.setTabOrder(self.output_edit, self.btn_start)
        QWidget.setTabOrder(self.btn_start, self.btn_cancel)
        QWidget.setTabOrder(self.btn_cancel, self.btn_clear)

    def _current_workflow(self) -> str:
        val = self.seg_workflow.value()
        if val == "vision":
            return WorkflowChoice.VISION.value
        return WorkflowChoice.STRUCTURED.value

    def _on_workflow_changed(self, value: str) -> None:
        vision = value == "vision"
        self.vision_card.setVisible(vision)
        for w in getattr(self, "_structured_cards", []):
            w.setVisible(not vision)
        if vision:
            self.lbl_workflow_hint.setText("整页视觉转录 + 人工图片确认")
            self.command_bar.pipeline.set_mode("vision")
            self.badge_profile.set_status("Vision Fidelity", "info")
            self.vision_status.set_active(False)
        else:
            self.lbl_workflow_hint.setText("Docling Lean + DeepSeek 公式恢复")
            self.command_bar.pipeline.set_mode("structured")
            self._refresh_recognize_extras_label()
            self.vision_status.set_active(False)

    def _refresh_empty_state(self) -> None:
        empty = self.table.rowCount() == 0
        self.empty_hint.setVisible(empty)
        self.table.setVisible(not empty)
        self.btn_copy_tasks_md.setEnabled(not empty)

    def _task_table_row_values(self, task: ConvertTask) -> list[str]:
        status_text, _ = self._status_display(task)
        if getattr(task, "workflow", "") == WorkflowChoice.VISION.value:
            mode = "视觉高保真"
            rec_lbl, post_lbl = "—", self._vision_fidelity_label(task)
        else:
            mode = task.engine
            rec_lbl, post_lbl = self._formula_column_labels(task)
        return [
            task.name,
            str(task.pages) if task.pages is not None else "-",
            mode,
            self._stage_display(task),
            status_text,
            rec_lbl,
            post_lbl,
            f"{task.elapsed_sec:.1f}s" if task.elapsed_sec is not None else "-",
        ]

    def _copy_task_table_markdown(self) -> None:
        if self.table.rowCount() == 0:
            QMessageBox.information(self, "任务列表", "没有可复制的内容。")
            return
        rows: list[list[str]] = []
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if not item:
                continue
            tid = item.data(Qt.ItemDataRole.UserRole)
            task = self._tasks.get(tid)
            if task is None:
                continue
            rows.append(self._task_table_row_values(task))
        if not rows:
            QMessageBox.information(self, "任务列表", "没有可复制的内容。")
            return
        md = format_task_table_markdown(self.COLS_MARKDOWN, rows)
        QGuiApplication.clipboard().setText(md)
        QMessageBox.information(
            self,
            "任务列表",
            f"已复制 {len(rows)} 条任务的 Markdown 表格到剪贴板。",
        )

    def _refresh_export_extras_label(self, *_args) -> None:
        self.lbl_export_extras.setText(extras_summary(self._export_extra_cbs))

    def _on_engine_segment(self, value: str) -> None:
        if value == "MinerU":
            self.rb_mineru.setChecked(True)
        elif value == "自动":
            self.rb_auto.setChecked(True)
        else:
            self.rb_docling.setChecked(True)

    def _kick_deepseek_background_warmup(self) -> None:
        """应用启动/开启 LP 时后台暖机，与选文件解耦。"""
        if not self._deepseek_limited_production():
            return

        def _emit_ds_state(state: str) -> None:
            from PySide6.QtCore import QTimer

            QTimer.singleShot(0, lambda s=state: self._on_deepseek_state(s))

        def _run() -> None:
            try:
                from app.ocr.deepseek_worker_client import ensure_deepseek_daemon

                info = ensure_deepseek_daemon(warmup=True)
                h = info.get("health") or {}
                if h.get("model_loaded"):
                    _emit_ds_state("warm")
                elif info.get("warmup_started"):
                    _emit_ds_state("warming")
            except Exception:
                pass

        import threading

        threading.Thread(target=_run, daemon=True, name="ds-gui-warmup").start()
        _emit_ds_state("warming")

    def _refresh_ds_badge(self) -> None:
        if not self._deepseek_limited_production():
            self.badge_ds.set_status("DeepSeek · Off", "neutral")
            self.command_bar.deepseek.set_status("DeepSeek · Off", "neutral")
            return
        self.badge_ds.set_status("DeepSeek · Cold", "neutral")
        self.command_bar.deepseek.set_status("DeepSeek · Cold", "neutral")

    def _on_pipeline_stage(self, stage: str) -> None:
        self.command_bar.pipeline.set_stage(stage)
        if self._vision_run_active:
            self.vision_status.set_pipeline_stage(stage)

    def _on_vision_log(self, line: str) -> None:
        self._on_log(line)
        # 高保真运行中，或侧栏可见时，一律写入状态面板（避免漏掉 [PW]/[UI L2]）
        if self._vision_run_active or (
            hasattr(self, "vision_card") and self.vision_card.isVisible()
        ):
            self.vision_status.set_active(True)
            self.vision_status.append_line(line)

    def _on_deepseek_state(self, state: str) -> None:
        mapping = {
            "warming": ("DeepSeek · Warming", "warning"),
            "warm": ("DeepSeek · Warm", "info"),
            "unavailable": ("DeepSeek · Unavailable", "danger"),
            "cold": ("DeepSeek · Cold", "neutral"),
        }
        text, tone = mapping.get(state, ("DeepSeek · —", "neutral"))
        self.badge_ds.set_status(text, tone)
        self.command_bar.deepseek.set_status(text, tone)

    def _update_pipeline_from_stage(self, text: str) -> None:
        from app.ui.identity import classify_deepseek_state, classify_pipeline_stage

        kind = classify_pipeline_stage(text)
        if kind:
            self._on_pipeline_stage(kind)
        ds = classify_deepseek_state(text)
        if ds:
            self._on_deepseek_state(ds)

    def _refresh_recognize_extras_label(self, *_args) -> None:
        ident = formula_profile_identity(
            preset=self._formula_recovery_preset(),
            enrich=self.cb_formulas.isChecked(),
            deepseek=self._deepseek_limited_production(),
        )
        tone = formula_profile_tone(ident)
        self.badge_profile.set_status(ident, tone)
        self.lbl_recognize_extras.setText(f"公式：{ident}")
        self.lbl_formula_identity.setText(
            f"Docling formula enrich {'ON' if self.cb_formulas.isChecked() else 'OFF'}"
            f" · DeepSeek limited production "
            f"{'ON' if self._deepseek_limited_production() else 'OFF'}"
        )
        self._recognize_more.set_identity(ident)
        self._refresh_ds_badge()

    def _apply_settings_to_ui(self) -> None:
        was_ds = self._deepseek_limited_production()
        cfg = load_defaults()
        self.output_edit.setText(str(cfg["output_dir"]))
        self.cb_per_folder.setChecked(bool(cfg["per_folder"]))
        eng = str(cfg["engine"])
        if eng == "MinerU":
            self.rb_mineru.setChecked(True)
            self.seg_engine.set_value("MinerU")
        elif eng == "自动":
            self.rb_auto.setChecked(True)
            self.seg_engine.set_value("自动")
        else:
            self.rb_docling.setChecked(True)
            self.seg_engine.set_value("Docling")
        ocr = str(cfg["ocr_mode"])
        if ocr == "force":
            self.rb_ocr_force.setChecked(True)
        elif ocr == "disable":
            self.rb_ocr_off.setChecked(True)
        else:
            self.rb_ocr_auto.setChecked(True)
        # 图片始终导出
        self.cb_images.setChecked(True)
        self.cb_md.setChecked(bool(cfg.get("export_md", True)))
        self.cb_raw_md.setChecked(bool(cfg.get("export_raw_md", False)))
        self.cb_repair_json.setChecked(bool(cfg.get("export_repair_json", False)))
        self.cb_conversion_log.setChecked(bool(cfg.get("export_conversion_log", False)))
        self.cb_manifest.setChecked(bool(cfg.get("export_manifest", False)))
        self.cb_formula_qa.setChecked(bool(cfg.get("export_formula_qa", False)))
        self.cb_timings.setChecked(bool(cfg.get("export_timings", False)))
        self._refresh_export_extras_label()
        self.cb_tables.setChecked(bool(cfg["keep_tables"]))
        self.cb_formulas.setChecked(bool(cfg["keep_formulas"]))
        preset = str(cfg.get("formula_recovery_preset", "balanced") or "balanced").lower()
        idx = self.cmb_formula_recovery.findData(preset)
        self.cmb_formula_recovery.setCurrentIndex(idx if idx >= 0 else 1)
        self.cb_deepseek_lp.setChecked(bool(cfg.get("deepseek_limited_production", False)))
        self._sync_deepseek_lp_enabled()
        if self._deepseek_limited_production():
            self.cb_formulas.setChecked(False)
        self.cb_refs.setChecked(bool(cfg["keep_refs"]))
        self._refresh_recognize_extras_label()
        scale = float(cfg.get("images_scale", 2.0))
        if scale <= 1.0:
            self.rb_img_fast.setChecked(True)
        elif scale >= 3.0:
            self.rb_img_hq.setChecked(True)
        else:
            self.rb_img_std.setChecked(True)
        mode = str(cfg.get("image_path_mode", "relative"))
        if mode == "absolute":
            self.rb_path_abs.setChecked(True)
        else:
            self.rb_path_rel.setChecked(True)
        now_ds = self._deepseek_limited_production()
        if was_ds and not now_ds:
            self._shutdown_deepseek_ocr2()
        elif not was_ds and now_ds:
            self._kick_deepseek_background_warmup()
        else:
            self._refresh_ds_badge()

    def _shutdown_deepseek_ocr2(self) -> None:
        """关闭 OCR-2 时释放 Worker / GPU。"""
        try:
            from app.ocr.deepseek_worker_client import reset_deepseek_worker_client

            reset_deepseek_worker_client(kill_worker=True)
        except Exception:
            pass
        self._refresh_ds_badge()

    def _images_scale(self) -> float:
        if self.rb_img_fast.isChecked():
            return 1.0
        if self.rb_img_hq.isChecked():
            return 3.0
        return 2.0

    def _image_path_mode(self) -> str:
        return "absolute" if self.rb_path_abs.isChecked() else "relative"

    def _formula_recovery_preset(self) -> str:
        data = self.cmb_formula_recovery.currentData()
        return str(data or "balanced")

    def _deepseek_limited_production(self) -> bool:
        # Phase 5E：Lean = UI 不勾 enrich（省 Docling 重复跑），解析仍导出 LaTeX 种子 + DS ON
        return bool(
            self._formula_recovery_preset() == "balanced"
            and self.cb_deepseek_lp.isChecked()
        )

    def _sync_deepseek_lp_enabled(self) -> None:
        ok = self._formula_recovery_preset() == "balanced"
        self.cb_deepseek_lp.setEnabled(ok)
        if not ok:
            self.cb_deepseek_lp.setChecked(False)
        # 均衡恢复始终可用（不依赖 Docling enrich）
        self.cmb_formula_recovery.setEnabled(True)

    def _on_deepseek_lp_toggled(self, checked: bool) -> None:
        settings().setValue("deepseek_limited_production", bool(checked))
        # Lean：开启 DeepSeek 时自动关掉 Docling enrich，避免双路径浪费
        if checked and self._formula_recovery_preset() == "balanced":
            self.cb_formulas.setChecked(False)
        if checked:
            self._kick_deepseek_background_warmup()
        else:
            self._shutdown_deepseek_ocr2()

    def _effective_keep_formulas(self) -> bool:
        """Lean Balanced：UI 显示 enrich OFF；实际解析仍导出 LaTeX 种子供 DeepSeek 抢救。"""
        if self._deepseek_limited_production():
            return False
        return self.cb_formulas.isChecked()

    def _current_engine(self) -> str:
        if self.rb_mineru.isChecked():
            return EngineChoice.MINERU.value
        if self.rb_auto.isChecked():
            return EngineChoice.AUTO.value
        return EngineChoice.DOCLING.value

    def _ocr_mode(self) -> str:
        if self.rb_ocr_force.isChecked():
            return "force"
        if self.rb_ocr_off.isChecked():
            return "disable"
        return "auto"

    def _on_drop(self, paths: list[str]) -> None:
        if not paths:
            files, _ = QFileDialog.getOpenFileNames(
                self, "选择 PDF", "", "PDF Files (*.pdf)"
            )
            paths = files
        for p in paths:
            self._add_task(Path(p))

    def _add_task(self, pdf: Path) -> None:
        if not pdf.exists() or pdf.suffix.lower() != ".pdf":
            return
        tid = str(pdf.resolve())
        if tid in self._tasks:
            return
        pages = None
        if PdfReader is not None:
            try:
                pages = len(PdfReader(str(pdf)).pages)
            except Exception:
                pages = None
        task = ConvertTask(
            pdf_path=pdf,
            engine=self._current_engine(),
            workflow=self._current_workflow(),
            pages=pages,
        )
        self._tasks[tid] = task
        row = self.table.rowCount()
        self.table.insertRow(row)
        self._refresh_row(row, task)
        self.drop.set_compact(True)
        self._refresh_empty_state()

    def _row_of(self, task_id: str) -> int:
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == task_id:
                return r
        return -1

    def _stage_display(self, task: ConvertTask) -> str:
        if task.status == TaskStatus.WAITING.value:
            return "—"
        if task.status == TaskStatus.DONE.value:
            return "Done"
        if task.status in (TaskStatus.FAILED.value, TaskStatus.CANCELLED.value):
            return "—"
        kind = classify_pipeline_stage(task.message or "")
        return STAGE_LABELS.get(kind, task.message or "—")

    def _status_display(self, task: ConvertTask) -> tuple[str, str]:
        raw = task.status
        if raw == TaskStatus.RUNNING.value:
            kind = classify_pipeline_stage(task.message or "")
            label = STAGE_LABELS.get(kind, "Running")
            if label == "Done":
                label = "Running"
            return (label, "info")
        mapping = {
            TaskStatus.WAITING.value: ("Queued", "neutral"),
            TaskStatus.DONE.value: ("Completed", "success"),
            TaskStatus.FAILED.value: ("Failed", "danger"),
            TaskStatus.CANCELLED.value: ("Cancelled", "warning"),
        }
        return mapping.get(raw, (raw, "neutral"))

    def _make_action_cell(self, task: ConvertTask) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(4, 0, 4, 0)
        lay.setSpacing(4)
        tid = task.id
        if task.status == TaskStatus.DONE.value:
            btn_md = QPushButton()
            btn_md.setIcon(icon("file"))
            btn_md.setProperty("variant", "icon")
            btn_md.setToolTip("打开 Markdown")
            btn_md.clicked.connect(lambda: self._open_task_md(tid))
            btn_dir = QPushButton()
            btn_dir.setIcon(icon("folder"))
            btn_dir.setProperty("variant", "icon")
            btn_dir.setToolTip("打开文件夹")
            btn_dir.clicked.connect(lambda: self._open_task_dir(tid))
            lay.addWidget(btn_md)
            lay.addWidget(btn_dir)
        elif task.status == TaskStatus.FAILED.value:
            btn = QPushButton("查看错误")
            btn.setProperty("variant", "icon")
            btn.setToolTip(task.error or "查看错误")
            btn.clicked.connect(lambda: self._show_task_error(tid))
            lay.addWidget(btn)
        else:
            dash = QLabel("—")
            dash.setProperty("role", "subtle")
            lay.addWidget(dash)
        lay.addStretch(1)
        return w

    def _open_task_md(self, task_id: str) -> None:
        t = self._tasks.get(task_id)
        if not t or not t.output_md or not t.output_md.exists():
            QMessageBox.information(self, "提示", "请选择已完成且有 Markdown 输出的任务。")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(t.output_md)))

    def _open_task_dir(self, task_id: str) -> None:
        t = self._tasks.get(task_id)
        if not t or not t.output_dir:
            QMessageBox.information(self, "提示", "请选择已有输出目录的任务。")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(t.output_dir)))

    def _show_task_error(self, task_id: str) -> None:
        t = self._tasks.get(task_id)
        QMessageBox.warning(self, "错误信息", (t.error if t else "") or "无错误信息")

    def _load_task_formula_metrics(self, task: ConvertTask) -> None:
        qa = load_formula_qa_for_task(
            pdf_stem=task.pdf_path.stem,
            out_dir=task.output_dir,
        )
        rec, post, total = formula_metrics_from_qa(qa)
        task.formula_recognized = rec
        task.formula_post_ok = post
        task.formula_total = total

    def _load_task_vision_fidelity(self, task: ConvertTask) -> None:
        stats = load_fidelity_stats(task.output_dir)
        final_c, ds_c, ratio = fidelity_metrics_from_stats(stats)
        task.vision_final_chars = final_c
        task.vision_ds_chars = ds_c
        task.vision_fidelity_ratio = ratio

    def _vision_fidelity_label(self, task: ConvertTask) -> str:
        if task.status == TaskStatus.RUNNING.value:
            return vision_fidelity_column_label(
                out_dir=task.output_dir,
                partial=True,
            )
        if task.vision_final_chars is not None or task.vision_ds_chars is not None:
            return format_fidelity_label(
                final_chars=task.vision_final_chars,
                ds_chars=task.vision_ds_chars,
            )
        return vision_fidelity_column_label(out_dir=task.output_dir)

    def _formula_column_labels(self, task: ConvertTask) -> tuple[str, str]:
        qa = load_formula_qa_for_task(
            pdf_stem=task.pdf_path.stem,
            out_dir=task.output_dir,
        )
        return formula_column_labels(qa)

    def _formula_recognition_label(self, task: ConvertTask) -> str:
        return self._formula_column_labels(task)[0]

    def _formula_posthoc_label(self, task: ConvertTask) -> str:
        return self._formula_column_labels(task)[1]

    def _refresh_row(self, row: int, task: ConvertTask) -> None:
        status_text, tone = self._status_display(task)
        stage = self._stage_display(task)
        if task.status == TaskStatus.RUNNING.value:
            if getattr(task, "workflow", "") == WorkflowChoice.VISION.value:
                self._load_task_vision_fidelity(task)
                rec_lbl, post_lbl = "—", self._vision_fidelity_label(task)
            else:
                rec_lbl, post_lbl = "…", "…"
        elif task.status == TaskStatus.WAITING.value:
            rec_lbl, post_lbl = "—", "—"
        elif getattr(task, "workflow", "") == WorkflowChoice.VISION.value:
            rec_lbl, post_lbl = "—", self._vision_fidelity_label(task)
        else:
            rec_lbl, post_lbl = self._formula_column_labels(task)
        mode = (
            "视觉高保真"
            if getattr(task, "workflow", "") == WorkflowChoice.VISION.value
            else task.engine
        )
        vals = [
            task.name,
            str(task.pages) if task.pages is not None else "-",
            mode,
            stage,
            status_text,
            rec_lbl,
            post_lbl,
            f"{task.elapsed_sec:.1f}s" if task.elapsed_sec is not None else "-",
            "",
        ]
        for c, v in enumerate(vals):
            item = QTableWidgetItem(v)
            if c == 0:
                item.setData(Qt.ItemDataRole.UserRole, task.id)
                item.setToolTip(f"{task.size_label} · {task.pdf_path}")
            if c == 5:
                item.setToolTip(
                    TOOLTIP_FORMULA_RECOGNITION
                    if task.formula_total is not None
                    else "转换完成后从 formula_qa 读取"
                )
            if c == 6:
                if getattr(task, "workflow", "") == WorkflowChoice.VISION.value:
                    item.setToolTip(TOOLTIP_VISION_FIDELITY)
                else:
                    item.setToolTip(
                        TOOLTIP_FORMULA_POSTCHECK
                        if task.formula_total is not None
                        else "转换完成后从 formula_qa 读取"
                    )
            if c == 5 and task.formula_total and task.formula_recognized is not None:
                if task.formula_recognized < task.formula_total:
                    item.setForeground(Qt.GlobalColor.darkYellow)
            if c == 6 and getattr(task, "workflow", "") == WorkflowChoice.VISION.value:
                ratio = task.vision_fidelity_ratio
                if ratio is not None:
                    if ratio < 0.70:
                        item.setForeground(Qt.GlobalColor.red)
                    elif ratio < 0.85:
                        item.setForeground(Qt.GlobalColor.darkYellow)
                    elif ratio >= 0.95:
                        item.setForeground(Qt.GlobalColor.darkGreen)
            if c == 6 and task.formula_total and task.formula_post_ok is not None:
                if (
                    task.formula_post_ok < task.formula_total
                    or (
                        task.formula_recognized is not None
                        and task.formula_post_ok < task.formula_recognized
                    )
                ):
                    item.setForeground(Qt.GlobalColor.red)
                elif task.formula_post_ok == task.formula_total:
                    item.setForeground(Qt.GlobalColor.darkGreen)
            self.table.setItem(row, c, item)
        self.table.setCellWidget(row, 4, StatusBadge(status_text, tone))
        self.table.setCellWidget(row, 8, self._make_action_cell(task))

    def _selected_task(self) -> ConvertTask | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.table.item(rows[0].row(), 0)
        if not item:
            return None
        return self._tasks.get(item.data(Qt.ItemDataRole.UserRole))

    def _start(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        waiting = [
            t
            for t in self._tasks.values()
            if t.status
            in (
                TaskStatus.WAITING.value,
                TaskStatus.FAILED.value,
                TaskStatus.DONE.value,
            )
        ]
        if not waiting:
            QMessageBox.information(self, "提示", "没有待转换的 PDF。请先拖入文件。")
            return

        out_text = self.output_edit.text().strip()
        if not out_text:
            QMessageBox.warning(self, "导出目录", "请先指定导出目录。")
            self.output_edit.setFocus()
            return
        out_root = Path(out_text)
        try:
            out_root.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            QMessageBox.warning(self, "导出目录", f"无法创建导出目录：\n{out_root}\n\n{e}")
            return
        if not out_root.is_dir():
            QMessageBox.warning(self, "导出目录", f"路径不是有效目录：\n{out_root}")
            return
        self._persist_output_dir()

        # 更新工作流 / 引擎到任务
        eng = self._current_engine()
        wf = self._current_workflow()
        from app.utils.paths import vision_task_output_dir
        from app.vision_transcribe.manifest import should_force_vision_rerun

        for t in waiting:
            was_done = t.status == TaskStatus.DONE.value
            if t.status in (
                TaskStatus.WAITING.value,
                TaskStatus.FAILED.value,
                TaskStatus.DONE.value,
            ):
                t.workflow = wf
                t.engine = eng
                t.status = TaskStatus.WAITING.value
                t.error = ""
                if wf == WorkflowChoice.VISION.value:
                    vis_out = vision_task_output_dir(out_root, t.pdf_path)
                    t.vision_force_rerun = should_force_vision_rerun(
                        vis_out,
                        checkbox=self.cb_vision_force_rerun.isChecked(),
                        task_was_done=was_done,
                    )
                else:
                    t.vision_force_rerun = False

        self._done_count = 0
        self._total_count = len(waiting)
        self.command_bar.set_running(True)
        self.command_bar.set_count(0, self._total_count)
        self.command_bar.pipeline.reset()

        if wf == WorkflowChoice.VISION.value:
            self.command_bar.pipeline.set_mode("vision")
            self.command_bar.pipeline.set_stage("render")
            mode = self.cmb_vision_browser.currentData() or "clipboard"
            cfg = VisionConfig(
                browser_mode=str(mode),
                headless=False,
                images_scale=self._images_scale(),
                image_path_mode=self._image_path_mode(),
            )
            # 高保真固定输出到「Pdf名_高保真」，与快速模式目录隔离
            per_folder = True
            if not self.cb_per_folder.isChecked():
                self._on_vision_log(
                    "[vision] 高保真输出到「Pdf名_高保真」子文件夹（与快速模式隔离）"
                )
            self._vision_run_active = True
            self.vision_status.clear()
            self.vision_status.set_active(True)
            self.vision_status.append_line(
                f"开始高保真 · 浏览器={mode} · 共 {len(waiting)} 篇"
            )
            self._worker = VisionConversionWorker(
                waiting,
                output_root=out_root,
                per_folder=per_folder,
                config=cfg,
            )
            self._worker.task_status.connect(self._on_task_status)
            self._worker.task_finished.connect(self._on_task_finished)
            self._worker.log_line.connect(self._on_vision_log)
            self._worker.stage.connect(self._on_stage)
            self._worker.pipeline_stage.connect(self._on_pipeline_stage)
            self._worker.needs_clipboard.connect(self._on_vision_clipboard)
            self._worker.needs_user.connect(self._on_vision_needs_user)
            self._worker.needs_figures.connect(self._on_vision_figures)
            self._worker.finished.connect(self._on_worker_done)
            self._worker.start()
            return

        self.command_bar.pipeline.set_mode("structured")
        self.command_bar.pipeline.set_stage("parse")

        # V1：串行（默认 1），GPU 友好
        self._worker = ConversionWorker(
            waiting,
            output_root=out_root,
            per_folder=self.cb_per_folder.isChecked(),
            ocr_mode=self._ocr_mode(),
            keep_images=True,  # 图片为必要组件
            keep_tables=self.cb_tables.isChecked(),
            keep_formulas=self._effective_keep_formulas(),
            formula_recovery_preset=self._formula_recovery_preset(),
            deepseek_limited_production=self._deepseek_limited_production(),
            images_scale=self._images_scale(),
            image_path_mode=self._image_path_mode(),
            export_md=self.cb_md.isChecked(),
            export_raw_md=self.cb_raw_md.isChecked(),
            export_repair_json=self.cb_repair_json.isChecked(),
            export_conversion_log=self.cb_conversion_log.isChecked(),
            export_manifest=self.cb_manifest.isChecked(),
            export_formula_qa=self.cb_formula_qa.isChecked(),
            export_timings=self.cb_timings.isChecked(),
        )
        self._worker.task_status.connect(self._on_task_status)
        self._worker.task_finished.connect(self._on_task_finished)
        self._worker.log_line.connect(self._on_log)
        self._worker.stage.connect(self._on_stage)
        self._worker.pipeline_stage.connect(self._on_pipeline_stage)
        self._worker.deepseek_state.connect(self._on_deepseek_state)
        self._worker.finished.connect(self._on_worker_done)
        self._worker.start()

    def _on_vision_clipboard(
        self,
        task_id: str,
        batch_id: int,
        start_page: int,
        end_page: int,
        hint: str,
    ) -> None:
        dlg = VisionClipboardDialog(
            self, start_page=start_page, end_page=end_page, hint=hint
        )
        if dlg.exec():
            text = dlg.result_text()
            if isinstance(self._worker, VisionConversionWorker):
                self._worker.submit_clipboard(text)
        else:
            if isinstance(self._worker, VisionConversionWorker):
                self._worker.request_cancel()

    def _on_vision_needs_user(self, task_id: str, message: str) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("需要人工处理")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(
            (message or "DeepSeek 需要登录或验证。")
            + "\n\n请直接在已打开的浏览器窗口里操作，不要关窗口；完成后点「继续」。"
        )
        cont = box.addButton("继续", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("取消任务", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is cont and isinstance(self._worker, VisionConversionWorker):
            self._worker.resume_after_user()
        elif isinstance(self._worker, VisionConversionWorker):
            self._worker.request_cancel()

    def _on_vision_figures(self, task_id: str, output_dir: str) -> None:
        dlg = VisionFigureDialog(Path(output_dir), self)
        dlg.exec()
        if isinstance(self._worker, VisionConversionWorker):
            self._worker.resume_after_user()

    def _open_vision_deepseek_ui(self) -> None:
        VisionDeepSeekUiDialog(self).exec()

    def _cancel(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.request_cancel()
            self.stage_label.setText("正在取消…")
            self._update_pipeline_from_stage("正在取消")

    def _on_task_status(self, task_id: str, status: str, message: str) -> None:
        task = self._tasks.get(task_id)
        if not task:
            return
        if status == TaskStatus.RUNNING.value:
            task.formula_recognized = None
            task.formula_post_ok = None
            task.formula_total = None
        task.status = status
        task.message = message
        if self._vision_run_active and message:
            # 仅用粗粒度任务文案更新顶栏，细步骤由日志 [PW]/[UI L2] 驱动
            if any(k in message for k in ("视觉转录", "浏览器", "渲染", "校验", "合并")):
                self.vision_status.set_task_message(message)
        row = self._row_of(task_id)
        if row >= 0:
            self._refresh_row(row, task)

    def _on_task_finished(
        self,
        task_id: str,
        ok: bool,
        md: str,
        out_dir: str,
        err: str,
        elapsed: float,
    ) -> None:
        task = self._tasks.get(task_id)
        if not task:
            return
        task.elapsed_sec = elapsed
        task.output_dir = Path(out_dir) if out_dir else None
        if ok:
            task.status = TaskStatus.DONE.value
            task.output_md = Path(md) if md else None
            task.error = ""
            if getattr(task, "workflow", "") == WorkflowChoice.VISION.value:
                self._load_task_vision_fidelity(task)
            else:
                self._load_task_formula_metrics(task)
        else:
            task.status = TaskStatus.FAILED.value
            task.error = err
            if getattr(task, "workflow", "") == WorkflowChoice.VISION.value:
                self._load_task_vision_fidelity(task)
            else:
                self._load_task_formula_metrics(task)
        self._done_count += 1
        self.command_bar.set_count(self._done_count, self._total_count)
        row = self._row_of(task_id)
        if row >= 0:
            self._refresh_row(row, task)

    def _on_worker_done(self) -> None:
        if self._vision_run_active:
            self._vision_run_active = False
            self.vision_status.append_line("高保真任务队列结束")
            self.vision_status.set_pipeline_stage("idle")
        self.command_bar.set_running(False)
        self.stage_label.setText("空闲")
        self._on_pipeline_stage("idle")
        if self._deepseek_limited_production():
            self._on_deepseek_state("warm")
        else:
            self._refresh_ds_badge()
        cfg = load_defaults()
        if cfg.get("notify"):
            try:
                from PySide6.QtWidgets import QSystemTrayIcon
                from PySide6.QtGui import QIcon

                if QSystemTrayIcon.isSystemTrayAvailable():
                    # 简单气泡；无托盘图标时忽略
                    pass
            except Exception:
                pass
            try:
                # Windows toast via powershell（失败无害）
                os.system(
                    'powershell -NoProfile -Command '
                    '"[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null" 2>nul'
                )
            except Exception:
                pass
        if cfg.get("auto_open"):
            done = [t for t in self._tasks.values() if t.status == TaskStatus.DONE.value and t.output_dir]
            if done:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(done[-1].output_dir)))

    def _clear(self) -> None:
        if self._worker and self._worker.isRunning():
            QMessageBox.warning(self, "提示", "转换进行中，无法清空。")
            return
        self._tasks.clear()
        self.table.setRowCount(0)
        self.drop.set_compact(False)
        self._refresh_empty_state()

    def _open_selected_md(self) -> None:
        t = self._selected_task()
        if not t or not t.output_md or not t.output_md.exists():
            QMessageBox.information(self, "提示", "请选择已完成且有 Markdown 输出的任务。")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(t.output_md)))

    def _open_selected_dir(self) -> None:
        t = self._selected_task()
        if not t or not t.output_dir:
            QMessageBox.information(self, "提示", "请选择已有输出目录的任务。")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(t.output_dir)))

    def _on_cell_clicked(self, row: int, col: int) -> None:
        if col != 8:
            return
        item = self.table.item(row, 0)
        if not item:
            return
        t = self._tasks.get(item.data(Qt.ItemDataRole.UserRole))
        if not t:
            return
        if t.status == TaskStatus.FAILED.value:
            QMessageBox.warning(self, "错误信息", t.error or "无错误信息")
        elif t.output_md and t.output_md.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(t.output_md)))

    def _on_stage(self, text: str) -> None:
        self.stage_label.setText(text)
        self._update_pipeline_from_stage(text)

    def _on_double_click(self, row: int, _col: int) -> None:
        item = self.table.item(row, 0)
        if not item:
            return
        t = self._tasks.get(item.data(Qt.ItemDataRole.UserRole))
        if not t:
            return
        if t.status == TaskStatus.FAILED.value:
            QMessageBox.warning(self, "错误信息", t.error or "无错误信息")
            return
        if t.output_md and t.output_md.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(t.output_md)))
            return
        if t.output_dir and t.output_dir.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(t.output_dir)))

    def _context_menu(self, pos) -> None:
        menu = QMenu(self)
        act_copy = menu.addAction("复制任务表（Markdown）")
        act_copy.setEnabled(self.table.rowCount() > 0)
        t = self._selected_task()
        act_rebuild_figs = None
        if t:
            menu.addSeparator()
            act_err = menu.addAction("查看错误")
            act_retry = menu.addAction("重试")
            act_mineru = menu.addAction("使用 MinerU 重新转换")
            act_md = menu.addAction("打开 Markdown")
            act_dir = menu.addAction("打开文件夹")
            if getattr(t, "workflow", "") == WorkflowChoice.VISION.value and t.output_dir:
                act_rebuild_figs = menu.addAction("仅重合并与裁图（不重跑浏览器）")
        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen == act_copy:
            self._copy_task_table_markdown()
            return
        if not t:
            return
        if chosen == act_err:
            QMessageBox.warning(self, "错误信息", t.error or "无错误信息")
        elif chosen == act_retry:
            was_done = t.status == TaskStatus.DONE.value
            t.status = TaskStatus.WAITING.value
            t.error = ""
            if getattr(t, "workflow", "") == WorkflowChoice.VISION.value:
                from app.utils.paths import vision_task_output_dir
                from app.vision_transcribe.manifest import should_force_vision_rerun

                out_root = Path(self.output_edit.text().strip() or ".")
                vis_out = t.output_dir or vision_task_output_dir(out_root, t.pdf_path)
                t.vision_force_rerun = should_force_vision_rerun(
                    vis_out,
                    checkbox=self.cb_vision_force_rerun.isChecked(),
                    task_was_done=was_done,
                )
            else:
                t.vision_force_rerun = False
            row = self._row_of(t.id)
            if row >= 0:
                self._refresh_row(row, t)
            self._start()
        elif chosen == act_mineru:
            t.engine = EngineChoice.MINERU.value
            t.status = TaskStatus.WAITING.value
            t.error = ""
            row = self._row_of(t.id)
            if row >= 0:
                self._refresh_row(row, t)
            self._start()
        elif chosen == act_md:
            self._open_selected_md()
        elif chosen == act_dir:
            self._open_selected_dir()
        elif act_rebuild_figs is not None and chosen == act_rebuild_figs:
            self._rebuild_vision_figures(t)

    def _rebuild_vision_figures(self, task: ConvertTask) -> None:
        if self._figure_rebuild_worker and self._figure_rebuild_worker.isRunning():
            QMessageBox.information(self, "提示", "正在重合并与裁图，请稍候…")
            return
        if not task.output_dir or not task.pdf_path.is_file():
            QMessageBox.warning(self, "提示", "缺少 PDF 或输出目录。")
            return
        cfg = VisionConfig(
            browser_mode=str(self.cmb_vision_browser.currentData() or "playwright"),
            images_scale=self._images_scale(),
            image_path_mode=self._image_path_mode(),
        )
        self._vision_run_active = True
        self.vision_status.set_active(True)
        self.vision_status.append_line("仅重合并与裁图（不重跑浏览器）…")
        worker = VisionFigureRebuildWorker(
            task.id,
            task.pdf_path,
            task.output_dir,
            config=cfg,
            parent=self,
        )
        self._figure_rebuild_worker = worker

        def _log(msg: str) -> None:
            if msg:
                self.vision_status.append_line(msg)

        worker.log_line.connect(_log)

        def _ok(tid: str, final_md: str) -> None:
            self._vision_run_active = False
            self.vision_status.append_line(f"裁图完成: {final_md}")
            task.output_md = Path(final_md)
            self._load_task_vision_fidelity(task)
            row = self._row_of(tid)
            if row >= 0:
                self._refresh_row(row, task)
            QMessageBox.information(self, "完成", f"已更新 Markdown 与 images/\n{final_md}")

        def _fail(tid: str, err: str) -> None:
            self._vision_run_active = False
            self.vision_status.append_line(f"裁图失败: {err}")
            QMessageBox.warning(self, "裁图失败", err)

        worker.finished_ok.connect(_ok)
        worker.failed.connect(_fail)
        worker.finished.connect(lambda: setattr(self, "_figure_rebuild_worker", None))
        worker.start()

    def _pick_output(self) -> None:
        start = self.output_edit.text().strip() or str(Path.home())
        d = QFileDialog.getExistingDirectory(
            self,
            "选择导出目录",
            start,
            QFileDialog.Option.ShowDirsOnly | QFileDialog.Option.DontResolveSymlinks,
        )
        if d:
            self.output_edit.setText(d)
            self._persist_output_dir()

    def _persist_output_dir(self) -> None:
        path = self.output_edit.text().strip()
        if path:
            settings().setValue("output_dir", path)

    def _open_output_root(self) -> None:
        path = self.output_edit.text().strip()
        if not path:
            QMessageBox.information(self, "提示", "请先指定导出目录。")
            return
        root = Path(path)
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            QMessageBox.warning(self, "导出目录", f"无法打开：\n{root}\n\n{e}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(root.resolve())))

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self)
        if dlg.exec():
            self._apply_settings_to_ui()

    def _open_formula_lab(self) -> None:
        from app.dialogs.formula_benchmark_dialog import FormulaBenchmarkDialog

        if self._bench_dialog is None:
            self._bench_dialog = FormulaBenchmarkDialog(self)
        self._bench_dialog.show()
        self._bench_dialog.raise_()
        self._bench_dialog.activateWindow()

    def _experiment_scan_roots(self) -> list[Path]:
        """诊断镜像目录 + 导出根目录 + 当前任务已完成目录（去重）。"""
        from app.utils.paths import EXPERIMENT_DIR, ensure_dirs

        ensure_dirs()
        roots: list[Path] = [EXPERIMENT_DIR]
        out = self.output_edit.text().strip()
        if out:
            roots.append(Path(out))
        for t in self._tasks.values():
            if t.output_dir and t.output_dir.exists():
                roots.append(t.output_dir)
                # 独立子文件夹时，父目录也扫一层
                parent = t.output_dir.parent
                if parent not in roots:
                    roots.append(parent)
        uniq: list[Path] = []
        seen: set[str] = set()
        for r in roots:
            key = str(r.resolve()) if r.exists() else str(r)
            if key in seen:
                continue
            seen.add(key)
            uniq.append(r)
        return uniq

    def _open_experiment_results(self) -> None:
        from app.dialogs.experiment_results_dialog import ExperimentResultsDialog

        roots = self._experiment_scan_roots()
        if self._experiment_dialog is None:
            self._experiment_dialog = ExperimentResultsDialog(self, roots=roots)
        else:
            self._experiment_dialog.set_roots(roots)
        self._experiment_dialog.show()
        self._experiment_dialog.raise_()
        self._experiment_dialog.activateWindow()

    def _open_experiment_cache(self) -> None:
        from app.dialogs.experiment_cache_dialog import ExperimentCacheDialog

        dlg = ExperimentCacheDialog(self)
        dlg.exec()

    def _on_log(self, line: str) -> None:
        self._log_dialog.append_line(line)

    def closeEvent(self, event) -> None:  # noqa: N802
        remove_listener(self._on_log)
        if self._worker and self._worker.isRunning():
            self._worker.request_cancel()
            self._worker.wait(3000)
        # 持久化当前界面选项
        s = settings()
        s.setValue("engine", self._current_engine() if self._current_engine() != "自动" else "自动")
        if self.rb_auto.isChecked():
            s.setValue("engine", "自动")
        s.setValue("output_dir", self.output_edit.text().strip())
        s.setValue("per_folder", self.cb_per_folder.isChecked())
        s.setValue("ocr_mode", self._ocr_mode())
        s.setValue("keep_images", True)
        s.setValue("export_md", self.cb_md.isChecked())
        s.setValue("export_raw_md", self.cb_raw_md.isChecked())
        s.setValue("export_repair_json", self.cb_repair_json.isChecked())
        s.setValue("export_conversion_log", self.cb_conversion_log.isChecked())
        s.setValue("export_manifest", self.cb_manifest.isChecked())
        s.setValue("export_formula_qa", self.cb_formula_qa.isChecked())
        s.setValue("export_timings", self.cb_timings.isChecked())
        s.setValue("keep_tables", self.cb_tables.isChecked())
        s.setValue("keep_formulas", self.cb_formulas.isChecked())
        s.setValue("formula_recovery_preset", self._formula_recovery_preset())
        s.setValue("deepseek_limited_production", self._deepseek_limited_production())
        s.setValue("keep_refs", self.cb_refs.isChecked())
        s.setValue("images_scale", self._images_scale())
        s.setValue("image_path_mode", self._image_path_mode())
        # Phase 5I：GUI 关闭不 terminate DeepSeek Worker（模型常驻本机 session）
        try:
            from app.ocr.deepseek_worker_client import reset_deepseek_worker_client

            reset_deepseek_worker_client(kill_worker=False)
        except Exception:
            pass
        super().closeEvent(event)
