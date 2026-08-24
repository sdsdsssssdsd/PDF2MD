"""Formula Benchmark Lab：对照 scale / padding / preprocess，不进日常转换。"""
from __future__ import annotations

import io
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.ui.fonts import mono_font
from app.ui.widgets.collapsible import CollapsibleSection
from app.ui.widgets.notice import Notice
from app.ui.widgets.section_card import SectionCard
from app.ui.widgets.status_badge import StatusBadge
from app.formula.benchmark import (
    PREPROCESS_CHOICES,
    SCALE_CHOICES,
    BenchmarkCase,
    BenchmarkConfig,
    expand_matrix,
    list_pdf_equations,
    preview_crop,
    run_benchmark,
    save_benchmark_run,
)
from app.utils.paths import BENCHMARK_CORPUS, BENCHMARK_DIR, ensure_dirs


def _pil_to_pixmap(img, max_w: int = 560, max_h: int = 240) -> QPixmap:
    if img is None:
        return QPixmap()
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qimg = QImage.fromData(buf.getvalue())
    pix = QPixmap.fromImage(qimg)
    return pix.scaled(max_w, max_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)


class _BenchWorker(QThread):
    progress = Signal(str)
    finished_ok = Signal(dict)
    failed = Signal(str)

    def __init__(self, case: BenchmarkCase, configs: list[BenchmarkConfig]) -> None:
        super().__init__()
        self._case = case
        self._configs = configs
        self._cancel = False

    def request_cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            payload = run_benchmark(
                self._case,
                self._configs,
                progress=lambda m: self.progress.emit(m),
                should_cancel=lambda: self._cancel,
            )
            self.finished_ok.emit(payload)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(f"{type(e).__name__}: {e}")


class FormulaBenchmarkDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("公式实验室 / Formula Benchmark")
        self.resize(1280, 820)
        ensure_dirs()
        self._eq_index: dict = {}
        self._worker: _BenchWorker | None = None
        self._last_payload: dict | None = None
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.addWidget(
            Notice(
                "实验工作台 · 不是转换设置",
                "用来对比裁图参数收益。日常转换请用主窗口的快速 / 均衡 / 精细。",
                tone="info",
            )
        )

        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self._left_panel())
        split.addWidget(self._mid_panel())
        split.addWidget(self._right_panel())
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 4)
        split.setStretchFactor(2, 3)
        root.addWidget(split, 2)

        chips_row = QHBoxLayout()
        chips_row.addWidget(QLabel("Benchmark Matrix"))
        self.lbl_chips = QLabel()
        self.lbl_chips.setProperty("role", "muted")
        chips_row.addWidget(self.lbl_chips, 1)
        root.addLayout(chips_row)
        root.addWidget(self._matrix_bar())

        lower = QSplitter(Qt.Orientation.Horizontal)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["配置", "OCR 秒", "最终决策", "Gain", "Context", "LaTeX"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.itemSelectionChanged.connect(self._on_table_row)
        lower.addWidget(self.table)
        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setPlaceholderText("选中一行查看 Validator / Corruption / Gold 等完整诊断。")
        lower.addWidget(self.detail)
        lower.setStretchFactor(0, 3)
        lower.setStretchFactor(1, 2)
        root.addWidget(lower, 3)

        self.pareto = QLabel("Pareto：跑完矩阵后显示 accept 率 vs 耗时。")
        self.pareto.setWordWrap(True)
        self.pareto.setProperty("role", "muted")
        root.addWidget(self.pareto)

        btn_row = QHBoxLayout()
        self.btn_run = QPushButton("Run benchmark")
        self.btn_run.setProperty("variant", "primary")
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setProperty("variant", "danger")
        self.btn_save = QPushButton("保存到 runs/")
        self.btn_folder = QPushButton("打开实验室文件夹")
        self.btn_cancel.setEnabled(False)
        self.btn_save.setEnabled(False)
        self.btn_run.clicked.connect(self._run)
        self.btn_cancel.clicked.connect(self._cancel)
        self.btn_save.clicked.connect(self._save)
        self.btn_folder.clicked.connect(self._open_folder)
        btn_row.addWidget(self.btn_run)
        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_save)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_folder)
        root.addLayout(btn_row)

        self.status = QLabel("就绪。1 Target → 2 预览裁图 → 3 Run benchmark。")
        self.status.setProperty("role", "muted")
        root.addWidget(self.status)
        mono = mono_font()
        for w in (self.parser_latex, self.gold_latex, self.live_latex, self.detail):
            w.setFont(mono)
        self._refresh_chips()

    def _left_panel(self) -> QWidget:
        box = SectionCard("1 · Target", "PDF、页码、Eq.n、bbox、前后文")
        form = QFormLayout()
        pdf_row = QHBoxLayout()
        self.pdf_edit = QLineEdit()
        self.pdf_edit.setPlaceholderText("PDF 路径")
        b1 = QPushButton("打开…")
        b2 = QPushButton("corpus")
        b1.clicked.connect(self._browse_pdf)
        b2.clicked.connect(self._browse_corpus)
        pdf_row.addWidget(self.pdf_edit)
        pdf_row.addWidget(b1)
        pdf_row.addWidget(b2)
        form.addRow("PDF", pdf_row)

        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.setMaximum(1)
        self.page_spin.valueChanged.connect(self._fill_eq_combo)
        form.addRow("页码（从 1）", self.page_spin)

        eq_row = QHBoxLayout()
        self.eq_combo = QComboBox()
        self.eq_combo.setEditable(True)
        self.eq_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        load_btn = QPushButton("扫描编号")
        load_btn.clicked.connect(self._scan_pdf)
        eq_row.addWidget(self.eq_combo)
        eq_row.addWidget(load_btn)
        form.addRow("Eq. (n)", eq_row)

        self.bbox_edit = QLineEdit()
        self.bbox_edit.setPlaceholderText("可选：x0,y0,x1,y1（留空则按编号裁）")
        form.addRow("bbox", self.bbox_edit)

        self.ctx_before = QTextEdit()
        self.ctx_before.setPlaceholderText("公式前文，例如：Recall can be calculated using Eq. (4):")
        self.ctx_before.setMaximumHeight(70)
        form.addRow("前文", self.ctx_before)
        self.ctx_after = QTextEdit()
        self.ctx_after.setMaximumHeight(50)
        form.addRow("后文", self.ctx_after)
        box.body.addLayout(form)
        return box

    def _mid_panel(self) -> QWidget:
        box = SectionCard("2 · Crop & Ground Truth", "大裁图预览、Parser、Gold")
        prev_row = QHBoxLayout()
        self.btn_preview = QPushButton("预览裁图")
        self.btn_preview.clicked.connect(self._preview)
        prev_row.addWidget(self.btn_preview)
        prev_row.addStretch(1)
        box.body.addLayout(prev_row)
        self.crop_label = QLabel("尚无裁图")
        self.crop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.crop_label.setMinimumHeight(200)
        self.crop_label.setProperty("uiCard", True)
        box.body.addWidget(self.crop_label)
        self.parser_latex = QTextEdit()
        self.parser_latex.setPlaceholderText("Parser 原公式 LaTeX（可从 .raw.md 粘贴）")
        self.parser_latex.setMaximumHeight(90)
        box.body.addWidget(QLabel("Parser 原公式"))
        box.body.addWidget(self.parser_latex)
        self.gold_latex = QTextEdit()
        self.gold_latex.setPlaceholderText("可选：人工正确答案。有它才能统计「真恢复」。")
        self.gold_latex.setMaximumHeight(70)
        box.body.addWidget(QLabel("Gold（可选）"))
        box.body.addWidget(self.gold_latex)
        return box

    def _right_panel(self) -> QWidget:
        box = SectionCard("3 · Recognition", "ACCEPT / REJECT、耗时、Context、LaTeX")
        self.live_badge = StatusBadge("—", "neutral")
        box.body.addWidget(self.live_badge)
        self.live_decision = QLabel("—")
        self.live_decision.setProperty("role", "title")
        box.body.addWidget(self.live_decision)
        self.live_meta = QLabel("耗时 / Validator / Corruption / Context")
        self.live_meta.setWordWrap(True)
        self.live_meta.setProperty("role", "muted")
        box.body.addWidget(self.live_meta)
        self.notice_conflict = Notice(
            "Context conflict",
            "ocr_context_conflict 为 HARD REJECT，与普通 validator fail 不同级。",
            tone="danger",
        )
        self.notice_conflict.hide()
        box.body.addWidget(self.notice_conflict)
        self.live_latex = QTextEdit()
        self.live_latex.setReadOnly(True)
        box.body.addWidget(self.live_latex)
        return box

    def _matrix_bar(self) -> QWidget:
        box = CollapsibleSection("Benchmark Matrix · 展开选择配置")
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("scale"))
        self.cb_scales: dict[float, QCheckBox] = {}
        for s in SCALE_CHOICES:
            cb = QCheckBox(f"{s:g}×")
            cb.setChecked(s in (2.0, 2.5))
            cb.toggled.connect(self._refresh_chips)
            self.cb_scales[s] = cb
            row1.addWidget(cb)
        row1.addStretch(1)
        box.body.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("padding"))
        self.cb_pads: dict[str, QCheckBox] = {}
        for name, default in (("small", False), ("medium", True), ("large", False)):
            cb = QCheckBox(name)
            cb.setChecked(default)
            cb.toggled.connect(self._refresh_chips)
            self.cb_pads[name] = cb
            row2.addWidget(cb)
        row2.addStretch(1)
        box.body.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("preprocess"))
        self.cb_preps: dict[str, QCheckBox] = {}
        for name in PREPROCESS_CHOICES:
            cb = QCheckBox(name)
            cb.setChecked(name == "original")
            cb.toggled.connect(self._refresh_chips)
            self.cb_preps[name] = cb
            row3.addWidget(cb)
        row3.addStretch(1)
        box.body.addLayout(row3)

        self.cb_full = QCheckBox("完整矩阵（4×3×3 = 36 次 OCR，高成本）")
        self.cb_full.toggled.connect(self._toggle_full)
        box.body.addWidget(self.cb_full)
        self.warn_full = Notice(
            "高成本选项",
            "完整矩阵会跑 36 次公式 OCR，墙钟显著上升。仅在对照实验时勾选。",
            tone="warning",
        )
        self.warn_full.hide()
        box.body.addWidget(self.warn_full)
        return box

    def _refresh_chips(self, *_args) -> None:
        scales = [f"{s:g}×" for s, cb in self.cb_scales.items() if cb.isChecked()]
        pads = [n for n, cb in self.cb_pads.items() if cb.isChecked()]
        preps = [n for n, cb in self.cb_preps.items() if cb.isChecked()]
        n = len(scales) * len(pads) * len(preps)
        self.lbl_chips.setText("  ·  ".join(scales + pads + preps) + f"   （{n} 组）")

    def _toggle_full(self, on: bool) -> None:
        self.warn_full.setVisible(on)
        if not on:
            self._refresh_chips()
            return
        for cb in self.cb_scales.values():
            cb.setChecked(True)
        for cb in self.cb_pads.values():
            cb.setChecked(True)
        for cb in self.cb_preps.values():
            cb.setChecked(True)
        self._refresh_chips()

    def _case(self) -> BenchmarkCase:
        bbox = None
        raw = self.bbox_edit.text().strip()
        if raw:
            parts = [float(x.strip()) for x in raw.replace("，", ",").split(",")]
            if len(parts) != 4:
                raise ValueError("bbox 需要 4 个数：x0,y0,x1,y1")
            bbox = (parts[0], parts[1], parts[2], parts[3])
        return BenchmarkCase(
            pdf_path=self.pdf_edit.text().strip(),
            page=max(0, self.page_spin.value() - 1),
            eq_number=self.eq_combo.currentText().strip().strip("()"),
            bbox=bbox,
            parser_latex=self.parser_latex.toPlainText().strip(),
            context_before=self.ctx_before.toPlainText().strip(),
            context_after=self.ctx_after.toPlainText().strip(),
            gold_latex=self.gold_latex.toPlainText().strip(),
        )

    def _selected_configs(self) -> list[BenchmarkConfig]:
        scales = [s for s, cb in self.cb_scales.items() if cb.isChecked()]
        pads = [n for n, cb in self.cb_pads.items() if cb.isChecked()]
        preps = [n for n, cb in self.cb_preps.items() if cb.isChecked()]
        if not scales or not pads or not preps:
            raise ValueError("scale / padding / preprocess 至少各选一项")
        return expand_matrix(scales=scales, paddings=pads, preprocesses=preps)

    def _browse_pdf(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择 PDF", str(BENCHMARK_CORPUS), "PDF (*.pdf)")
        if path:
            self.pdf_edit.setText(path)
            self._scan_pdf()

    def _browse_corpus(self) -> None:
        ensure_dirs()
        path, _ = QFileDialog.getOpenFileName(
            self, "从 corpus 选 PDF", str(BENCHMARK_CORPUS), "PDF (*.pdf)"
        )
        if path:
            self.pdf_edit.setText(path)
            self._scan_pdf()

    def _scan_pdf(self) -> None:
        path = self.pdf_edit.text().strip()
        if not path:
            return
        try:
            info = list_pdf_equations(path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "扫描失败", str(e))
            return
        self._eq_index = info
        self.page_spin.setMaximum(max(1, int(info["page_count"])))
        self._fill_eq_combo()
        n = len(info.get("all") or [])
        self.status.setText(f"已扫描 {info['page_count']} 页，右侧方程编号 {n} 个。")

    def _fill_eq_combo(self) -> None:
        page0 = self.page_spin.value() - 1
        by_page = (self._eq_index or {}).get("by_page") or {}
        # JSON keys may be str if ever serialized; here they are int
        nums = by_page.get(page0) or by_page.get(str(page0)) or []
        cur = self.eq_combo.currentText()
        self.eq_combo.blockSignals(True)
        self.eq_combo.clear()
        self.eq_combo.addItems([str(x) for x in nums])
        if cur:
            self.eq_combo.setEditText(cur)
        elif nums:
            self.eq_combo.setCurrentIndex(0)
        self.eq_combo.blockSignals(False)

    def _preview(self) -> None:
        try:
            case = self._case()
            if not case.pdf_path:
                raise ValueError("请先选择 PDF")
            img, page, bbox = preview_crop(case, BenchmarkConfig(scale=2.0, padding="medium"))
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "预览失败", str(e))
            return
        self.crop_label.setPixmap(_pil_to_pixmap(img))
        self.bbox_edit.setText(",".join(f"{x:.1f}" for x in bbox))
        self.page_spin.setValue(page + 1)
        self.status.setText(f"裁图预览 page={page + 1} bbox={tuple(round(x, 1) for x in bbox)}")

    def _run(self) -> None:
        try:
            case = self._case()
            if not case.pdf_path:
                raise ValueError("请先选择 PDF")
            configs = self._selected_configs()
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "无法开始", str(e))
            return
        n = len(configs)
        if n >= 36:
            ok = QMessageBox.question(
                self,
                "高成本：36 次 OCR",
                f"将调用公式 OCR {n} 次。这是显式高成本选项，墙钟会明显上升。继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if ok != QMessageBox.StandardButton.Yes:
                return
        elif n > 12:
            ok = QMessageBox.question(
                self,
                "OCR 次数",
                f"将调用公式 OCR {n} 次（首次还会加载模型，可能稍慢）。继续？",
            )
            if ok != QMessageBox.StandardButton.Yes:
                return
        self.table.setRowCount(0)
        self._last_payload = None
        self.btn_save.setEnabled(False)
        self.btn_run.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.status.setText(f"开始 {n} 组… 首次加载 UniMERNet 可能稍慢（之后走 GPU）")
        self._worker = _BenchWorker(case, configs)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_done)
        self._worker.failed.connect(self._on_fail)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _cancel(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.request_cancel()
            self.status.setText("正在取消…")

    def _on_progress(self, msg: str) -> None:
        self.status.setText(msg)

    def _apply_live_row(self, r: dict) -> None:
        decision = str(r.get("decision") or "").lower()
        self.live_decision.setText(decision.upper() or "—")
        if decision == "accept":
            self.live_badge.set_status("ACCEPT", "success")
        elif "conflict" in str(r.get("gate_reason") or r.get("reasons") or "").lower() or (
            "conflict" in decision
        ):
            self.live_badge.set_status("REJECT · CONFLICT", "danger")
        else:
            self.live_badge.set_status("REJECT", "danger")
        reasons = str(r.get("gate_reason") or r.get("reasons") or r.get("context_reason") or "")
        conflict = "conflict" in reasons.lower() or "conflict" in decision
        self.notice_conflict.setVisible(conflict)
        self.live_meta.setText(
            f"{r.get('config_label')}  ·  {r.get('ocr_seconds')}s  ·  "
            f"val={r.get('validator_score')}  corr={r.get('corruption_score')}  "
            f"ctx={r.get('context_overlap')}"
        )
        self.live_latex.setPlainText(r.get("latex") or r.get("error") or "")
        gold = r.get("gold_match", "—")
        self.detail.setPlainText(
            f"config: {r.get('config_label')}\n"
            f"decision: {r.get('decision')}\n"
            f"ocr_seconds: {r.get('ocr_seconds')}\n"
            f"gain: {r.get('gain')}\n"
            f"validator_score: {r.get('validator_score')}\n"
            f"corruption_score: {r.get('corruption_score')}\n"
            f"context_overlap: {r.get('context_overlap')}\n"
            f"gold_match: {gold}\n"
            f"reasons: {reasons}\n\n"
            f"LaTeX:\n{r.get('latex') or r.get('error') or ''}"
        )

    def _on_table_row(self) -> None:
        rows = (self._last_payload or {}).get("rows") or []
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            return
        idx = sel[0].row()
        if 0 <= idx < len(rows):
            self._apply_live_row(rows[idx])

    def _on_done(self, payload: dict) -> None:
        self._last_payload = payload
        rows = payload.get("rows") or []
        self.table.setRowCount(len(rows))
        last = rows[-1] if rows else None
        for i, r in enumerate(rows):
            vals = [
                r.get("config_label", ""),
                f"{r.get('ocr_seconds', 0):.2f}",
                r.get("decision", ""),
                f"{r.get('gain', 0):.2f}",
                f"{r.get('context_overlap', 0):.2f}",
                (r.get("latex") or r.get("error") or "")[:240],
            ]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(str(v))
                self.table.setItem(i, j, item)
        if last:
            self._apply_live_row(last)
            self.table.selectRow(len(rows) - 1)
        p = payload.get("pareto") or {}
        fa = p.get("fastest_accept") or {}
        self.pareto.setText(
            f"Pareto：{p.get('n', 0)} 组，accept {p.get('accept_n', 0)} "
            f"（{p.get('accept_rate', 0):.0%}），"
            f"gold 命中 {p.get('gold_match_n', 0)}，"
            f"均时 {p.get('mean_ocr_seconds', 0)}s。"
            + (
                f"  最快 accept：{fa.get('label')} ({fa.get('ocr_seconds')}s)。"
                if fa
                else "  没有任何配置被 GainEvaluator 接受。"
            )
            + "  不要用「大报错消失了」当准确率。"
        )
        self.btn_save.setEnabled(bool(rows))
        self.status.setText("完成。可保存 JSON 到 debug/formula_benchmark/runs/")

    def _on_fail(self, err: str) -> None:
        QMessageBox.warning(self, "Benchmark 失败", err)
        self.status.setText(err)

    def _on_worker_finished(self) -> None:
        self.btn_run.setEnabled(True)
        self.btn_cancel.setEnabled(False)

    def _save(self) -> None:
        if not self._last_payload:
            return
        path = save_benchmark_run(self._last_payload)
        self.status.setText(f"已保存 {path}")
        QMessageBox.information(self, "已保存", str(path))

    def _open_folder(self) -> None:
        ensure_dirs()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(BENCHMARK_DIR)))

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._worker and self._worker.isRunning():
            self._worker.request_cancel()
            self._worker.wait(4000)
        super().closeEvent(event)
