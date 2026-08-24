#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用当前 MatchEvaluator v2 重打已有 pred（不重跑模型、不写生产）。"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ocr.match_eval_v2 import FormulaMatchEvaluatorV2, summarize_reports  # noqa: E402
from app.utils.paths import K5_RESULTS_DIR  # noqa: E402


def rescore_payload(payload: dict) -> dict:
    ev = FormulaMatchEvaluatorV2(compute_cdm=False)
    reports = []
    details = []
    for row in payload.get("details") or []:
        pred = str(row.get("pred") or "")
        gold = str(row.get("gold") or row.get("gold_latex_raw") or "")
        report = ev.compare(pred, gold)
        reports.append(report)
        details.append(
            {
                **{k: v for k, v in row.items() if k not in report.to_dict()},
                "pred": pred,
                "gold": gold,
                **report.to_dict(),
            }
        )
    out = dict(payload)
    out["rescored_at"] = datetime.now().isoformat(timespec="seconds")
    out["evaluator"] = "match_eval_v2"
    out["summary"] = summarize_reports(reports)
    out["details"] = details
    return out


def rescore_gold_machine_pred(gold_path: Path) -> dict:
    ev = FormulaMatchEvaluatorV2(compute_cdm=False)
    reports = []
    details = []
    for line in gold_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if not row.get("verified"):
            continue
        pred = str(row.get("machine_pred") or "")
        gold = str(row.get("gold_latex_raw") or "")
        report = ev.compare(pred, gold)
        reports.append(report)
        details.append(
            {
                "id": row.get("id"),
                "equation_number": row.get("equation_number"),
                "pred": pred,
                "gold": gold,
                "source": "machine_pred_docling",
                **report.to_dict(),
            }
        )
    return {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "model": "L0_docling_machine_pred",
        "gold": str(gold_path),
        "summary": summarize_reports(reports),
        "details": details,
        "shadow_only": True,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Rescore saved formula preds with v2 evaluator")
    p.add_argument("inputs", nargs="*", help="results JSON with details[].pred/gold")
    p.add_argument("--gold-l0", default="", help="verified jsonl → score machine_pred as L0")
    p.add_argument("--in-place", action="store_true")
    args = p.parse_args(argv)

    if args.gold_l0:
        gold_path = Path(args.gold_l0)
        payload = rescore_gold_machine_pred(gold_path)
        dest = K5_RESULTS_DIR / "l0_o018_machine_pred.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(dest)
        print(json.dumps(payload["summary"], ensure_ascii=False))

    for raw in args.inputs:
        path = Path(raw)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if "details" not in payload:
            print(f"skip (no details): {path}", file=sys.stderr)
            continue
        updated = rescore_payload(payload)
        dest = path if args.in_place else path.with_name(path.stem + "_rescored.json")
        dest.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
        print(dest)
        print(json.dumps(updated.get("summary"), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
