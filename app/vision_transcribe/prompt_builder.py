"""构建并落盘批次 Prompt。"""
from __future__ import annotations

from pathlib import Path

from app.vision_transcribe.prompts import PROMPT_VERSION, build_batch_prompt


def build_prompt(start_page: int, end_page: int) -> str:
    return build_batch_prompt(start_page=start_page, end_page=end_page)


def write_batch_prompt(batch_dir: Path, start_page: int, end_page: int) -> Path:
    batch_dir.mkdir(parents=True, exist_ok=True)
    text = build_prompt(start_page, end_page)
    path = batch_dir / "prompt.txt"
    path.write_text(text, encoding="utf-8")
    meta = batch_dir / "prompt.version"
    meta.write_text(PROMPT_VERSION + "\n", encoding="utf-8")
    return path
