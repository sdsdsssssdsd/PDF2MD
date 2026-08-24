#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gold-only 紧裁图。不改生产 bbox / 不覆盖 benchmarks/crops 生产缓存。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.formula.gold_crop import (  # noqa: E402
    build_gold_tight_crops,
    load_jsonl,
    write_jsonl,
)
from app.utils.paths import K5_GOLD_DIR, ensure_dirs  # noqa: E402

try:
    from app.utils.paths import K5_TIGHT_CROPS_DIR  # noqa: E402
except ImportError:
    from app.utils.paths import K5_CROPS_DIR  # noqa: E402

    K5_TIGHT_CROPS_DIR = K5_CROPS_DIR / "tight"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Build gold-only tight crops (no production bbox change)")
    p.add_argument("--gold", default=str(K5_GOLD_DIR / "o018_verified.jsonl"))
    p.add_argument("--also-skeleton", default="", help="optional core_skeleton.jsonl for quality tags")
    p.add_argument("--out-dir", default=str(K5_TIGHT_CROPS_DIR))
    p.add_argument("--no-update-gold", action="store_true")
    p.add_argument(
        "--only-rejected",
        action="store_true",
        help="Rebuild tight crops only for crop_rejected / unverified rows. Verified Gold images stay.",
    )
    args = p.parse_args(argv)

    ensure_dirs()
    gold_path = Path(args.gold)
    rows = load_jsonl(gold_path)
    if not rows:
        print(json.dumps({"ok": False, "error": "empty_gold", "gold": str(gold_path)}))
        return 1

    sk_path = Path(args.also_skeleton) if args.also_skeleton else None
    sk_rows: list[dict] = []
    if sk_path and sk_path.is_file():
        sk_rows = load_jsonl(sk_path)

    seen: set[str] = {str(r.get("id") or "") for r in rows}
    work = list(rows) + [r for r in sk_rows if str(r.get("id") or "") not in seen]
    if args.only_rejected:
        verified_ids = {
            str(r.get("id") or "")
            for r in rows + sk_rows
            if r.get("verified") and str(r.get("gold_latex_raw") or "").strip()
        }
        extra_verified = K5_GOLD_DIR / "o018_verified.jsonl"
        if extra_verified.is_file():
            verified_ids.update(
                str(r.get("id") or "")
                for r in load_jsonl(extra_verified)
                if r.get("verified")
            )
        extra_v2 = K5_GOLD_DIR / "human_verified_v2.jsonl"
        if extra_v2.is_file():
            verified_ids.update(
                str(r.get("id") or "")
                for r in load_jsonl(extra_v2)
                if r.get("verified")
            )
        work = [r for r in work if str(r.get("id") or "") not in verified_ids]
    man = build_gold_tight_crops(
        work,
        out_dir=Path(args.out_dir),
        update_records=True,
    )
    # skeleton 里与 verified 同 id 的行同步紧裁字段
    by_id = {str(r.get("id") or ""): r for r in work}
    for row in sk_rows:
        src = by_id.get(str(row.get("id") or ""))
        if not src:
            continue
        for k in ("bbox_pdf_tight", "crop_path_tight", "crop_quality"):
            if src.get(k):
                row[k] = src[k]

    if not args.no_update_gold:
        write_jsonl(gold_path, rows)
        if sk_path and sk_rows:
            write_jsonl(sk_path, sk_rows)

    print(
        json.dumps(
            {
                "ok": True,
                "n": man.get("n"),
                "ok_n": man.get("ok"),
                "failed": man.get("failed"),
                "out_dir": str(args.out_dir),
                "gold": str(gold_path),
                "skeleton": str(sk_path) if sk_path else "",
                "production_bbox_unchanged": True,
            },
            ensure_ascii=False,
        )
    )
    return 0 if man.get("failed", 0) == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
