"""主窗口。"""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from app.dialogs.log_dialog import LogDialog
from app.dialogs.settings_dialog import load_defaults, settings, SettingsDialog
from app.drop_widget import DropWidget
from app.task_model import ConvertTask, EngineChoice, TaskStatus
from app.utils.logger import add_listener, get_logger, remove_listener
from app.utils.paths import ensure_dirs
from app.workers.docling_worker import ConversionWorker

try:
    from pypdf import PdfReader
except Exception:  # noqa: BLE001
    PdfReader = None  # type: ignore


class MainWindow(QMainWindow):
    COLS = ["文件名", "大小", "页数", "引擎", "状态", "耗时", "输出", "错误"]

    def __init__(self) -> None:
        super().__init__()
        ensure_dirs()
        self.setWindowTitle("PDF → Markdown")
        self.resize(1000, 700)

        self._tasks: dict[str, ConvertTask] = {}
        self._worker: ConversionWorker | None = None
        self._log_dialog = LogDialog(self)
        self._done_count = 0
        self._total_count = 0

        self._build_ui()
        self._apply_settings_to_ui()

        get_logger()
        add_listener(self._on_log)
        get_logger().info("GUI 启动")

    def _build_ui(self) -> None:
        tb = QToolBar()
        self.addToolBar(tb)
        act_settings = QAction("设置", self)
        act_log = QAction("查看日志", self)
        act_settings.triggered.connect(self._open_settings)
        act_log.triggered.connect(self._log_dialog.show)
        tb.addAction(act_settings)
        tb.addAction(act_log)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        title = QLabel("PDF → Markdown")
        title.setStyleSheet("font-size: 22px; font-weight: 600;")
        subtitle = QLabel("学术论文转换工具")
        subtitle.setStyleSheet("color: #666; margin-bottom: 8px;")
        root.addWidget(title)
        root.addWidget(subtitle)

        self.drop = DropWidget()
        self.drop.files_dropped.connect(self._on_drop)
        root.addWidget(self.drop)

        # 引擎
        eng_row = QHBoxLayout()
        eng_row.addWidget(QLabel("转换引擎："))
        self.rb_docling = QRadioButton("Docling（推荐）")
        self.rb_mineru = QRadioButton("MinerU")
        self.rb_auto = QRadioButton("自动选择")
        self.rb_docling.setChecked(True)
        self._eng_group = QButtonGroup(self)
        for b in (self.rb_docling, self.rb_mineru, self.rb_auto):
            self._eng_group.addButton(b)
            eng_row.addWidget(b)
        eng_row.addStretch(1)
        root.addLayout(eng_row)

        # 导出组件（每篇论文）
        export_row = QHBoxLayout()
        export_row.addWidget(QLabel("导出组件："))
        self.cb_images = QCheckBox("图片")
        self.cb_images.setChecked(True)
        self.cb_images.setEnabled(False)
        self.cb_images.setToolTip("图片为必要组件，始终导出，不可取消")
        self.cb_md = QCheckBox("Markdown（.md）")
        self.cb_md.setChecked(True)
        self.cb_md.setToolTip("最终 Markdown 正文（默认导出）")
        self.cb_raw_md = QCheckBox("原始解析（.raw.md）")
        self.cb_raw_md.setChecked(False)
        self.cb_raw_md.setToolTip("保留解析器原始 Markdown，便于对照修复效果")
        self.cb_repair_json = QCheckBox("修复报告（.repair.json）")
        self.cb_repair_json.setChecked(False)
        self.cb_repair_json.setToolTip("保留 RepairPipeline 质量/修复报告")
        for c in (self.cb_images, self.cb_md, self.cb_raw_md, self.cb_repair_json):
            export_row.addWidget(c)
        export_row.addStretch(1)
        root.addLayout(export_row)

        # 识别选项
        opt = QHBoxLayout()
        opt.addWidget(QLabel("识别："))
        self.cb_tables = QCheckBox("表格")
        self.cb_formulas = QCheckBox("数学公式")
        self.cb_refs = QCheckBox("参考文献")
        for c in (self.cb_tables, self.cb_formulas, self.cb_refs):
            c.setChecked(True)
            opt.addWidget(c)
        opt.addStretch(1)
        root.addLayout(opt)

        img_row = QHBoxLayout()
        img_row.addWidget(QLabel("图片质量："))
        self.rb_img_fast = QRadioButton("快速")
        self.rb_img_std = QRadioButton("标准")
        self.rb_img_hq = QRadioButton("高清")
        self.rb_img_std.setChecked(True)
        self.rb_img_fast.setToolTip("scale=1，速度快，插图较糊")
        self.rb_img_std.setToolTip("scale=2，清晰与速度平衡（推荐）")
        self.rb_img_hq.setToolTip("scale=3，最清晰，转换更慢、文件更大")
        self._img_group = QButtonGroup(self)
        for b in (self.rb_img_fast, self.rb_img_std, self.rb_img_hq):
            self._img_group.addButton(b)
            img_row.addWidget(b)
        img_row.addStretch(1)
        root.addLayout(img_row)

        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("图片路径："))
        self.rb_path_rel = QRadioButton("相对路径")
        self.rb_path_abs = QRadioButton("绝对路径")
        self.rb_path_rel.setChecked(True)
        self.rb_path_rel.setToolTip("如 images/xxx.png，便于移动整个输出文件夹")
        self.rb_path_abs.setToolTip("如 D:\\...\\images\\xxx.png")
        self._path_group = QButtonGroup(self)
        for b in (self.rb_path_rel, self.rb_path_abs):
            self._path_group.addButton(b)
            path_row.addWidget(b)
        path_row.addStretch(1)
        root.addLayout(path_row)

        ocr_row = QHBoxLayout()
        ocr_row.addWidget(QLabel("OCR："))
        self.rb_ocr_auto = QRadioButton("自动")
        self.rb_ocr_force = QRadioButton("强制 OCR")
        self.rb_ocr_off = QRadioButton("禁用 OCR")
        self.rb_ocr_auto.setChecked(True)
        self._ocr_group = QButtonGroup(self)
        for b in (self.rb_ocr_auto, self.rb_ocr_force, self.rb_ocr_off):
            self._ocr_group.addButton(b)
            ocr_row.addWidget(b)
        ocr_row.addStretch(1)
        root.addLayout(ocr_row)

        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("导出目录："))
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("转换结果保存到此目录（可浏览或直接输入）")
        self.output_edit.setToolTip(
            "指定 Markdown / 图片 / repair 报告的导出根目录。\n"
            "勾选「每篇论文建立独立文件夹」时，会在其下再建以 PDF 文件名命名的子目录。"
        )
        self.output_edit.editingFinished.connect(self._persist_output_dir)
        btn_out = QPushButton("浏览...")
        btn_out.setToolTip("选择或新建导出目录")
        btn_out.clicked.connect(self._pick_output)
        btn_open_out = QPushButton("打开")
        btn_open_out.setToolTip("在资源管理器中打开当前导出目录")
        btn_open_out.clicked.connect(self._open_output_root)
        self.cb_per_folder = QCheckBox("每篇论文建立独立文件夹")
        self.cb_per_folder.setChecked(True)
        out_row.addWidget(self.output_edit, 1)
        out_row.addWidget(btn_out)
        out_row.addWidget(btn_open_out)
        out_row.addWidget(self.cb_per_folder)
        root.addLayout(out_row)

        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table.cellDoubleClicked.connect(self._on_double_click)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.table, 1)

        btn_row = QHBoxLayout()
        self.btn_start = QPushButton("开始转换")
        self.btn_cancel = QPushButton("取消")
        self.btn_clear = QPushButton("清空列表")
        self.btn_open_md = QPushButton("打开 Markdown")
        self.btn_open_dir = QPushButton("打开文件夹")
        self.btn_start.clicked.connect(self._start)
        self.btn_cancel.clicked.connect(self._cancel)
        self.btn_clear.clicked.connect(self._clear)
        self.btn_open_md.clicked.connect(self._open_selected_md)
        self.btn_open_dir.clicked.connect(self._open_selected_dir)
        self.btn_cancel.setEnabled(False)
        for b in (
            self.btn_start,
            self.btn_cancel,
            self.btn_clear,
            self.btn_open_md,
            self.btn_open_dir,
        ):
            btn_row.addWidget(b)
        btn_row.addStretch(1)
        root.addLayout(btn_row)

        self.stage_label = QLabel("就绪")
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # 不确定进度，避免伪造百分比
        self.progress.setVisible(False)
        self.count_label = QLabel("已完成 0 / 0")
        root.addWidget(self.stage_label)
        root.addWidget(self.progress)
        root.addWidget(self.count_label)

    def _apply_settings_to_ui(self) -> None:
        cfg = load_defaults()
        self.output_edit.setText(str(cfg["output_dir"]))
        self.cb_per_folder.setChecked(bool(cfg["per_folder"]))
        eng = str(cfg["engine"])
        if eng == "MinerU":
            self.rb_mineru.setChecked(True)
        elif eng == "自动":
            self.rb_auto.setChecked(True)
        else:
            self.rb_docling.setChecked(True)
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
        self.cb_tables.setChecked(bool(cfg["keep_tables"]))
        self.cb_formulas.setChecked(bool(cfg["keep_formulas"]))
        self.cb_refs.setChecked(bool(cfg["keep_refs"]))
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

    def _images_scale(self) -> float:
        if self.rb_img_fast.isChecked():
            return 1.0
        if self.rb_img_hq.isChecked():
            return 3.0
        return 2.0

    def _image_path_mode(self) -> str:
        return "absolute" if self.rb_path_abs.isChecked() else "relative"

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
        task = ConvertTask(pdf_path=pdf, engine=self._current_engine(), pages=pages)
        self._tasks[tid] = task
        row = self.table.rowCount()
        self.table.insertRow(row)
        self._refresh_row(row, task)

    def _row_of(self, task_id: str) -> int:
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == task_id:
                return r
        return -1

    def _refresh_row(self, row: int, task: ConvertTask) -> None:
        vals = [
            task.name,
            task.size_label,
            str(task.pages) if task.pages is not None else "-",
            task.engine,
            task.status,
            f"{task.elapsed_sec:.1f}s" if task.elapsed_sec is not None else "-",
            "打开" if task.output_md else "-",
            (task.error[:80] + "…") if len(task.error) > 80 else task.error,
        ]
        for c, v in enumerate(vals):
            item = QTableWidgetItem(v)
            if c == 0:
                item.setData(Qt.ItemDataRole.UserRole, task.id)
            self.table.setItem(row, c, item)

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
        waiting = [t for t in self._tasks.values() if t.status in (TaskStatus.WAITING.value, TaskStatus.FAILED.value)]
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

        # 更新引擎选择到任务
        eng = self._current_engine()
        for t in waiting:
            if t.status == TaskStatus.WAITING.value:
                t.engine = eng

        self._done_count = 0
        self._total_count = len(waiting)
        self.count_label.setText(f"已完成 0 / {self._total_count}")
        self.progress.setVisible(True)
        self.btn_start.setEnabled(False)
        self.btn_cancel.setEnabled(True)

        # V1：串行（默认 1），GPU 友好
        self._worker = ConversionWorker(
            waiting,
            output_root=out_root,
            per_folder=self.cb_per_folder.isChecked(),
            ocr_mode=self._ocr_mode(),
            keep_images=True,  # 图片为必要组件
            keep_tables=self.cb_tables.isChecked(),
            keep_formulas=self.cb_formulas.isChecked(),
            images_scale=self._images_scale(),
            image_path_mode=self._image_path_mode(),
            export_md=self.cb_md.isChecked(),
            export_raw_md=self.cb_raw_md.isChecked(),
            export_repair_json=self.cb_repair_json.isChecked(),
        )
        self._worker.task_status.connect(self._on_task_status)
        self._worker.task_finished.connect(self._on_task_finished)
        self._worker.log_line.connect(self._on_log)
        self._worker.stage.connect(self.stage_label.setText)
        self._worker.finished.connect(self._on_worker_done)
        self._worker.start()

    def _cancel(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.request_cancel()
            self.stage_label.setText("正在取消...")

    def _on_task_status(self, task_id: str, status: str, message: str) -> None:
        task = self._tasks.get(task_id)
        if not task:
            return
        task.status = status
        task.message = message
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
            task.output_md = Path(md)
            task.error = ""
        else:
            task.status = TaskStatus.FAILED.value
            task.error = err
        self._done_count += 1
        self.count_label.setText(f"已完成 {self._done_count} / {self._total_count}")
        row = self._row_of(task_id)
        if row >= 0:
            self._refresh_row(row, task)

    def _on_worker_done(self) -> None:
        self.progress.setVisible(False)
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.stage_label.setText("空闲")
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

    def _on_double_click(self, row: int, _col: int) -> None:
        item = self.table.item(row, 0)
        if not item:
            return
        t = self._tasks.get(item.data(Qt.ItemDataRole.UserRole))
        if t and t.output_dir and t.output_dir.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(t.output_dir)))

    def _context_menu(self, pos) -> None:
        t = self._selected_task()
        if not t:
            return
        menu = QMenu(self)
        act_err = menu.addAction("查看错误")
        act_retry = menu.addAction("重试")
        act_mineru = menu.addAction("使用 MinerU 重新转换")
        act_md = menu.addAction("打开 Markdown")
        act_dir = menu.addAction("打开文件夹")
        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen == act_err:
            QMessageBox.warning(self, "错误信息", t.error or "无错误信息")
        elif chosen == act_retry:
            t.status = TaskStatus.WAITING.value
            t.error = ""
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
        s.setValue("keep_tables", self.cb_tables.isChecked())
        s.setValue("keep_formulas", self.cb_formulas.isChecked())
        s.setValue("keep_refs", self.cb_refs.isChecked())
        s.setValue("images_scale", self._images_scale())
        s.setValue("image_path_mode", self._image_path_mode())
        super().closeEvent(event)
