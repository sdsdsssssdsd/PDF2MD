# -*- coding: utf-8 -*-
"""实验结果对话框：全量决策表 + 动态 X 轴图表 + 复制表格 Markdown。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCharts import (
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QChart,
    QChartView,
    QLineSeries,
    QValueAxis,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QClipboard, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.diagnostics.experiment_report import (
    ExperimentBatch,
    collect_experiment_results,
    format_experiment_markdown,
    rows_for_latest_batch,
)
from app.ui.charts import apply_chart_theme, colorize_bar_set
from app.ui.fonts import mono_font
from app.ui.identity import BATCH_INDEX_ROLE, batch_index_from_item
from app.ui.widgets.metric_card import MetricCard
from app.ui.widgets.notice import Notice

_BATCH_INDEX_ROLE = BATCH_INDEX_ROLE
CORE_COLUMNS = [
    "Document",
    "run_id",
    "attempted",
    "accepted",
    "rejected",
    "accept_rate",
    "sec/accept",
    "profile",
    "total(s)",
]
_CORE_COLS = {0, 1, 2, 3, 4, 5, 7, 8, 11}

_TABLE_COLS = [
    "Document",
    "run_id",
    "attempted",
    "accepted",
    "rejected",
    "accept_rate",
    "cost/accept",
    "sec/accept",
    "profile",
    "first→last",
    "curve_auc",
    "total(s)",
    "docling(s)",
    "asset(s)",
    "repair(s)",
    "cold(s)",
    "ocr_infer(s)",
    "ds_load(s)",
]


def _short(name: str, n: int = 18) -> str:
    return name if len(name) <= n else name[: n - 1] + "…"


def _f(v: float | None, digits: int = 1) -> str:
    if v is None:
        return ""
    return f"{v:.{digits}f}"


class ExperimentResultsDialog(QDialog):
    def __init__(
        self,
        parent=None,
        *,
        roots: list[Path | str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("实验结果")
        self.resize(1280, 820)
        self._roots = [Path(r) for r in (roots or []) if r]
        self._batch: ExperimentBatch | None = None
        self._md = ""
        self._build()
        self.refresh()
        try:
            from app.ui.theme import theme_manager

            mgr = theme_manager()
            if mgr is not None:
                mgr.theme_changed.connect(lambda *_: self._on_theme_changed())
        except Exception:
            pass

    def set_roots(self, roots: list[Path | str]) -> None:
        self._roots = [Path(r) for r in roots if r]
        self.refresh()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.addWidget(
            Notice(
                "诊断 dashboard · 只读",
                "context_conflict 仅展示分型，不提供放宽 Gate 的入口。"
                "完整指标可通过列选择或 Raw JSON 查看。",
                tone="info",
            )
        )
        kpi = QHBoxLayout()
        self.kpi_n = MetricCard("记录数")
        self.kpi_acc = MetricCard("Accepted")
        self.kpi_steady = MetricCard("Steady wall time")
        self.kpi_cold = MetricCard("Cold start")
        for w in (self.kpi_n, self.kpi_acc, self.kpi_steady, self.kpi_cold):
            kpi.addWidget(w)
        root.addLayout(kpi)

        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索文档…")
        self.search.textChanged.connect(self._apply_filters)
        self.cmb_profile = QComboBox()
        self.cmb_profile.addItem("全部 profile", "")
        self.cmb_profile.currentIndexChanged.connect(self._apply_filters)
        self.cb_all_cols = QCheckBox("显示全部列")
        self.cb_all_cols.setToolTip("默认只显示 9 列核心决策指标，其余进入详情。")
        self.cb_all_cols.toggled.connect(self._apply_column_visibility)
        self.lbl_status = QLabel("未加载")
        self.lbl_status.setProperty("role", "muted")
        top.addWidget(self.search, 2)
        top.addWidget(self.cmb_profile)
        top.addWidget(self.cb_all_cols)
        top.addWidget(self.lbl_status, 1)
        btn_refresh = QPushButton("刷新")
        btn_refresh.clicked.connect(self.refresh)
        btn_copy = QPushButton("复制为 Markdown")
        btn_copy.clicked.connect(self._copy_md)
        btn_copy_sel = QPushButton("复制当前行")
        btn_copy_sel.clicked.connect(self._copy_selected_curve)
        top.addWidget(btn_refresh)
        top.addWidget(btn_copy)
        top.addWidget(btn_copy_sel)
        root.addLayout(top)

        split = QSplitter(Qt.Orientation.Vertical)
        root.addWidget(split, 1)

        table_split = QSplitter(Qt.Orientation.Horizontal)
        self.table = QTableWidget(0, len(_TABLE_COLS))
        self.table.setHorizontalHeaderLabels(_TABLE_COLS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._on_row_selected)
        self._apply_column_visibility()
        table_split.addWidget(self.table)
        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setPlaceholderText("选中一行查看完整指标与 failure_class（只读）。")
        table_split.addWidget(self.detail)
        table_split.setStretchFactor(0, 3)
        table_split.setStretchFactor(1, 2)
        split.addWidget(table_split)

        bottom = QWidget()
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(0, 0, 0, 0)
        tabs = QTabWidget()
        bl.addWidget(tabs)

        overview = QWidget()
        ov = QVBoxLayout(overview)
        self._scroll_cost = QScrollArea()
        self._scroll_cost.setWidgetResizable(True)
        self._scroll_rate = QScrollArea()
        self._scroll_rate.setWidgetResizable(True)
        self._scroll_wall = QScrollArea()
        self._scroll_wall.setWidgetResizable(True)
        self.chart_cost = QChartView()
        self.chart_rate = QChartView()
        self.chart_wall = QChartView()
        for cv in (self.chart_cost, self.chart_rate, self.chart_wall):
            cv.setRenderHint(QPainter.RenderHint.Antialiasing)
            cv.setMinimumHeight(280)
        self._scroll_cost.setWidget(self.chart_cost)
        self._scroll_rate.setWidget(self.chart_rate)
        self._scroll_wall.setWidget(self.chart_wall)
        charts_row = QHBoxLayout()
        charts_row.addWidget(self._scroll_cost, 1)
        charts_row.addWidget(self._scroll_rate, 1)
        ov.addLayout(charts_row)
        ov.addWidget(self._scroll_wall, 1)
        tabs.addTab(overview, "总览")

        curve_w = QWidget()
        cl = QVBoxLayout(curve_w)
        row = QHBoxLayout()
        row.addWidget(QLabel("记录："))
        self.cmb_doc = QComboBox()
        self.cmb_doc.currentIndexChanged.connect(self._redraw_curve)
        self.cmb_doc.currentIndexChanged.connect(self._refresh_detail)
        row.addWidget(self.cmb_doc, 1)
        cl.addLayout(row)
        self.chart_curve = QChartView()
        self.chart_curve.setRenderHint(QPainter.RenderHint.Antialiasing)
        cl.addWidget(self.chart_curve, 1)
        tabs.addTab(curve_w, "Accept Curve")

        self.md_view = QTextEdit()
        self.md_view.setReadOnly(True)
        tabs.addTab(self.md_view, "Decision Markdown")

        self.json_view = QTextEdit()
        self.json_view.setReadOnly(True)
        tabs.addTab(self.json_view, "Raw JSON")

        audit = QWidget()
        al = QVBoxLayout(audit)
        al.addWidget(
            Notice(
                "Conflict Audit · Read only",
                "只展示 context_conflict 分型。不提供放宽 Gate 的按钮。",
                tone="warning",
            )
        )
        self.audit_view = QTextEdit()
        self.audit_view.setReadOnly(True)
        al.addWidget(self.audit_view, 1)
        tabs.addTab(audit, "Conflict Audit")

        split.addWidget(bottom)
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 3)
        mono = mono_font()
        self.json_view.setFont(mono)
        self.detail.setFont(mono)
        self.audit_view.setFont(mono)

    def _on_theme_changed(self) -> None:
        if self._batch:
            self._redraw_overview()
            self._redraw_curve()

    def refresh(self) -> None:
        if not self._roots:
            self.lbl_status.setText("无导出目录可扫描")
            return
        try:
            # 全量：不过滤、不按篇折叠
            self._batch = collect_experiment_results(
                self._roots, prefer_latest_per_doc=False, max_docs=None
            )
        except Exception as e:
            QMessageBox.warning(self, "实验结果", f"扫描失败：{e}")
            return
        n = len(self._batch.rows)
        accepted = sum(int(r.accepted or 0) for r in self._batch.rows)
        self.kpi_n.set_value(str(n))
        self.kpi_acc.set_value(str(accepted))
        self.kpi_steady.set_value(f"{self._batch.batch_steady_state_seconds:.1f}s")
        self.kpi_cold.set_value(f"{self._batch.batch_cold_start_seconds:.1f}s")
        self.lbl_status.setText(
            f"已加载 {n} 条记录 · roots={len(self._roots)}"
        )
        self._fill_profile_filter()
        self._fill_table()
        self._fill_combo()
        self._redraw_overview()
        self._redraw_curve()
        self._md = format_experiment_markdown(self._batch)
        self.md_view.setPlainText(self._md)
        import json

        self.json_view.setPlainText(
            json.dumps(
                {
                    "collected_at": self._batch.collected_at,
                    "roots": self._batch.roots,
                    "rows": [r.to_dict() for r in self._batch.rows],
                    "failure_memory_summary": self._batch.failure_memory_summary,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        self._fill_conflict_audit()

    def _fill_profile_filter(self) -> None:
        cur = self.cmb_profile.currentData()
        profiles = sorted({
            (r.profile or "").strip()
            for r in (self._batch.rows if self._batch else [])
            if (r.profile or "").strip()
        })
        self.cmb_profile.blockSignals(True)
        self.cmb_profile.clear()
        self.cmb_profile.addItem("全部 profile", "")
        for p in profiles:
            self.cmb_profile.addItem(p, p)
        idx = self.cmb_profile.findData(cur)
        self.cmb_profile.setCurrentIndex(idx if idx >= 0 else 0)
        self.cmb_profile.blockSignals(False)

    def _filtered_indices(self) -> list[int]:
        rows = self._batch.rows if self._batch else []
        q = self.search.text().strip().lower()
        prof = str(self.cmb_profile.currentData() or "")
        out: list[int] = []
        for i, r in enumerate(rows):
            if prof and (r.profile or "") != prof:
                continue
            hay = f"{r.document} {r.run_id} {r.profile} {r.chart_label()}".lower()
            if q and q not in hay:
                continue
            out.append(i)
        return out

    def _apply_column_visibility(self, *_args) -> None:
        show_all = bool(getattr(self, "cb_all_cols", None) and self.cb_all_cols.isChecked())
        for col in range(len(_TABLE_COLS)):
            self.table.setColumnHidden(col, False if show_all else col not in _CORE_COLS)

    def _apply_filters(self, *_args) -> None:
        self._fill_table()

    def _fill_conflict_audit(self) -> None:
        rows = self._batch.rows if self._batch else []
        lines = [
            "READ ONLY · 不放宽 ocr_context_conflict",
            "",
        ]
        fm = (self._batch.failure_memory_summary if self._batch else {}) or {}
        if fm:
            lines.append(f"Failure Memory summary keys: {', '.join(sorted(fm.keys())[:20])}")
            if "events_count" in fm:
                lines.append(f"events_count: {fm.get('events_count')}")
            lines.append("")
        conflict_docs = []
        for r in rows:
            counts = r.failure_class_counts or {}
            n = int(counts.get("context_conflict") or counts.get("context_strong_conflict") or 0)
            if "conflict" in (r.profile or "") or n:
                conflict_docs.append(
                    f"- {r.chart_label()}  profile={r.profile or '—'}  "
                    f"accepted={r.accepted} rejected={r.rejected}  "
                    f"failure_class={counts}"
                )
        if not conflict_docs:
            lines.append("本批没有 profile / failure_class 标出的 conflict 文档。")
        else:
            lines.append(f"{len(conflict_docs)} 篇含 conflict 信号：")
            lines.extend(conflict_docs)
        self.audit_view.setPlainText("\n".join(lines))

    def _fill_table(self) -> None:
        all_rows = self._batch.rows if self._batch else []
        indices = self._filtered_indices()
        rows = [all_rows[i] for i in indices]
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for visual_i, batch_index in enumerate(indices):
            r = all_rows[batch_index]
            cold = r.batch_cold_start_seconds
            if cold is None:
                cold = r.model_cold_start
            fl = ""
            if r.first_accept_attempt is not None:
                fl = f"{r.first_accept_attempt}→{r.last_accept_attempt or r.first_accept_attempt}"
            vals = [
                r.document,
                r.run_id,
                "" if r.attempted is None else str(r.attempted),
                "" if r.accepted is None else str(r.accepted),
                "" if r.rejected is None else str(r.rejected),
                "" if r.accept_rate is None else f"{r.accept_rate:.1%}",
                _f(r.cost_per_recovered_formula),
                _f(r.seconds_per_accept),
                r.profile or "",
                fl,
                _f(r.accept_curve_auc, 3),
                _f(r.total_seconds),
                _f(r.docling_seconds),
                _f(r.asset_seconds),
                _f(r.repair_seconds),
                _f(cold),
                _f(r.ocr_inference_seconds),
                _f(r.deepseek_load),
            ]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setData(_BATCH_INDEX_ROLE, batch_index)
                if j >= 2:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                if j >= 2 and v not in {"", "—"}:
                    try:
                        item.setData(
                            Qt.ItemDataRole.UserRole,
                            float(str(v).replace("%", "")),
                        )
                    except ValueError:
                        pass
                self.table.setItem(visual_i, j, item)
        self.table.setSortingEnabled(True)

    def _fill_combo(self) -> None:
        self.cmb_doc.blockSignals(True)
        self.cmb_doc.clear()
        for batch_index, r in enumerate(self._batch.rows if self._batch else []):
            self.cmb_doc.addItem(r.chart_label(), batch_index)
        self.cmb_doc.blockSignals(False)

    def _on_row_selected(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        item = self.table.item(rows[0].row(), 0)
        batch_index = batch_index_from_item(item)
        if batch_index is None:
            return
        combo_index = self.cmb_doc.findData(batch_index)
        if combo_index >= 0:
            self.cmb_doc.setCurrentIndex(combo_index)
        self._refresh_detail()

    def _selected_result(self):
        if not self._batch:
            return None
        batch_index = self.cmb_doc.currentData()
        if batch_index is None:
            return None
        batch_index = int(batch_index)
        if not 0 <= batch_index < len(self._batch.rows):
            return None
        return self._batch.rows[batch_index]

    def _refresh_detail(self) -> None:
        r = self._selected_result()
        if r is None:
            self.detail.setPlainText("")
            return
        cold = r.batch_cold_start_seconds
        if cold is None:
            cold = r.model_cold_start
        fl = ""
        if r.first_accept_attempt is not None:
            fl = f"{r.first_accept_attempt}→{r.last_accept_attempt or r.first_accept_attempt}"
        self.detail.setPlainText(
            f"{r.chart_label()}\n"
            f"profile: {r.profile or '—'}\n"
            f"attempted/accepted/rejected: {r.attempted} / {r.accepted} / {r.rejected}\n"
            f"accept_rate: {'' if r.accept_rate is None else f'{r.accept_rate:.1%}'}\n"
            f"sec/accept: {_f(r.seconds_per_accept)}   cost/accept: {_f(r.cost_per_recovered_formula)}\n"
            f"first→last: {fl or '—'}   curve_auc: {_f(r.accept_curve_auc, 3)}\n"
            f"total={_f(r.total_seconds)}  docling={_f(r.docling_seconds)}  "
            f"asset={_f(r.asset_seconds)}  repair={_f(r.repair_seconds)}\n"
            f"cold={_f(cold)}  ocr_infer={_f(r.ocr_inference_seconds)}  ds_load={_f(r.deepseek_load)}\n"
            f"failure_class: {r.failure_class_counts or {}}\n"
            f"wasted_ocr_by_class: {r.wasted_ocr_seconds_by_class or {}}\n"
        )

    def _sized_chart_view(self, view: QChartView, n_cats: int) -> None:
        # 每类至少 56px，保证 N 条都会出现在 X 轴（可横向滚动）
        w = max(480, int(n_cats) * 56)
        view.setMinimumWidth(w)
        view.resize(w, view.height())

    def _bar_chart(
        self,
        *,
        title: str,
        values: list[float],
        cats: list[str],
        y_title: str,
        y_max: float | None = None,
    ) -> QChart:
        chart = QChart()
        chart.setTitle(f"{title}（n={len(cats)}）")
        chart.legend().setVisible(False)
        if not cats:
            return chart
        s = QBarSet(title)
        colorize_bar_set(s, "accent")
        for v in values:
            s.append(float(v))
        series = QBarSeries()
        series.append(s)
        chart.addSeries(series)
        axis_x = QBarCategoryAxis()
        axis_x.append(cats)
        axis_x.setLabelsAngle(-60)
        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(axis_x)
        axis_y = QValueAxis()
        axis_y.setTitleText(y_title)
        if y_max is not None:
            axis_y.setRange(0, y_max)
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_y)
        apply_chart_theme(chart)
        return chart

    def _redraw_overview(self) -> None:
        # 关键点：全部记录进 X 轴；缺测值用 0，不再丢掉「无 OCR」的篇
        rows = list(self._batch.rows if self._batch else [])
        cats = [_short(r.chart_label()) for r in rows]
        n = len(cats)

        cost_vals = [
            float(r.cost_per_recovered_formula)
            if r.cost_per_recovered_formula is not None
            else 0.0
            for r in rows
        ]
        rate_vals = [
            float(r.accept_rate) * 100.0 if r.accept_rate is not None else 0.0
            for r in rows
        ]
        total_vals = [float(r.total_seconds or 0.0) for r in rows]
        repair_vals = [float(r.repair_seconds or 0.0) for r in rows]
        cold_vals = [
            float(
                r.batch_cold_start_seconds
                if r.batch_cold_start_seconds is not None
                else (r.model_cold_start or 0.0)
            )
            for r in rows
        ]

        self.chart_cost.setChart(
            self._bar_chart(
                title="cost_per_recovered_formula",
                values=cost_vals,
                cats=cats,
                y_title="seconds (0=无接受/无OCR)",
            )
        )
        self.chart_rate.setChart(
            self._bar_chart(
                title="accept_rate",
                values=rate_vals,
                cats=cats,
                y_title="%",
                y_max=100,
            )
        )

        # 墙钟拆分：total / repair / cold 三组并排
        chart_w = QChart()
        chart_w.setTitle(f"墙钟拆分 total / repair / cold（n={n}）")
        if cats:
            b_total = QBarSet("total")
            b_repair = QBarSet("repair")
            b_cold = QBarSet("cold")
            colorize_bar_set(b_total, "accent")
            colorize_bar_set(b_repair, "info")
            colorize_bar_set(b_cold, "warning")
            for a, b, c in zip(total_vals, repair_vals, cold_vals):
                b_total.append(a)
                b_repair.append(b)
                b_cold.append(c)
            series = QBarSeries()
            series.append(b_total)
            series.append(b_repair)
            series.append(b_cold)
            chart_w.addSeries(series)
            axis_x = QBarCategoryAxis()
            axis_x.append(cats)
            axis_x.setLabelsAngle(-60)
            chart_w.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
            series.attachAxis(axis_x)
            axis_y = QValueAxis()
            axis_y.setTitleText("seconds")
            chart_w.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
            series.attachAxis(axis_y)
            chart_w.legend().setVisible(True)
        apply_chart_theme(chart_w)
        self.chart_wall.setChart(chart_w)

        for cv in (self.chart_cost, self.chart_rate, self.chart_wall):
            self._sized_chart_view(cv, max(n, 1))

    def _redraw_curve(self) -> None:
        chart = QChart()
        r = self._selected_result()
        if r is None:
            self.chart_curve.setChart(chart)
            return
        series = QLineSeries()
        series.setName("cumulative accepted")
        curve = r.cumulative_accept_curve or []
        for i, v in enumerate(curve, start=1):
            series.append(float(i), float(v))
        # 无曲线时仍画 attempted 轴空线，避免“空白误以为坏了”
        if not curve and r.attempted:
            for i in range(1, int(r.attempted) + 1):
                series.append(float(i), 0.0)
        chart.addSeries(series)
        chart.createDefaultAxes()
        axes = chart.axes(Qt.Orientation.Horizontal)
        if axes:
            axes[0].setTitleText("attempt")
        axes_y = chart.axes(Qt.Orientation.Vertical)
        if axes_y:
            axes_y[0].setTitleText("accepted (cumulative)")
        chart.setTitle(
            f"{r.chart_label()} · positions={r.accept_positions} · auc={r.accept_curve_auc}"
        )
        apply_chart_theme(chart)
        self.chart_curve.setChart(chart)

    def _copy_md(self) -> None:
        if not self._batch or not self._batch.rows:
            self.refresh()
        if not self._batch or not self._batch.rows:
            QMessageBox.information(self, "实验结果", "没有可复制的内容。")
            return
        latest = rows_for_latest_batch(self._batch.rows)
        md = format_experiment_markdown(ExperimentBatch(rows=latest))
        QApplication.clipboard().setText(md, QClipboard.Mode.Clipboard)
        n = len(latest)
        total = len(self._batch.rows)
        if n < total:
            tip = f"已复制最近一次同批转换 {n} 条（共 {total} 条历史）的决策表 Markdown。"
        else:
            tip = "已复制决策表 Markdown 到剪贴板。"
        QMessageBox.information(self, "实验结果", tip)

    def _copy_selected_curve(self) -> None:
        r = self._selected_result()
        if r is None:
            return
        import json

        QApplication.clipboard().setText(
            json.dumps(r.to_dict(), ensure_ascii=False, indent=2),
            QClipboard.Mode.Clipboard,
        )
        QMessageBox.information(self, "实验结果", f"已复制 {r.chart_label()} 全量字段。")
