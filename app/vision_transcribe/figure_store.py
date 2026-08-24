"""裁剪整页图并保存到 figures/。"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from app.vision_transcribe.manifest import vision_dir
from app.vision_transcribe.models import FigureRecord, figure_png_name, page_png_name


def figures_dir(output_dir: Path) -> Path:
    d = output_dir / "figures"
    d.mkdir(parents=True, exist_ok=True)
    return d


def bookfigure_path(output_dir: Path, page: int) -> Path:
    return output_dir / "bookfigures" / page_png_name(page)


def crop_and_save(
    output_dir: Path,
    record: FigureRecord,
    bbox: tuple[float, float, float, float],
    *,
    source: Path | None = None,
) -> FigureRecord:
    """bbox = (x0, y0, x1, y1) 像素坐标，相对 bookfigures 页图。"""
    src = source or bookfigure_path(output_dir, record.page)
    if not src.exists():
        raise FileNotFoundError(str(src))
    img = Image.open(src).convert("RGB")
    x0, y0, x1, y1 = bbox
    x0, y0 = max(0, int(x0)), max(0, int(y0))
    x1, y1 = min(img.width, int(x1)), min(img.height, int(y1))
    if x1 <= x0 or y1 <= y0:
        raise ValueError(f"非法 bbox: {bbox}")
    crop = img.crop((x0, y0, x1, y1))
    name = figure_png_name(record.page, record.index)
    dest = figures_dir(output_dir) / name
    crop.save(dest, format="PNG", optimize=True)
    record.file = f"figures/{name}"
    record.bbox = [float(x0), float(y0), float(x1), float(y1)]
    record.status = "done"
    return record


def save_figures_json(output_dir: Path, figures: list[FigureRecord]) -> Path:
    path = vision_dir(output_dir) / "figures.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [
        {
            "marker": f.marker,
            "page": f.page,
            "index": f.index,
            "file": f.file,
            "bbox": f.bbox,
            "status": f.status,
        }
        for f in figures
    ]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_figures_json(output_dir: Path) -> list[FigureRecord]:
    path = vision_dir(output_dir) / "figures.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    out: list[FigureRecord] = []
    for item in data:
        out.append(
            FigureRecord(
                marker=str(item["marker"]),
                page=int(item["page"]),
                index=int(item.get("index", 1)),
                file=str(item.get("file", "")),
                bbox=list(item.get("bbox") or []),
                status=str(item.get("status", "pending")),
            )
        )
    return out
