# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QIcon

_ICON_ROOT = Path(__file__).parent / "icons"


def icon(name: str) -> QIcon:
    path = _ICON_ROOT / f"{name}.svg"
    if not path.is_file():
        return QIcon()
    return QIcon(str(path))
