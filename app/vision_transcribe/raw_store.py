"""批次 raw 层元数据与分析报告持久化。"""
from __future__ import annotations

import json
from pathlib import Path

from app.vision_transcribe.models import VisionQualityReport


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def save_metadata(batch_dir: Path, data: dict) -> None:
    save_json(batch_dir / "metadata.json", data)


def save_analysis(batch_dir: Path, report: VisionQualityReport) -> None:
    save_json(batch_dir / "analysis.json", report.to_dict())


def load_analysis(batch_dir: Path) -> dict:
    path = batch_dir / "analysis.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}
