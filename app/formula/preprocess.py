"""公式裁图预处理：最多 2～3 个变体（原图 / 放大 / 对比度）。"""
from __future__ import annotations

from typing import Any


def to_pil_image(image: Any):
    """PyMuPDF Pixmap / PIL / path → RGB PIL.Image。"""
    try:
        from PIL import Image
    except Exception:
        return None

    if image is None:
        return None
    if hasattr(image, "convert") and hasattr(image, "size"):
        # already PIL-like
        img = image
        if getattr(img, "mode", None) not in ("RGB", "L"):
            img = img.convert("RGB")
        return img
    # PyMuPDF Pixmap
    if hasattr(image, "samples") and hasattr(image, "width"):
        mode = "RGB"
        n = getattr(image, "n", 3)
        if n == 1:
            mode = "L"
        elif n == 4:
            mode = "RGBA"
        img = Image.frombytes(mode, (image.width, image.height), image.samples)
        if mode == "RGBA":
            img = img.convert("RGB")
        elif mode == "L":
            img = img.convert("RGB")
        return img
    if isinstance(image, (str, bytes)):
        try:
            return Image.open(image).convert("RGB")
        except Exception:
            return None
    return None


def formula_image_variants(image: Any, *, attempt: int = 1) -> list[tuple[str, Any]]:
    """按 attempt 返回少量变体（裁图已是高 DPI，这里做增强而非盲目再 2x）。

    Attempt 1: 原图（PDF 已 3x 渲染）
    Attempt 2: 对比度增强
    Attempt 3: 再 1.5x 锐化放大 + 对比度
    """
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps

    base = to_pil_image(image)
    if base is None:
        return [("original", image)]

    out: list[tuple[str, Any]] = [("original", base)]
    if attempt >= 2:
        gray = ImageOps.grayscale(base)
        enhanced = ImageEnhance.Contrast(gray).enhance(1.7)
        out.append(("contrast", enhanced.convert("RGB")))
    if attempt >= 3:
        w, h = base.size
        up = base.resize(
            (max(1, int(w * 1.5)), max(1, int(h * 1.5))),
            Image.Resampling.LANCZOS,
        )
        up = up.filter(ImageFilter.SHARPEN)
        gray = ImageOps.grayscale(up)
        enhanced = ImageEnhance.Contrast(gray).enhance(1.5)
        out.append(("upscale1_5_sharp", enhanced.convert("RGB")))
    return out[:3]


def apply_named_preprocess(image: Any, name: str = "original"):
    """按名字返回单张增强图：original / contrast / sharpen。"""
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps

    base = to_pil_image(image)
    if base is None:
        return image
    key = (name or "original").lower().strip()
    if key in ("original", "none", ""):
        return base
    if key == "contrast":
        gray = ImageOps.grayscale(base)
        return ImageEnhance.Contrast(gray).enhance(1.7).convert("RGB")
    if key in ("sharpen", "upscale1_5_sharp"):
        w, h = base.size
        up = base.resize(
            (max(1, int(w * 1.5)), max(1, int(h * 1.5))),
            Image.Resampling.LANCZOS,
        )
        up = up.filter(ImageFilter.SHARPEN)
        gray = ImageOps.grayscale(up)
        return ImageEnhance.Contrast(gray).enhance(1.5).convert("RGB")
    return base
