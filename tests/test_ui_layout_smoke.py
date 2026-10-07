# -*- coding: utf-8 -*-
"""低成本 UI 回归：尺寸、默认按钮、列数。不测像素截图。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication

from app.dialogs.experiment_results_dialog import (
    CORE_COLUMNS,
    ExperimentResultsDialog,
    _CORE_COLS,
    _TABLE_COLS,
)
from app.dialogs.formula_benchmark_dialog import FormulaBenchmarkDialog
from app.dialogs.settings_dialog import SettingsDialog
from app.main_window import MainWindow
from app.ui.icons import icon
from app.ui.theme import install_theme


def _app() -> QApplication:
    inst = QApplication.instance()
    if inst is not None:
        return inst
    app = QApplication([])
    install_theme(app, "浅色")
    return app


def test_main_window_minimum_and_defaults():
    _app()
    w = MainWindow()
    assert w.minimumWidth() >= 1024
    assert w.minimumHeight() >= 700
    assert w.table.columnCount() == len(MainWindow.COLS) == 9
    assert w.btn_start.isDefault()
    assert not w.btn_clear.isDefault()
    assert not w.btn_cancel.isDefault()
    assert not w.empty_hint.isHidden()
    assert w.table.isHidden()
    w.close()


def test_api_vision_force_rerun_control():
    _app()
    w = MainWindow()
    assert w.cmb_api_precision.itemText(0) == "标准（6 页/批）"
    assert w.cb_api_force_rerun.text() == "强制重跑 API 视觉转录"
    assert w.cb_vision_force_rerun.text() == "强制重跑浏览器转录"
    w.close()


def test_format_repair_workspace_exists():
    _app()
    w = MainWindow()
    assert w.format_repair_workspace is not None
    assert "format_repair" in w.workflow_picker._buttons
    assert w.workflow_picker._buttons["format_repair"].text().startswith("格式修正")
    w.close()


def test_daily_workspace_progress_bar():
    _app()
    w = MainWindow()
    ws = w.daily_workspace
    row = ws.progress_row
    assert row.isHidden()

    ws.set_busy(True)
    assert not row.isHidden()
    assert row.bar.value() == 0
    assert row.percent_label.text() == "0%"
    assert ws.is_busy()
    assert not ws.btn_cancel.isHidden()

    ws.set_status("识别中…")
    assert "识别中" in row.status_text()
    assert "已用 0s" in row.status_text()  # 运行中显示耗时

    ws.set_progress(42, "第 2/7 批 · 已接收 1,234 字")
    assert row.bar.value() == 42
    assert row.percent_label.text() == "42%"
    assert "第 2/7 批" in row.status_text()

    # 控制器 → 工作区（MainWindow 接线）
    w._daily.progress.emit("已完成 12/39 张", 27)
    assert row.bar.value() == 27
    assert row.percent_label.text() == "27%"
    assert "已完成 12/39 张" in row.status_text()

    ws.set_busy(False)
    assert row.isHidden()
    assert not ws.is_busy()
    assert ws.btn_cancel.isHidden()
    # 收尾消息回到窗口底部状态栏
    ws.set_status("识别完成 · 可直接复制")
    assert "识别完成" in ws.lbl_status.text()
    w.close()


def test_api_vision_command_bar_progress():
    """API 高精度：页级进度 → Command Bar 确定进度条 + 阶段文本带百分比。"""
    _app()
    w = MainWindow()
    w.workflow_picker.set_value("vision_api")
    assert not w.command_bar.isHidden()

    w.command_bar.set_running(True)
    w.command_bar.set_progress(0)
    w._vision.progress.emit("页面渲染 3/30", 12)
    assert w.command_bar.progress.maximum() == 100
    assert w.command_bar.progress.value() == 12
    assert "12%" in w.stage_label.text()
    assert "页面渲染 3/30" in w.stage_label.text()

    w._vision.progress.emit("视觉转录 6/30 页（第 2 批 0007–0012）", 40)
    assert w.command_bar.progress.value() == 40
    assert "40%" in w.stage_label.text()

    w.command_bar.set_running(False)
    assert w.command_bar.progress.isHidden()
    w.close()


def test_format_repair_workspace_progress_bar():
    _app()
    w = MainWindow()
    ws = w.format_repair_workspace
    row = ws.progress_row
    assert row.isHidden()

    ws.set_busy(True)
    assert not row.isHidden()
    assert row.bar.value() == 0
    assert not ws.btn_cancel.isHidden()

    ws.set_status("正在修正格式…")
    assert "正在修正格式" in row.status_text()
    assert "已用 0s" in row.status_text()

    ws.set_progress(46, "第 2/3 段 · 已接收 8,120 字")
    assert row.bar.value() == 46
    assert row.percent_label.text() == "46%"

    # 控制器 → 工作区（MainWindow 接线）
    w._repair.progress.emit("已完成 2/3 段", 60)
    assert row.bar.value() == 60
    assert "已完成 2/3 段" in row.status_text()

    ws.set_busy(False)
    assert row.isHidden()
    assert ws.btn_cancel.isHidden()
    ws.set_status("DeepSeek 已修正 · 2 段")
    assert "已修正" in ws.lbl_status.text()
    w.close()


def test_experiment_core_columns_hidden_rest():
    assert len(CORE_COLUMNS) == 9
    assert len(_CORE_COLS) == 9
    assert len(_TABLE_COLS) == 18


def test_experiment_dialog_builds():
    _app()
    dlg = ExperimentResultsDialog(roots=[Path("logs/experiment")])
    assert dlg.table.columnCount() == 18
    assert dlg.table.isColumnHidden(6)
    assert not dlg.table.isColumnHidden(0)
    dlg.cb_all_cols.setChecked(True)
    assert not dlg.table.isColumnHidden(6)
    dlg.close()


def test_formula_lab_default_table_cols():
    _app()
    dlg = FormulaBenchmarkDialog()
    assert dlg.table.columnCount() == 6
    assert dlg.notice_conflict.isHidden()
    dlg.close()


def test_settings_nav_and_env_table():
    _app()
    dlg = SettingsDialog()
    assert dlg.nav.count() == 6
    assert dlg.stack.count() == 6
    assert dlg.env_table.columnCount() == 3
    assert not dlg.parallel.isEnabled()
    dlg.close()


def test_icons_resolve():
    for name in (
        "settings",
        "log",
        "flask",
        "chart",
        "database",
        "more",
        "play",
        "stop",
        "lock",
        "folder",
        "file",
        "chevron-right",
    ):
        ico = icon(name)
        assert not ico.isNull(), name
