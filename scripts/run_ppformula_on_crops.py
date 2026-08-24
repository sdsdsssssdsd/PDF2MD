#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在 .venv-paddle-formula 里对冻结 crop 跑 PP-FormulaNet（不进 GUI）。"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", required=True)
    ap.add_argument("--model", default="PP-FormulaNet_plus-M")
    ap.add_argument("--crop-root", default=str(ROOT / "benchmarks" / "crops"))
    ap.add_argument(
        "--prefer-tight",
        action="store_true",
        help="Use crop_path_tight (Gold-only). Production crop_path stays untouched.",
    )
    ap.add_argument("--out", default="")
    ap.add_argument(
        "--include-unverified",
        action="store_true",
        help="Also dump preds for skeleton rows. Exact only counted when verified gold exists.",
    )
    args = ap.parse_args()

    from paddleocr import FormulaRecognition

    from app.ocr.match_eval_v2 import FormulaMatchEvaluatorV2, summarize_reports

    gold_path = Path(args.gold)
    crop_root = Path(args.crop_root)
    ev = FormulaMatchEvaluatorV2(compute_cdm=False)
    model = FormulaRecognition(model_name=args.model)
    reports = []
    details = []
    total = sum(1 for line in gold_path.read_text(encoding="utf-8").splitlines() if line.strip())
    done = 0
    for line in gold_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        verified = bool(row.get("verified"))
        if not verified and not args.include_unverified:
            continue
        rel = (row.get("crop_path_tight") if args.prefer_tight else row.get("crop_path")) or ""
        crop = crop_root / rel if rel else crop_root / "_missing.png"
        pred = ""
        err = ""
        if args.prefer_tight and not row.get("crop_path_tight"):
            err = "tight_crop_missing"
        elif crop.is_file():
            try:
                out = list(model.predict(str(crop)))
                item = out[0] if out else {}
                pred = str((item or {}).get("rec_formula") or "")
            except Exception as e:
                err = f"{type(e).__name__}:{e}"
        else:
            err = "crop_missing"
        gold = row.get("gold_latex_raw") or ""
        if verified and str(gold).strip():
            report = ev.compare(pred, gold)
            reports.append(report)
            scored = report.to_dict()
        else:
            scored = {"strict_canonical_exact": None, "reasons": ["no_gold"]}
        details.append(
            {
                "id": row.get("id"),
                "equation_number": row.get("equation_number"),
                "verified": verified,
                "pred": pred,
                "gold": gold,
                "error": err,
                **scored,
            }
        )
        done += 1
        if done % 20 == 0 or done == total:
            print(f"[{args.model}] {done}/{total}", flush=True)

    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "model": args.model,
        "gold": str(gold_path),
        "summary": summarize_reports(reports),
        "details": details,
        "shadow_only": True,
        "prefer_tight": bool(args.prefer_tight),
        "include_unverified": bool(args.include_unverified),
        "do_not_train": True,
    }
    out = Path(args.out) if args.out else ROOT / "benchmarks" / "results" / "pp_m_o018.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out)
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
