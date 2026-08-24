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
    assert dlg.nav.count() == 5
    assert dlg.stack.count() == 5
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
