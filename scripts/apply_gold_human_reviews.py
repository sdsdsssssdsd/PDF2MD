#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把人工核验写进骨架 / extra verified。不改 O-018 canary，不改生产 crop。"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.formula.gold_schema import FormulaGoldRecord, validate_gold_record  # noqa: E402
from app.ocr.match_eval_v2 import canonicalize_latex  # noqa: E402
from app.utils.paths import K5_GOLD_DIR  # noqa: E402


def _load_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _dump_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8",
    )


def _load_reviews() -> dict[str, dict]:
    by_id: dict[str, dict] = {}
    for name in ("human_reviews_20260823.json", "human_reviews_harvest.json"):
        path = K5_GOLD_DIR / name
        if not path.is_file():
            continue
        spec = json.loads(path.read_text(encoding="utf-8"))
        for r in spec.get("reviews") or []:
            if r.get("id"):
                by_id[str(r["id"])] = r
    return by_id


def _apply_one(
    row: dict,
    rev: dict,
    *,
    verified: list[dict],
    issues: list[str],
    keep_tags: list[str] | None = None,
) -> str:
    action = str(rev.get("action") or "")
    quality = list(row.get("crop_quality") or [])
    for tag in rev.get("crop_quality") or []:
        if tag not in quality:
            quality.append(tag)
    row["crop_quality"] = quality
    if action == "verify":
        gold = str(rev.get("gold_latex_raw") or "").strip()
        rec = dict(row)
        rec["gold_latex_raw"] = gold
        rec["gold_latex_canonical"] = canonicalize_latex(gold)
        rec["verified"] = True
        rec["equation_number"] = str(rev.get("equation_number") or rec.get("equation_number") or "")
        tags = ["human_verified", "tight_crop_ok"]
        for extra in keep_tags or []:
            if extra not in tags:
                tags.append(extra)
        rec["tags"] = tags
        rec["notes"] = str(rev.get("notes") or "human_from_tight_crop")
        rec["split"] = "regression"
        bad = validate_gold_record(rec)
        if bad:
            issues.append(f"{rec.get('id')}:{bad}")
            return "issue"
        row.update(rec)
        verified.append(FormulaGoldRecord.from_dict(rec).to_dict())
        return "verify"
    if action == "reject":
        row["verified"] = False
        row["gold_latex_raw"] = ""
        row["gold_latex_canonical"] = ""
        row["notes"] = str(rev.get("notes") or "human_reject")
        tags = [t for t in (row.get("tags") or []) if t != "verified_seed"]
        if "needs_human_gt" not in tags:
            tags.append("needs_human_gt")
        if "crop_rejected" not in tags:
            tags.append("crop_rejected")
        row["tags"] = tags
        return "reject"
    return ""


def main() -> int:
    reviews_path = K5_GOLD_DIR / "human_reviews_20260823.json"
    skeleton_path = K5_GOLD_DIR / "core_skeleton.jsonl"
    harvest_path = K5_GOLD_DIR / "harvest_display.jsonl"
    extra_path = K5_GOLD_DIR / "human_verified_v2.jsonl"
    by_id = _load_reviews()
    skeleton = _load_jsonl(skeleton_path)
    harvest = _load_jsonl(harvest_path)
    verified: list[dict] = []
    n_verify = n_reject = 0
    issues: list[str] = []

    for row in skeleton:
        gid = str(row.get("id") or "")
        rev = by_id.get(gid)
        if not rev:
            continue
        result = _apply_one(row, rev, verified=verified, issues=issues)
        if result == "verify":
            n_verify += 1
        elif result == "reject":
            n_reject += 1

    for row in harvest:
        gid = str(row.get("id") or "")
        rev = by_id.get(gid)
        if not rev:
            continue
        result = _apply_one(
            row, rev, verified=verified, issues=issues, keep_tags=["harvest_display"]
        )
        if result == "verify":
            n_verify += 1
        elif result == "reject":
            n_reject += 1

    if issues:
        print({"ok": False, "issues": issues})
        return 1

    _dump_jsonl(skeleton_path, skeleton)
    _dump_jsonl(harvest_path, harvest)
    _dump_jsonl(extra_path, verified)
    summary = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "reviews": str(reviews_path),
        "verify": n_verify,
        "reject": n_reject,
        "extra_verified": str(extra_path),
        "o018_canary_untouched": True,
        "production_crops_untouched": True,
        "do_not_train": True,
    }
    (K5_GOLD_DIR / "human_reviews_20260823_applied.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
