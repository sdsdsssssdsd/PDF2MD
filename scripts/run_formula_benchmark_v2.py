#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""k5 Formula benchmark v2：Recognition-only 或对照评测（不写生产 Markdown）。

  python scripts/run_formula_benchmark_v2.py --gold benchmarks/gold/core.jsonl --fake
  python scripts/run_formula_benchmark_v2.py --gold ... --backends P1,P2 --mode recognition
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.formula.backends import is_pp_formulanet, paddle_model_name  # noqa: E402
from app.formula.gold_schema import FormulaGoldRecord, validate_gold_record  # noqa: E402
from app.ocr.k5_experiments import K5_EXPERIMENTS  # noqa: E402
from app.ocr.match_eval_v2 import FormulaMatchEvaluatorV2, summarize_reports  # noqa: E402
from app.utils.paths import K5_CROPS_DIR, K5_RESULTS_DIR, ensure_dirs  # noqa: E402


def _load_gold(path: Path, *, require_crop: bool = False) -> list[FormulaGoldRecord]:
    rows: list[FormulaGoldRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        issues = validate_gold_record(obj)
        if "missing_id" in issues:
            continue
        rec = FormulaGoldRecord.from_dict(obj)
        if not rec.verified or not rec.gold_latex_raw.strip():
            continue
        if require_crop and not (rec.crop_path.strip() or rec.crop_path_tight.strip()):
            continue
        rows.append(rec)
    return rows


def _crop_file(rec: FormulaGoldRecord, *, prefer_tight: bool) -> Path | None:
    rel = ""
    if prefer_tight and rec.crop_path_tight.strip():
        rel = rec.crop_path_tight.strip()
    elif rec.crop_path.strip():
        rel = rec.crop_path.strip()
    if not rel:
        return None
    path = K5_CROPS_DIR / rel
    return path if path.is_file() else None


def _predict_real(backend: str, rec: FormulaGoldRecord, *, prefer_tight: bool) -> str:
    crop = _crop_file(rec, prefer_tight=prefer_tight)
    if crop is None:
        return ""
    if is_pp_formulanet(backend):
        from PIL import Image

        from app.formula.ppformula_worker_recognizer import PPFormulaWorkerRecognizer

        recg = PPFormulaWorkerRecognizer(model_name=paddle_model_name(backend))
        out = recg.recognize(Image.open(crop))
        return (out.latex or "").strip()
    return ""


def _fake_predict(backend: str, gold: str) -> str:
    if backend == "docling":
        return gold
    if "deepseek" in backend:
        # 故意制造子串伪 exact，验证 v2 不把它当 strict
        return gold + r"\quad extra"
    if backend.endswith("_m"):
        return gold
    if backend.endswith("_l"):
        return gold
    if "paddleocr" in backend:
        return gold
    return gold


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="k5 formula benchmark v2")
    p.add_argument("--gold", required=True, help="JSONL gold (verified rows only)")
    p.add_argument("--backends", default="L2,P1,P2,P3")
    p.add_argument("--mode", choices=("recognition", "production"), default="recognition")
    p.add_argument("--fake", action="store_true", help="No GPU; use gold echo / controlled mismatch")
    p.add_argument("--out-dir", default="")
    p.add_argument(
        "--require-crop",
        action="store_true",
        help="Skip verified rows without crop_path (recognition-only)",
    )
    p.add_argument(
        "--prefer-tight",
        action="store_true",
        help="Use crop_path_tight when present (Gold-only; default on for --mode recognition)",
    )
    p.add_argument(
        "--production-crop",
        action="store_true",
        help="Force production crop_path even in recognition mode",
    )
    args = p.parse_args(argv)

    gold_path = Path(args.gold)
    if not gold_path.is_file():
        print(f"gold not found: {gold_path}", file=sys.stderr)
        return 2

    ensure_dirs()
    records = _load_gold(gold_path, require_crop=bool(args.require_crop))
    ids = [x.strip().upper() for x in args.backends.split(",") if x.strip()]
    unknown = [i for i in ids if i not in K5_EXPERIMENTS]
    if unknown:
        print(f"unknown backends: {unknown}", file=sys.stderr)
        return 2

    prefer_tight = args.mode == "recognition"
    if args.production_crop:
        prefer_tight = False
    if args.prefer_tight:
        prefer_tight = True

    ev = FormulaMatchEvaluatorV2(compute_cdm=False)
    out_root = Path(args.out_dir) if args.out_dir else K5_RESULTS_DIR
    out_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    batch: dict = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "mode": args.mode,
        "fake": bool(args.fake),
        "prefer_tight": prefer_tight,
        "gold": str(gold_path),
        "n_verified": len(records),
        "note": "Recognition-only on verified gold; tight crops when prefer_tight. Never write production Markdown.",
        "experiments": {},
    }

    for eid in ids:
        spec = K5_EXPERIMENTS[eid]
        reports = []
        details = []
        for rec in records:
            if args.fake:
                pred = _fake_predict(spec.backend, rec.gold_latex_raw)
            elif spec.backend == "docling":
                pred = rec.machine_pred.strip()
            else:
                pred = _predict_real(spec.backend, rec, prefer_tight=prefer_tight)
            report = ev.compare(pred, rec.gold_latex_raw)
            reports.append(report)
            details.append(
                {
                    "id": rec.id,
                    "pdf_id": rec.pdf_id,
                    "language": rec.language,
                    "backend": spec.backend,
                    **report.to_dict(),
                }
            )
        batch["experiments"][eid] = {
            "spec": spec.label,
            "backend": spec.backend,
            "role": spec.role,
            "summary": summarize_reports(reports),
            "n": len(details),
        }

    out = out_root / f"k5_v2_{args.mode}_{stamp}.json"
    out.write_text(json.dumps(batch, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out)
    print(json.dumps({k: v["summary"] for k, v in batch["experiments"].items()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
