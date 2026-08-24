# -*- coding: utf-8 -*-
"""用 o018_verified.jsonl 里冻结的紧框重渲 PNG，并写回骨架。不改生产 crop。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.formula.crop_cache import resolve_pdf, write_crop_png
from app.formula.gold_crop import load_jsonl, render_gold_tight_crop, write_jsonl
from app.utils.paths import K5_CROPS_DIR, K5_GOLD_DIR


def main() -> int:
    verified = load_jsonl(K5_GOLD_DIR / "o018_verified.jsonl")
    skeleton = load_jsonl(K5_GOLD_DIR / "core_skeleton.jsonl")
    by_id = {r["id"]: r for r in verified}
    for row in skeleton:
        src = by_id.get(row.get("id") or "")
        if not src:
            continue
        for k in ("bbox_pdf_tight", "crop_path_tight", "crop_quality"):
            if src.get(k):
                row[k] = src[k]
        pdf = resolve_pdf(str(src["pdf_id"]))
        dest = K5_CROPS_DIR / src["crop_path_tight"]
        image, _ = render_gold_tight_crop(pdf, int(src["page"]), list(src["bbox_pdf_tight"]))
        write_crop_png(image, dest)
        print("restored", src["id"], dest)
    write_jsonl(K5_GOLD_DIR / "core_skeleton.jsonl", skeleton)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
