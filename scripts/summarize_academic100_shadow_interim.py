#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用已完成的 PaddleVL 分片 + PP-M 出 interim shadow 报告。"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.formula.consensus import dual_model_consensus  # noqa: E402
from app.ocr.k5_taxonomy import summarize_shadow, simulate_shadow_writeback  # noqa: E402
from app.utils.paths import K5_GOLD_DIR, K5_RESULTS_DIR  # noqa: E402

PART_DIR = K5_RESULTS_DIR / "paddlevl_academic100_parts"
PP_OUT = K5_RESULTS_DIR / "pp_m_academic100_regression_tight.json"
SUBSET = K5_GOLD_DIR / "harvest_display_regression.jsonl"
OUT = K5_RESULTS_DIR / "academic100_shadow_interim.json"


def main() -> int:
    parts = sorted(PART_DIR.glob("part_*.json"))
    vl: dict[str, str] = {}
    for p in parts:
        for d in json.loads(p.read_text(encoding="utf-8")).get("details") or []:
            vl[str(d["id"])] = str(d.get("pred") or "")
    pp: dict[str, str] = {}
    if PP_OUT.is_file():
        for d in json.loads(PP_OUT.read_text(encoding="utf-8")).get("details") or []:
            pp[str(d["id"])] = str(d.get("pred") or "")
    verified = {}
    for line in (K5_GOLD_DIR / "verified_all.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            verified[str(r["id"])] = str(r.get("gold_latex_raw") or "")
    rows = [json.loads(l) for l in SUBSET.read_text(encoding="utf-8").splitlines() if l.strip()]
    shadows_v = []
    consensus = {"ACCEPT": 0, "ACCEPT_VISUAL": 0, "DISAGREE": 0, "INCOMPLETE": 0}
    covered = 0
    for row in rows:
        rid = str(row.get("id") or "")
        if rid not in vl:
            continue
        covered += 1
        p, v = pp.get(rid, ""), vl.get(rid, "")
        cons = dual_model_consensus(p, v)
        consensus[cons.decision] = consensus.get(cons.decision, 0) + 1
        gold = verified.get(rid, "")
        if gold:
            shadows_v.append(
                simulate_shadow_writeback(
                    p, v or p, gold,
                    page=int(row.get("page") or 1),
                    bbox=list(row.get("bbox_pdf_tight") or row.get("bbox_pdf") or []),
                )
            )
    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "vl_parts_done": len(parts),
        "vl_preds": len(vl),
        "pp_preds": len(pp),
        "n_subset": len(rows),
        "n_both_models": sum(1 for r in rows if str(r["id"]) in pp and str(r["id"]) in vl),
        "consensus_on_covered": consensus,
        "shadow_verified_subset": summarize_shadow(shadows_v) if shadows_v else None,
        "partial": True,
        "shadow_only": True,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(OUT)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
