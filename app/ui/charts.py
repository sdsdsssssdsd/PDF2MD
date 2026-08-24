# -*- coding: utf-8 -*-
"""QtCharts 与 Theme tokens 对齐。"""
from __future__ import annotations

from PySide6.QtCharts import QBarSet, QChart
from PySide6.QtGui import QBrush, QColor, QPen

from app.ui.tokens import LIGHT, ThemeTokens


def current_tokens() -> ThemeTokens:
    try:
        from app.ui.theme import theme_manager

        mgr = theme_manager()
        if mgr is not None:
            return mgr.tokens
    except Exception:
        pass
    return LIGHT


def apply_chart_theme(chart: QChart) -> None:
    t = current_tokens()
    chart.setBackgroundBrush(QBrush(QColor(t.surface)))
    chart.setPlotAreaBackgroundBrush(QBrush(QColor(t.surface_alt)))
    chart.setPlotAreaBackgroundVisible(True)
    chart.setTitleBrush(QBrush(QColor(t.text)))
    chart.setBackgroundRoundness(8)
    legend = chart.legend()
    legend.setLabelColor(QColor(t.text_muted))
    for axis in chart.axes():
        axis.setLabelsColor(QColor(t.text_muted))
        axis.setTitleBrush(QBrush(QColor(t.text_muted)))
        axis.setLinePen(QPen(QColor(t.border)))
        try:
            axis.setGridLineColor(QColor(t.border))
        except Exception:
            pass


def colorize_bar_set(bar: QBarSet, role: str = "accent") -> None:
    t = current_tokens()
    color = {
        "accent": t.accent,
        "success": t.success,
        "warning": t.warning,
        "danger": t.danger,
        "info": t.info,
    }.get(role, t.accent)
    bar.setColor(QColor(color))
    bar.setBorderColor(QColor(color))
