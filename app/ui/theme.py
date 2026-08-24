# -*- coding: utf-8 -*-
"""ThemeManager：全局 Palette + QSS，浅色 / 深色 / 跟随系统。"""
from __future__ import annotations

from enum import Enum
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

from app.ui.tokens import DARK, LIGHT, ThemeTokens

_STYLE_PATH = Path(__file__).with_name("style.qss")
_MANAGER: ThemeManager | None = None


class ThemeMode(str, Enum):
    SYSTEM = "跟随系统"
    LIGHT = "浅色"
    DARK = "深色"


class ThemeManager(QObject):
    theme_changed = Signal(str)

    def __init__(self, app: QApplication) -> None:
        super().__init__(app)
        self._app = app
        self._mode = ThemeMode.SYSTEM
        self._tokens = LIGHT
        try:
            app.styleHints().colorSchemeChanged.connect(self._on_system_scheme_changed)
        except Exception:
            pass

    @property
    def tokens(self) -> ThemeTokens:
        return self._tokens

    @property
    def mode(self) -> ThemeMode:
        return self._mode

    def apply(self, value: str | ThemeMode) -> None:
        try:
            mode = value if isinstance(value, ThemeMode) else ThemeMode(value)
        except ValueError:
            mode = ThemeMode.SYSTEM
        self._mode = mode
        self._tokens = DARK if self._resolve_dark(mode) else LIGHT
        self._apply_font()
        self._apply_palette(self._tokens)
        self._apply_qss(self._tokens)
        self.theme_changed.emit(mode.value)

    def _resolve_dark(self, mode: ThemeMode) -> bool:
        if mode == ThemeMode.DARK:
            return True
        if mode == ThemeMode.LIGHT:
            return False
        try:
            return self._app.styleHints().colorScheme() == Qt.ColorScheme.Dark
        except Exception:
            return False

    def _on_system_scheme_changed(self, *_args) -> None:
        if self._mode == ThemeMode.SYSTEM:
            self.apply(self._mode)

    def _apply_font(self) -> None:
        families = set(QFontDatabase.families())
        if "Segoe UI Variable Text" in families:
            family = "Segoe UI Variable Text"
        elif "Segoe UI" in families:
            family = "Segoe UI"
        else:
            family = self._app.font().family()
        font = QFont(family)
        font.setPointSizeF(10.0)
        self._app.setFont(font)

    def _apply_palette(self, t: ThemeTokens) -> None:
        p = QPalette()
        p.setColor(QPalette.ColorRole.Window, QColor(t.window))
        p.setColor(QPalette.ColorRole.WindowText, QColor(t.text))
        p.setColor(QPalette.ColorRole.Base, QColor(t.surface))
        p.setColor(QPalette.ColorRole.AlternateBase, QColor(t.surface_alt))
        p.setColor(QPalette.ColorRole.Text, QColor(t.text))
        p.setColor(QPalette.ColorRole.PlaceholderText, QColor(t.text_subtle))
        p.setColor(QPalette.ColorRole.Button, QColor(t.surface))
        p.setColor(QPalette.ColorRole.ButtonText, QColor(t.text))
        p.setColor(QPalette.ColorRole.Highlight, QColor(t.accent))
        p.setColor(QPalette.ColorRole.HighlightedText, QColor(t.accent_text))
        p.setColor(
            QPalette.ColorGroup.Disabled,
            QPalette.ColorRole.Text,
            QColor(t.disabled_text),
        )
        p.setColor(
            QPalette.ColorGroup.Disabled,
            QPalette.ColorRole.ButtonText,
            QColor(t.disabled_text),
        )
        self._app.setPalette(p)

    def _apply_qss(self, t: ThemeTokens) -> None:
        qss = _STYLE_PATH.read_text(encoding="utf-8")
        for key, value in {
            "@WINDOW@": t.window,
            "@SURFACE@": t.surface,
            "@SURFACE_ALT@": t.surface_alt,
            "@SURFACE_HOVER@": t.surface_hover,
            "@BORDER@": t.border,
            "@BORDER_STRONG@": t.border_strong,
            "@TEXT@": t.text,
            "@TEXT_MUTED@": t.text_muted,
            "@TEXT_SUBTLE@": t.text_subtle,
            "@ACCENT@": t.accent,
            "@ACCENT_HOVER@": t.accent_hover,
            "@ACCENT_PRESSED@": t.accent_pressed,
            "@ACCENT_TEXT@": t.accent_text,
            "@SUCCESS@": t.success,
            "@SUCCESS_BG@": t.success_bg,
            "@WARNING@": t.warning,
            "@WARNING_BG@": t.warning_bg,
            "@DANGER@": t.danger,
            "@DANGER_BG@": t.danger_bg,
            "@INFO@": t.info,
            "@INFO_BG@": t.info_bg,
            "@SELECTION@": t.selection,
            "@DISABLED_BG@": t.disabled_bg,
            "@DISABLED_TEXT@": t.disabled_text,
        }.items():
            qss = qss.replace(key, value)
        self._app.setStyleSheet(qss)


def install_theme(app: QApplication, mode: str) -> ThemeManager:
    global _MANAGER
    _MANAGER = ThemeManager(app)
    _MANAGER.apply(mode)
    return _MANAGER


def theme_manager() -> ThemeManager | None:
    return _MANAGER
