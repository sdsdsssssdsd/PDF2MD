"""从 PDF 渲染 formula / region / page 图，供 Document OCR 使用。"""
from __future__ import annotations

from typing import Any

from app.formula.preprocess import to_pil_image
from app.formula.session import column_bounds


def render_clip(
    page: Any,
    bbox: tuple[float, float, float, float],
    *,
    scale: float = 2.0,
):
    import pymupdf

    x0, y0, x1, y1 = bbox
    clip = pymupdf.Rect(float(x0), float(y0), float(x1), float(y1))
    s = max(1.0, min(float(scale), 3.5))
    pix = page.get_pixmap(matrix=pymupdf.Matrix(s, s), clip=clip, alpha=False)
    return to_pil_image(pix) or pix


def page_bbox(page: Any) -> tuple[float, float, float, float]:
    r = page.rect
    return (0.0, 0.0, float(r.width), float(r.height))


def region_bbox_from_formula(
    page: Any,
    formula_bbox: tuple[float, float, float, float],
    *,
    height_ratio: float = 0.22,
) -> tuple[float, float, float, float]:
    """公式 + 上下文段落：竖向约页面高度 15%~30%，宽度保持所属栏。"""
    page_w = float(page.rect.width)
    page_h = float(page.rect.height)
    fx0, fy0, fx1, fy1 = formula_bbox
    ratio = max(0.15, min(0.30, float(height_ratio)))
    band = page_h * ratio
    cy = (fy0 + fy1) * 0.5
    y0 = max(0.0, cy - band * 0.55)
    y1 = min(page_h, cy + band * 0.45)
    # 用公式框中心决定栏
    mid_x = (fx0 + fx1) * 0.5
    if mid_x >= page_w * 0.5:
        x0, x1 = column_bounds(page_w, page_w * 0.75, page_w * 0.92)
    else:
        x0, x1 = column_bounds(page_w, page_w * 0.08, page_w * 0.35)
    # 保证覆盖公式水平范围
    x0 = min(x0, fx0)
    x1 = max(x1, fx1)
    return (float(x0), float(y0), float(x1), float(y1))
