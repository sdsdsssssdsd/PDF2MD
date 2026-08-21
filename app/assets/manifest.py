"""images/manifest.json 读写。"""
from __future__ import annotations

import json
from pathlib import Path

from app.assets.models import FigureAsset


def build_manifest_payload(
    *,
    source_pdf: str,
    figures: list[FigureAsset],
) -> dict:
    items = []
    for f in figures:
        items.append(
            {
                "asset_id": f.asset_id,
                "asset_index": f.asset_index,
                "file": f.file,
                "page": f.page,
                "figure_label": f.figure_label,
                "caption": f.caption,
                "bbox": f.bbox,
                "parser_source": f.parser_source,
                "parser_file": f.parser_file,
                "confidence": round(f.confidence, 4),
                "subfigure_status": f.subfigure_status,
                "subfigures": [
                    {
                        "index": s.index,
                        "original_label": s.original_label,
                        "file": s.file,
                        "bbox": s.bbox,
                        "confidence": round(s.confidence, 4),
                    }
                    for s in f.subfigures
                ],
            }
        )
    return {
        "source_pdf": source_pdf,
        "figures": items,
    }


def write_manifest(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
