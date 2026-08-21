"""从主图裁切子图（派生资源；永不删除主图）。"""
from __future__ import annotations

from pathlib import Path

from app.assets.subfigure_detector import SubfigurePlan


def render_subfigures(
    composite_path: Path,
    plans: list[SubfigurePlan],
    *,
    out_dir: Path,
    parent_index: int,
    pdf_stem: str,
) -> list[tuple[SubfigurePlan, Path]]:
    """按归一化 bbox 裁切；失败则返回已成功的子集（调用方应整体放弃）。"""
    try:
        from PIL import Image
    except ImportError as e:
        raise RuntimeError("Pillow required for subfigure crop") from e

    out_dir.mkdir(parents=True, exist_ok=True)
    img = Image.open(composite_path).convert("RGBA")
    w, h = img.size
    results: list[tuple[SubfigurePlan, Path]] = []
    ext = composite_path.suffix.lower() or ".png"
    for p in plans:
        x1, y1, x2, y2 = p.bbox
        left = max(0, min(w - 1, int(x1 * w)))
        top = max(0, min(h - 1, int(y1 * h)))
        right = max(left + 1, min(w, int(x2 * w)))
        bottom = max(top + 1, min(h, int(y2 * h)))
        crop = img.crop((left, top, right, bottom))
        name = f"image_{parent_index}-{p.index}_{pdf_stem}{ext}"
        dest = out_dir / name
        if ext in {".jpg", ".jpeg"}:
            crop.convert("RGB").save(dest, quality=95)
        else:
            crop.save(dest)
        results.append((p, dest))
    return results
