#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重裁骨架里 crop_rejected 行。不改生产 bbox，不标 verified。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.formula.crop_cache import resolve_pdf
from app.formula.gold_crop import (
    build_gold_tight_crops,
    load_jsonl,
    text_in_bbox,
    write_jsonl,
)
from app.utils.paths import K5_GOLD_DIR, K5_TIGHT_CROPS_DIR, ensure_dirs


def main() -> int:
    ensure_dirs()
    sk_path = K5_GOLD_DIR / "core_skeleton.jsonl"
    rows = load_jsonl(sk_path)
    work = [
        r
        for r in rows
        if "crop_rejected" in (r.get("tags") or []) and not r.get("verified")
    ]
    if not work:
        print(json.dumps({"ok": True, "n": 0, "note": "no_rejected"}))
        return 0
    man = build_gold_tight_crops(
        work,
        out_dir=K5_TIGHT_CROPS_DIR,
        update_records=True,
        write_manifest=True,
        manifest_name="salvage_manifest.json",
    )
    id_map = {r["id"]: r for r in work}
    for row in rows:
        upd = id_map.get(row.get("id"))
        if upd:
            for k in ("bbox_pdf_tight", "crop_path_tight", "crop_quality"):
                if upd.get(k):
                    row[k] = upd[k]
    write_jsonl(sk_path, rows)

    previews = []
    import pymupdf

    for row in work:
        pdf = resolve_pdf(str(row.get("pdf_id") or ""))
        prev = {"id": row.get("id"), "quality": row.get("crop_quality"), "text": ""}
        if pdf and row.get("bbox_pdf_tight"):
            doc = pymupdf.open(str(pdf))
            try:
                page_i = int(row.get("page") or 0)
                idx = page_i if page_i < len(doc) else max(0, page_i - 1)
                if 0 <= idx < len(doc):
                    prev["text"] = text_in_bbox(doc[idx], row["bbox_pdf_tight"])[:240]
            finally:
                doc.close()
        previews.append(prev)
    out = {
        "ok": True,
        "n": len(work),
        "tight_ok": man.get("ok"),
        "do_not_train": True,
        "verified": 0,
        "previews": previews,
    }
    (K5_GOLD_DIR / "salvage_rejected_preview.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(out, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
