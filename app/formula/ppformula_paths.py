# -*- coding: utf-8 -*-
"""Paddle 公式 Worker 路径：独立 venv，禁止塞进 GUI Python。"""
from __future__ import annotations

import os
from pathlib import Path

from app.utils.paths import APP_ROOT

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18775
META_PATH = APP_ROOT / ".cache" / "paddle_formula_worker.json"

_DEFAULT_VENV = APP_ROOT / ".venv-paddle-formula" / (
    "Scripts" if os.name == "nt" else "bin"
) / ("python.exe" if os.name == "nt" else "python")


def resolve_paddle_python() -> Path | None:
    raw = (os.environ.get("PDF2MD_PADDLE_PYTHON") or "").strip()
    if raw:
        p = Path(raw)
        return p if p.is_file() else None
    if _DEFAULT_VENV.is_file():
        return _DEFAULT_VENV
    return None
