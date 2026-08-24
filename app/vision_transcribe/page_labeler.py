"""页面图片顶部机器页码横幅（仅服务视觉模型，不进最终 Markdown）。"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def add_page_label(
    image_path: Path,
    page: int,
    *,
    banner_px: int = 48,
    inplace: bool = True,
    out_path: Path | None = None,
) -> Path:
    """在图片顶部加白边并写 PDF2MD PAGE XXXX。"""
    img = Image.open(image_path).convert("RGB")
    w, h = img.size
    banner = max(24, int(banner_px))
    canvas = Image.new("RGB", (w, h + banner), (255, 255, 255))
    canvas.paste(img, (0, banner))
    draw = ImageDraw.Draw(canvas)
    label = f"PDF2MD PAGE {page:04d}"
    try:
        font = ImageFont.truetype("arial.ttf", size=max(16, banner // 2))
    except OSError:
        font = ImageFont.load_default()
    # 粗略居左上
    draw.text((12, max(4, (banner - 18) // 2)), label, fill=(20, 20, 20), font=font)
    dest = out_path or image_path
    if not inplace and out_path is None:
        dest = image_path
    canvas.save(dest, format="PNG", optimize=True)
    return Path(dest)
