# -*- coding: utf-8 -*-
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from app.ui.widgets.status_badge import StatusBadge

_STRUCTURED = ("Parse", "Assets", "Repair", "Mirror")
_VISION = ("Render", "Transcribe", "Merge", "Figures")

_STRUCTURED_KEYS = ["parse", "assets", "repair", "mirror"]
_VISION_KEYS = ["render", "transcribe", "merge", "figures"]
# validate 映射到 transcribe 进行中的子阶段
_VISION_ALIASES = {"validate": "transcribe"}


class PipelineStatusWidget(QWidget):
    """线性阶段指示。支持快速自动 / 高保真视觉两套标签。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mode = "structured"
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(6)
        self._badges: dict[str, StatusBadge] = {}
        self._arrows: list[QLabel] = []
        self._rebuild(_STRUCTURED)

    def _clear(self) -> None:
        while self._lay.count():
            item = self._lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._badges.clear()
        self._arrows.clear()

    def _rebuild(self, steps: tuple[str, ...]) -> None:
        self._clear()
        for i, name in enumerate(steps):
            badge = StatusBadge(f"{name} ○", "neutral")
            self._badges[name.lower()] = badge
            self._lay.addWidget(badge)
            if i < len(steps) - 1:
                arrow = QLabel("›")
                arrow.setProperty("role", "subtle")
                self._arrows.append(arrow)
                self._lay.addWidget(arrow)
        self.reset()

    def set_mode(self, mode: str) -> None:
        mode = "vision" if mode == "vision" else "structured"
        if mode == self._mode:
            return
        self._mode = mode
        self._rebuild(_VISION if mode == "vision" else _STRUCTURED)

    def reset(self) -> None:
        for name, badge in self._badges.items():
            badge.set_status(f"{name.capitalize()} ○", "neutral")

    def set_stage(self, stage: str) -> None:
        if self._mode == "vision":
            order = list(_VISION_KEYS)
            stage = _VISION_ALIASES.get(stage, stage)
        else:
            order = list(_STRUCTURED_KEYS)
        if stage == "idle":
            for key in order:
                if key in self._badges:
                    self._badges[key].set_status(f"{key.capitalize()} ✓", "success")
            return
        if stage not in order:
            return
        idx = order.index(stage)
        for i, key in enumerate(order):
            if key not in self._badges:
                continue
            label = key.capitalize()
            if i < idx:
                self._badges[key].set_status(f"{label} ✓", "success")
            elif i == idx:
                self._badges[key].set_status(f"{label} ●", "info")
            else:
                self._badges[key].set_status(f"{label} ○", "neutral")
