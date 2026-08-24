# -*- coding: utf-8 -*-
"""VLM 输入垫边：同一张紧 crop 像素，只改画布。不改生产 bbox。"""
from __future__ import annotations

from typing import Any


def letterbox_formula_crop_for_vlm(
    image: Any,
    *,
    min_h: int = 160,
    min_w: int = 320,
    multiple: int = 32,
    pad: int = 16,
) -> Any:
    from PIL import Image

    im = image.convert("RGB") if hasattr(image, "convert") else Image.open(image).convert("RGB")
    w, h = im.size
    nw = max(w + 2 * pad, int(min_w))
    nh = max(h + 2 * pad, int(min_h))
    m = max(1, int(multiple))
    nw = ((nw + m - 1) // m) * m
    nh = ((nh + m - 1) // m) * m
    canvas = Image.new("RGB", (nw, nh), (255, 255, 255))
    canvas.paste(im, ((nw - w) // 2, (nh - h) // 2))
    return canvas
