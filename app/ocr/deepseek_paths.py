"""DeepSeek-OCR 2 本地权重 / 专用 venv 路径（GUI 与脚本共用）。"""
from __future__ import annotations

import os
from pathlib import Path

# 与 scripts/run_phase*.py 冻结路径一致
HF_ROOT = Path(r"${PDF2MD_HF_HOME}")
DEEPSEEK_MODEL_DIR = Path(
    r"E:\Ollama\modelscope\models\deepseek-ai--DeepSeek-OCR-2\snapshots\master"
)
DSOCR2_PYTHON = Path(r"E:\Ollama\venvs\dsocr2\Scripts\python.exe")


def ensure_deepseek_hf_env() -> None:
    HF_ROOT.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(HF_ROOT))
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(HF_ROOT / "hub"))
    os.environ.setdefault("TRANSFORMERS_CACHE", str(HF_ROOT / "transformers"))
    os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
    os.environ.setdefault("USE_TF", "0")


def resolve_deepseek_model_name() -> str:
    if DEEPSEEK_MODEL_DIR.is_dir():
        return str(DEEPSEEK_MODEL_DIR)
    return "deepseek-ai/DeepSeek-OCR-2"


def resolve_dsocr2_python() -> Path | None:
    if DSOCR2_PYTHON.is_file():
        return DSOCR2_PYTHON
    return None
