# -*- coding: utf-8 -*-
from __future__ import annotations

from PySide6.QtGui import QFont, QFontDatabase


def mono_font(point_size: float = 10.0) -> QFont:
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    font.setPointSizeF(point_size)
    return font
