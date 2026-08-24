# -*- coding: utf-8 -*-
"""纯函数：配置身份 / 实验表行身份。供 UI 与单测共用。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidgetItem

from app.ui.pipeline_classify import (  # noqa: F401
    STAGE_LABELS,
    classify_deepseek_state,
    classify_pipeline_stage,
)

BATCH_INDEX_ROLE = Qt.ItemDataRole.UserRole + 1
CORE_COLUMNS = 9


def formula_profile_identity(
    *,
    preset: str,
    enrich: bool,
    deepseek: bool,
) -> str:
    preset = (preset or "").lower()
    if preset == "balanced" and deepseek and not enrich:
        return "Lean Balanced"
    if preset == "fast":
        return "Fast"
    if preset == "quality":
        return "Quality"
    return "Custom"


def formula_profile_tone(identity: str) -> str:
    return {
        "Lean Balanced": "info",
        "Fast": "neutral",
        "Quality": "warning",
        "Custom": "neutral",
    }.get(identity, "neutral")


def batch_index_from_item(item: QTableWidgetItem | None) -> int | None:
    if item is None:
        return None
    raw = item.data(BATCH_INDEX_ROLE)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None
