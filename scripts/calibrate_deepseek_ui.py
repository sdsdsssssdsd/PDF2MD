#!/usr/bin/env python
"""DeepSeek UI 校准：在参考截图上点选按钮，写入 data/deepseek_ui.json。

用法：
  python scripts/calibrate_deepseek_ui.py
  python scripts/calibrate_deepseek_ui.py --image "D:\\Docling\\浏览器页面\\1.png"

在窗口里依次点击：
  1. 识图模式（三按钮最右）
  2. 开启新对话（侧栏）
  3. 附件/回形针（可选，回车跳过）

坐标会保存为归一化 (0~1)，适配不同窗口大小。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageTk
import tkinter as tk

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.vision_transcribe.browser.deepseek_ui import DEFAULT_UI_CONFIG, load_ui_config, save_ui_config

STEPS = [
    ("vision_mode", "① 点击「识图模式」（三按钮最右侧）"),
    ("new_chat", "② 点击「开启新对话」（侧栏）"),
    ("attach", "③ 点击输入框「回形针」（可选，按 Esc 跳过）"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--image",
        default=str(ROOT / "浏览器页面" / "1.png"),
        help="参考截图路径",
    )
    args = ap.parse_args()
    img_path = Path(args.image)
    if not img_path.exists():
        print(f"找不到截图: {img_path}")
        return 1

    im = Image.open(img_path).convert("RGB")
    w, h = im.size
    cfg = load_ui_config()
    clicks: dict = dict(cfg.get("clicks") or {})
    step_idx = 0
    root = tk.Tk()
    root.title("DeepSeek UI 校准")
    label = tk.Label(root, text=STEPS[0][1], font=("Microsoft YaHei UI", 11))
    label.pack(padx=8, pady=6)

  # scale to fit screen
    max_w, max_h = 1200, 800
    scale = min(max_w / w, max_h / h, 1.0)
    disp_w, disp_h = int(w * scale), int(h * scale)
    disp = im.resize((disp_w, disp_h), Image.Resampling.LANCZOS)
    photo = ImageTk.PhotoImage(disp)

    canvas = tk.Canvas(root, width=disp_w, height=disp_h)
    canvas.pack()
    canvas.create_image(0, 0, anchor=tk.NW, image=photo)

    def on_click(event) -> None:
        nonlocal step_idx
        key, _ = STEPS[step_idx]
        nx = event.x / disp_w
        ny = event.y / disp_h
        clicks[key] = {"x": round(nx, 4), "y": round(ny, 4), "normalized": True}
        print(f"  {key}: ({nx:.3f}, {ny:.3f})")
        step_idx += 1
        if step_idx >= len(STEPS):
            finish()
            return
        label.config(text=STEPS[step_idx][1])

    def skip(_event=None) -> None:
        nonlocal step_idx
        step_idx += 1
        if step_idx >= len(STEPS):
            finish()
            return
        label.config(text=STEPS[step_idx][1])

    def finish() -> None:
        cfg["clicks"] = clicks
        cfg["click_strategy"] = cfg.get("click_strategy") or "auto"
        cfg["match_threshold"] = cfg.get("match_threshold", 0.72)
        save_ui_config(cfg)
        label.config(text=f"已保存 → {DEFAULT_UI_CONFIG}")
        root.after(1500, root.destroy)

    canvas.bind("<Button-1>", on_click)
    root.bind("<Escape>", skip)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
