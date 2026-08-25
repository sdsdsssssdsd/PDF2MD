"""DeepSeek-OCR 2 本地权重 / 专用 venv 路径（GUI 与脚本共用）。"""
from __future__ import annotations

import os
from pathlib import Path

from app.utils.paths import APP_ROOT

HF_ROOT = Path(
    os.environ.get("PDF2MD_HF_HOME")
    or os.environ.get("HF_HOME")
    or (APP_ROOT / ".cache" / "hf")
)
DEEPSEEK_MODEL_DIR = Path(os.environ.get("PDF2MD_DEEPSEEK_MODEL_DIR", ""))
DSOCR2_PYTHON = Path(os.environ.get("PDF2MD_DSOCR2_PYTHON", ""))


def ensure_deepseek_hf_env() -> None:
    HF_ROOT.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(HF_ROOT))
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(HF_ROOT / "hub"))
    os.environ.setdefault("TRANSFORMERS_CACHE", str(HF_ROOT / "transformers"))
    os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
    os.environ.setdefault("USE_TF", "0")


def resolve_deepseek_model_name() -> str:
    env = os.environ.get("PDF2MD_DEEPSEEK_MODEL_DIR", "").strip()
    if env:
        p = Path(env)
        if p.is_dir():
            return str(p)
    if DEEPSEEK_MODEL_DIR.is_dir():
        return str(DEEPSEEK_MODEL_DIR)
    return "deepseek-ai/DeepSeek-OCR-2"


def resolve_dsocr2_python() -> Path | None:
    env = os.environ.get("PDF2MD_DSOCR2_PYTHON", "").strip()
    if env:
        p = Path(env)
        if p.is_file():
            return p
    if DSOCR2_PYTHON.is_file():
        return DSOCR2_PYTHON
    return None
