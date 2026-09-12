"""按 bbox 从原图裁切。"""
from __future__ import annotations

from pathlib import Path

from app.daily_vision.models import FigureRegion


def crop_regions(
    image_paths: list[Path],
    regions: list[FigureRegion],
    out_dir: Path,
) -> dict[str, Path]:
    try:
        from PIL import Image
    except ImportError:
        return {}

    out_dir.mkdir(parents=True, exist_ok=True)
    mapping: dict[str, Path] = {}
    for reg in regions:
        idx = max(1, reg.source_image) - 1
        if idx >= len(image_paths):
            continue
        src = Path(image_paths[idx])
        if not src.is_file():
            continue
        marker = reg.marker.replace(":", "_")
        out_path = out_dir / f"{marker}.png"
        try:
            with Image.open(src) as im:
                w, h = im.size
                bbox = reg.bbox
                if len(bbox) == 4 and all(0 <= v <= 1.05 for v in bbox):
                    x0 = int(bbox[0] * w)
                    y0 = int(bbox[1] * h)
                    x1 = int(bbox[2] * w)
                    y1 = int(bbox[3] * h)
                    if x1 > x0 and y1 > y0:
                        crop = im.crop((x0, y0, x1, y1))
                        crop.save(out_path)
                        mapping[reg.marker] = out_path
                        continue
                im.save(out_path)
                mapping[reg.marker] = out_path
        except Exception:
            try:
                out_path.write_bytes(src.read_bytes())
                mapping[reg.marker] = out_path
            except Exception:
                pass
    return mapping
