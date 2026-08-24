#!/usr/bin/env python
"""校准 DeepSeek 发送箭头模板 send.png。

用法：
  python scripts/calibrate_deepseek_send.py
  python scripts/calibrate_deepseek_send.py --image path/to/screenshot.png

在截图上框选蓝色圆形发送箭头（含白箭头），保存到 data/deepseek_templates/send.png
并更新 data/deepseek_ui.json 的 templates.send。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageTk
import tkinter as tk

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.vision_transcribe.browser.deepseek_ui import DEFAULT_UI_CONFIG, load_ui_config, save_ui_config

TPL_DIR = ROOT / "data" / "deepseek_templates"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--image",
        default=str(ROOT / "浏览器页面" / "1.png"),
        help="含发送箭头的参考截图",
    )
    args = ap.parse_args()
    img_path = Path(args.image)
    if not img_path.exists():
        print(f"找不到截图: {img_path}")
        return 1

    im = Image.open(img_path).convert("RGB")
    w, h = im.size
    root = tk.Tk()
    root.title("DeepSeek 发送箭头校准")
    label = tk.Label(
        root,
        text="拖拽框选蓝色圆形发送箭头（松开鼠标保存）",
        font=("Microsoft YaHei UI", 11),
    )
    label.pack(padx=8, pady=6)

    max_w, max_h = 1200, 800
    scale = min(max_w / w, max_h / h, 1.0)
    disp_w, disp_h = int(w * scale), int(h * scale)
    disp = im.resize((disp_w, disp_h), Image.Resampling.LANCZOS)
    photo = ImageTk.PhotoImage(disp)

    canvas = tk.Canvas(root, width=disp_w, height=disp_h, cursor="cross")
    canvas.pack()
    canvas.create_image(0, 0, anchor=tk.NW, image=photo)

    start: list[int] = []
    rect_id: int | None = None

    def on_press(event) -> None:
        nonlocal rect_id
        start[:] = [event.x, event.y]
        if rect_id is not None:
            canvas.delete(rect_id)
        rect_id = canvas.create_rectangle(event.x, event.y, event.x, event.y, outline="#1a56db", width=2)

    def on_drag(event) -> None:
        if not start or rect_id is None:
            return
        canvas.coords(rect_id, start[0], start[1], event.x, event.y)

    def on_release(event) -> None:
        if not start:
            return
        x0, y0 = start[0], start[1]
        x1, y1 = event.x, event.y
        if abs(x1 - x0) < 8 or abs(y1 - y0) < 8:
            label.config(text="选区太小，请重新拖拽框选发送箭头")
            return
        left = int(min(x0, x1) / scale)
        top = int(min(y0, y1) / scale)
        right = int(max(x0, x1) / scale)
        bottom = int(max(y0, y1) / scale)
        crop = im.crop((left, top, right, bottom))
        TPL_DIR.mkdir(parents=True, exist_ok=True)
        out = TPL_DIR / "send.png"
        crop.save(out)
        cfg = load_ui_config()
        templates = dict(cfg.get("templates") or {})
        templates["send"] = {
            "file": str(out.relative_to(ROOT)).replace("/", "\\"),
            "gray_file": str((TPL_DIR / "send_gray.png").relative_to(ROOT)).replace("/", "\\")
            if (TPL_DIR / "send_gray.png").exists()
            else None,
            "search_roi": [0.62, 0.70, 1.0, 1.0],
            "threshold": 0.62,
            "locate_threshold": 0.55,
            "poll_ms": 80,
            "require_blue": True,
        }
        if templates["send"]["gray_file"] is None:
            del templates["send"]["gray_file"]
        cfg["templates"] = templates
        save_ui_config(cfg)
        label.config(text=f"已保存 {out} ({crop.size[0]}x{crop.size[1]})")
        print(f"saved {out} size={crop.size}")
        root.after(1200, root.destroy)

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
