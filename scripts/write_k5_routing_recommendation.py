#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""k5 路由策略建议（只读评测结果，不写生产）。"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.utils.paths import K5_RESULTS_DIR, ensure_dirs  # noqa: E402

OUT = K5_RESULTS_DIR / "k5_routing_recommendation.json"


def _load(name: str) -> dict:
    p = K5_RESULTS_DIR / name
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def main() -> int:
    ensure_dirs()
    compare = _load("k5_full_recognition_compare.json")
    hard = _load("hard200_recognition_compare.json")
    gate = _load("shadow_gate_calibration_verified_all.json")
    curve = _load("gate_coverage_precision_curve.json")
    backends = compare.get("backends") or {}
    exact = {
        k: (v.get("summary") or {}).get("strict_canonical_exact")
        for k, v in backends.items()
        if isinstance(v, dict) and not v.get("missing")
    }
    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "shadow_only": True,
        "production_unchanged": True,
        "verified361_exact": exact,
        "proposed_routing": {
            "easy_path": "PP-FormulaNet_plus-M",
            "hard_path": "PaddleOCR-VL-1.6",
            "quality_audit": "PP-FormulaNet_plus-L (shadow/benchmark only until gate passes)",
            "consensus": "dual_model PP-M + PaddleVL; abstain if DISAGREE",
            "legacy_baseline": "DeepSeek-OCR-2 (L2) — keep for A/B, do not train",
        },
        "hard200_vs_l2": hard.get("beats_l2_on_exact"),
        "gate_status": {
            "precision": (gate.get("summary") or {}).get("precision"),
            "coverage": (gate.get("summary") or {}).get("coverage"),
            "gate_pass": gate.get("gate_pass"),
            "curve_passing_n": curve.get("passing_n"),
        },
        "next_steps": [
            "不新开长 GPU benchmark；Academic100 VL 批跑完即止",
            "Gate：改规则/路由或接受更低 coverage，目标 precision≥99%",
            "Production bbox benchmark（k5 第 10 步）",
            "有限 writeback 试点前必须 Academic40 holdout",
        ],
        "do_not": [
            "未过 Gate 前切生产 DeepSeek",
            "用 machine_pred 当 Gold",
            "训练/伪标签",
        ],
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(OUT)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
