#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Academic100 display 式收割。不标 verified，不训练，不改生产 crop。"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.formula.gold_crop import build_gold_tight_crops, load_jsonl, write_jsonl
from app.formula.gold_harvest import harvest_pdf
from app.utils.paths import K5_GOLD_DIR, K5_MANIFESTS_DIR, K5_TIGHT_CROPS_DIR, TESTSET_DIR, ensure_dirs


def _existing_keys() -> tuple[set[tuple[str, int, str]], set[tuple[str, str]]]:
    keys: set[tuple[str, int, str]] = set()
    eqs: set[tuple[str, str]] = set()
    for name in ("core_skeleton.jsonl", "o018_verified.jsonl", "human_verified_v2.jsonl", "harvest_display.jsonl"):
        path = K5_GOLD_DIR / name
        for row in load_jsonl(path):
            pdf_id = str(row.get("pdf_id") or "")
            eq = str(row.get("equation_number") or "")
            if pdf_id and eq:
                page = int(row.get("page") or 0)
                keys.add((pdf_id, page, eq))
                keys.add((pdf_id, page - 1, eq))
                keys.add((pdf_id, page + 1, eq))
                eqs.add((pdf_id, eq))
    return keys, eqs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-paper", type=int, default=3)
    ap.add_argument("--per-lang", type=int, default=40)
    ap.add_argument("--no-crops", action="store_true")
    args = ap.parse_args()
    ensure_dirs()
    man_path = K5_MANIFESTS_DIR / "academic100_regression_v1.json"
    papers = json.loads(man_path.read_text(encoding="utf-8")).get("papers") or []
    skip, skip_eqs = _existing_keys()
    out = K5_GOLD_DIR / "harvest_display.jsonl"
    harvested: list[dict] = load_jsonl(out)
    counts = {"en": 0, "zh": 0}
    for row in harvested:
        lang = str(row.get("language") or "en")
        counts[lang] = counts.get(lang, 0) + 1
    for paper in papers:
        lang = str(paper.get("language") or "en")
        if counts.get(lang, 0) >= args.per_lang:
            continue
        pdf_id = str(paper.get("pdf_id") or "")
        pdf = TESTSET_DIR / str(paper.get("filename") or f"{pdf_id}.pdf")
        if not pdf.is_file():
            continue
        rows = harvest_pdf(
            pdf,
            pdf_id=pdf_id,
            language=lang,
            skip_keys=skip,
            per_paper=args.per_paper,
        )
        rows = [r for r in rows if (r["pdf_id"], str(r["equation_number"])) not in skip_eqs]
        keep = args.per_lang - counts.get(lang, 0)
        rows = rows[:keep]
        harvested.extend(rows)
        counts[lang] = counts.get(lang, 0) + len(rows)
        for row in rows:
            skip.add((row["pdf_id"], int(row["page"]), str(row["equation_number"])))
            skip_eqs.add((row["pdf_id"], str(row["equation_number"])))
        if counts["en"] >= args.per_lang and counts["zh"] >= args.per_lang:
            break

    write_jsonl(out, harvested)
    crop_n = 0
    new_rows = [r for r in harvested if not r.get("crop_path_tight")]
    if new_rows and not args.no_crops:
        man = build_gold_tight_crops(
            new_rows,
            out_dir=K5_TIGHT_CROPS_DIR,
            update_records=True,
            write_manifest=True,
            manifest_name="harvest_manifest.json",
        )
        write_jsonl(out, harvested)
        crop_n = int(man.get("ok") or 0)
    summary = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "n": len(harvested),
        "english": counts["en"],
        "chinese": counts["zh"],
        "tight_ok": crop_n,
        "do_not_train": True,
        "verified": 0,
        "out": str(out),
    }
    (K5_GOLD_DIR / "harvest_display_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
