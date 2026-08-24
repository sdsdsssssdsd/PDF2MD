#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""写出 k5 当前进度快照到 benchmarks/results/k5_progress_snapshot.json"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.utils.paths import K5_GOLD_DIR, K5_MANIFESTS_DIR, K5_RESULTS_DIR  # noqa: E402


def _sum(path: Path) -> dict | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8")).get("summary") or {}


def main() -> int:
    v = sum(1 for l in (K5_GOLD_DIR / "verified_all.jsonl").read_text(encoding="utf-8").splitlines() if l.strip())
    l2 = set()
    for f in K5_RESULTS_DIR.glob("deepseek_l2_verified*.json"):
        for d in json.loads(f.read_text(encoding="utf-8")).get("details") or []:
            l2.add(d["id"])
    snap = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "verified_gold": v,
        "target_gold": "800-1200",
        "l2_scored": len(l2),
        "l2_gap": v - len(l2),
        "backends": {
            "L2": _sum(K5_RESULTS_DIR / "deepseek_l2_verified_all.json"),
            "PP-M": _sum(K5_RESULTS_DIR / "pp_m_verified_all_tight.json"),
            "PP-L": _sum(K5_RESULTS_DIR / "pp_l_verified_all_tight.json"),
            "PaddleVL": _sum(K5_RESULTS_DIR / "paddlevl_verified_all_tight.json"),
        },
        "shadow_gate": (
            json.loads((K5_RESULTS_DIR / "shadow_gate_calibration_verified_all.json").read_text(encoding="utf-8")).get("summary")
            if (K5_RESULTS_DIR / "shadow_gate_calibration_verified_all.json").is_file()
            else None
        ),
        "gate_sweep": str(K5_RESULTS_DIR / "gate_threshold_sweep_verified361.json")
        if (K5_RESULTS_DIR / "gate_threshold_sweep_verified361.json").is_file()
        else None,
        "gate_coverage_curve": str(K5_RESULTS_DIR / "gate_coverage_precision_curve.json")
        if (K5_RESULTS_DIR / "gate_coverage_precision_curve.json").is_file()
        else None,
        "hard200_compare": str(K5_RESULTS_DIR / "hard200_recognition_compare.json")
        if (K5_RESULTS_DIR / "hard200_recognition_compare.json").is_file()
        else None,
        "routing_recommendation": str(K5_RESULTS_DIR / "k5_routing_recommendation.json")
        if (K5_RESULTS_DIR / "k5_routing_recommendation.json").is_file()
        else None,
        "academic100_shadow": str(K5_RESULTS_DIR / "academic100_shadow_recognition_summary.json")
        if (K5_RESULTS_DIR / "academic100_shadow_recognition_summary.json").is_file()
        else None,
        "hard200": str(K5_MANIFESTS_DIR / "hard200_v1.jsonl"),
        "holdout": str(K5_MANIFESTS_DIR / "academic40_holdout_v1.json"),
        "pipeline_log": str(K5_RESULTS_DIR / "k5_pipeline_sequential.log"),
        "shadow_only": True,
        "production_unchanged": True,
    }
    out = K5_RESULTS_DIR / "k5_progress_snapshot.json"
    out.write_text(json.dumps(snap, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(snap, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
