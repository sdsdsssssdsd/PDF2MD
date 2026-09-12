"""Correction 审计报告 sidecar。"""
from __future__ import annotations

import json
from pathlib import Path

from app.correction.models import CorrectionResult


def correction_report_path(md_path: Path) -> Path:
    md_path = Path(md_path)
    return md_path.with_name(f"{md_path.stem}.correction.json")


def write_correction_report(
    md_path: Path,
    result: CorrectionResult,
    *,
    merge_repair: Path | None = None,
) -> Path | None:
    if not md_path:
        return None
    report_path = correction_report_path(md_path)
    payload = result.to_report_dict()
    payload["output_md"] = str(md_path)
    if merge_repair and merge_repair.is_file():
        try:
            repair = json.loads(merge_repair.read_text(encoding="utf-8"))
            if isinstance(repair, dict):
                repair["correction"] = payload
                merge_repair.write_text(
                    json.dumps(repair, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
        except (OSError, json.JSONDecodeError):
            pass
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return report_path
