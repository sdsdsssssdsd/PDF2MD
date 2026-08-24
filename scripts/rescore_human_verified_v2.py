#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用已有 PP-M 骨架预测给新核验的 3 条打分。不重跑模型。"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ocr.match_eval_v2 import FormulaMatchEvaluatorV2, summarize_reports  # noqa: E402
from app.utils.paths import K5_GOLD_DIR, K5_RESULTS_DIR  # noqa: E402


def main() -> int:
    gold_path = K5_GOLD_DIR / "human_verified_v2.jsonl"
    pred_path = K5_RESULTS_DIR / "pp_m_skeleton23_tight.json"
    golds = {}
    for line in gold_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            golds[row["id"]] = row
    preds = {
        d["id"]: d.get("pred") or ""
        for d in json.loads(pred_path.read_text(encoding="utf-8")).get("details") or []
    }
    ev = FormulaMatchEvaluatorV2(compute_cdm=False)
    reports = []
    details = []
    for gid, g in golds.items():
        pred = preds.get(gid, "")
        report = ev.compare(pred, g.get("gold_latex_raw") or "")
        reports.append(report)
        details.append(
            {
                "id": gid,
                "equation_number": g.get("equation_number"),
                "pred": pred,
                "gold": g.get("gold_latex_raw"),
                **report.to_dict(),
            }
        )
        print(gid, report.strict_canonical_exact, pred[:80])
    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "model": "PP-FormulaNet_plus-M",
        "gold": str(gold_path),
        "source_preds": pred_path.name,
        "summary": summarize_reports(reports),
        "details": details,
        "shadow_only": True,
        "do_not_train": True,
    }
    out = K5_RESULTS_DIR / "pp_m_human_verified_v2.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out)
    print(json.dumps(payload["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
