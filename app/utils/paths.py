"""应用路径：基于项目根目录与当前 Python，不写死本机路径。"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]

# 当前解释器（venv / 系统 Python 均可）；也可用环境变量 PDF2MD_PYTHON 覆盖
_override = os.environ.get("PDF2MD_PYTHON")
PYTHON_EXE = Path(_override).resolve() if _override else Path(sys.executable).resolve()

_scripts = PYTHON_EXE.parent
# Windows: .../Scripts/python.exe；部分安装为同目录
if _scripts.name.lower() == "scripts":
    _bin = _scripts
else:
    _bin = _scripts / "Scripts"
    if not _bin.exists():
        _bin = _scripts

DOCLING_EXE = _bin / ("docling.exe" if sys.platform.startswith("win") else "docling")
MINERU_EXE = _bin / ("mineru.exe" if sys.platform.startswith("win") else "mineru")

# 若 Scripts 下没有，回退到 PATH
if not DOCLING_EXE.exists():
    found = shutil.which("docling")
    if found:
        DOCLING_EXE = Path(found)
if not MINERU_EXE.exists():
    found = shutil.which("mineru")
    if found:
        MINERU_EXE = Path(found)

INPUT_DIR = APP_ROOT / "input"
OUTPUT_DIR = APP_ROOT / "output"
LOGS_DIR = APP_ROOT / "logs"
ICONS_DIR = APP_ROOT / "icons"
SCRIPTS_DIR = APP_ROOT / "scripts"
CACHE_DIR = APP_ROOT / ".cache"
# 可用环境变量 PDF2MD_DOCLING_ARTIFACTS 覆盖（见 docling_engine._artifacts_dir）
DOCLING_ARTIFACTS_DIR = CACHE_DIR / "docling-artifacts"


def ensure_dirs() -> None:
    for d in (INPUT_DIR, OUTPUT_DIR, LOGS_DIR, ICONS_DIR, SCRIPTS_DIR, CACHE_DIR):
        d.mkdir(parents=True, exist_ok=True)


def task_output_dir(output_root: Path, pdf_path: Path, per_folder: bool) -> Path:
    stem = pdf_path.stem
    if per_folder:
        return output_root / stem
    return output_root
