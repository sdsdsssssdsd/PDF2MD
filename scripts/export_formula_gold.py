#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 formula_qa / crop cache 导出 Gold 骨架；O-018 五式写入 verified 种子。

机器 selected_latex 只进 machine_pred，绝不标 verified。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.formula.crop_cache import language_from_stem, load_crop_manifest  # noqa: E402
from app.formula.gold_crop import preserve_tight_fields, preserve_verified_fields  # noqa: E402
from app.formula.gold_schema import FormulaGoldRecord  # noqa: E402
from app.ocr.deepseek_benchmark import DEFAULT_O018_CASES  # noqa: E402
from app.ocr.match_eval_v2 import canonicalize_latex  # noqa: E402
from app.utils.paths import EXPERIMENT_DIR, K5_CROPS_DIR, K5_GOLD_DIR, ensure_dirs  # noqa: E402


def _skeleton_from_manifest(manifest: dict) -> list[dict]:
    rows: list[dict] = []
    for crop in manifest.get("crops") or []:
        if not crop.get("crop_ok"):
            continue
        rec = FormulaGoldRecord(
            id=str(crop.get("id") or ""),
            pdf_id=str(crop.get("pdf_id") or ""),
            language=str(crop.get("language") or language_from_stem(str(crop.get("pdf_id") or ""))),
            page=int(crop.get("page") or 0),
            bbox_pdf=list(crop.get("bbox_pdf") or []),
            crop_path=str(crop.get("crop_path") or ""),
            equation_number=str(crop.get("equation_number") or ""),
            gold_latex_raw="",
            gold_latex_canonical="",
            difficulty="medium",
            tags=["needs_human_gt"],
            split="regression",
            verified=False,
            notes="skeleton_only; do_not_train",
            machine_pred=((crop.get("extra") or {}).get("parser_latex") or "")[:400],
        )
        rows.append(rec.to_dict())
    return rows


def _seed_o018(skeleton: list[dict]) -> list[dict]:
    gold_by_eq = {str(c["eq_number"]): str(c["gold_latex"]) for c in DEFAULT_O018_CASES}
    seeded: list[dict] = []
    for row in skeleton:
        if row.get("pdf_id") != "O-018_Abdo2025_Stacking_SHAP":
            continue
        eq = str(row.get("equation_number") or "")
        gold = gold_by_eq.get(eq)
        if not gold:
            continue
        rec = dict(row)
        rec["gold_latex_raw"] = gold
        rec["gold_latex_canonical"] = canonicalize_latex(gold)
        rec["verified"] = True
        rec["tags"] = ["o018_canary", "verified_seed"]
        rec["notes"] = "human_canary_from_DEFAULT_O018_CASES"
        rec["split"] = "regression"
        seeded.append(rec)
    return seeded


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Export gold skeleton + O-018 verified seed")
    p.add_argument("--experiment-dir", default=str(EXPERIMENT_DIR))
    p.add_argument("--crop-manifest", default=str(K5_CROPS_DIR / "manifest.json"))
    p.add_argument("--out-skeleton", default="")
    p.add_argument("--out-verified", default="")
    args = p.parse_args(argv)
    del args.experiment_dir

    ensure_dirs()
    manifest = load_crop_manifest(Path(args.crop_manifest))
    skeleton = _skeleton_from_manifest(manifest)
    verified = _seed_o018(skeleton)

    sk_path = Path(args.out_skeleton) if args.out_skeleton else K5_GOLD_DIR / "core_skeleton.jsonl"
    vf_path = Path(args.out_verified) if args.out_verified else K5_GOLD_DIR / "o018_verified.jsonl"
    skeleton = preserve_tight_fields(skeleton, sk_path)
    skeleton = preserve_verified_fields(skeleton, sk_path)
    verified = preserve_tight_fields(verified, vf_path)
    verified = preserve_verified_fields(verified, vf_path)
    sk_path.parent.mkdir(parents=True, exist_ok=True)
    with sk_path.open("w", encoding="utf-8") as f:
        for row in skeleton:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    with vf_path.open("w", encoding="utf-8") as f:
        for row in verified:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(
        {
            "ok": True,
            "skeleton": str(sk_path),
            "skeleton_n": len(skeleton),
            "verified": str(vf_path),
            "verified_n": len(verified),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
