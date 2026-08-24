#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""O-018 Recognition-only → k5 失败层 + PP-M/VL 影子写回（不改生产）。"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.formula.consensus import dual_model_consensus  # noqa: E402
from app.formula.gold_schema import FormulaGoldRecord  # noqa: E402
from app.ocr.k5_taxonomy import (  # noqa: E402
    classify_crop_vs_ocr,
    layer_or_ok,
    simulate_shadow_writeback,
    summarize_shadow,
)
from app.utils.paths import K5_GOLD_DIR, K5_RESULTS_DIR  # noqa: E402

COMPARE = "o018_recognition_only_compare.json"
GOLD = "o018_verified.jsonl"
PRIMARY = "P1_PP-M_tight"
PEER = "P3_PaddleVL16_tight"
PROD = "P1_PP-M_prod_crop"


def _load_gold() -> dict[str, dict]:
    rows: dict[str, dict] = {}
    path = K5_GOLD_DIR / GOLD
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = FormulaGoldRecord.from_dict(json.loads(line))
        rows[str(rec.equation_number)] = rec.to_dict()
    return rows


def main() -> int:
    cmp_path = K5_RESULTS_DIR / COMPARE
    data = json.loads(cmp_path.read_text(encoding="utf-8"))
    golds = _load_gold()
    per_eq_in = data.get("per_eq") or {}
    per_eq = {}
    shadows = []
    crop_layers = {"prod": {}, "tight": {}}

    for eq, backends in per_eq_in.items():
        gold_row = golds.get(str(eq)) or {}
        gold = gold_row.get("gold_latex_raw") or ""
        prod = backends.get(PROD) or {}
        tight = backends.get(PRIMARY) or {}
        vl = backends.get(PEER) or {}
        prod_pred = str(prod.get("pred") or "")
        tight_pred = str(tight.get("pred") or "")
        vl_pred = str(vl.get("pred") or "")
        exact_prod = bool(prod.get("exact"))
        exact_tight = bool(tight.get("exact"))
        prod_layer, tight_layer = classify_crop_vs_ocr(
            exact_prod=exact_prod,
            exact_tight=exact_tight,
            prod_pred=prod_pred,
            tight_pred=tight_pred,
        )
        crop_layers["prod"][eq] = prod_layer
        crop_layers["tight"][eq] = tight_layer
        cons = dual_model_consensus(tight_pred, vl_pred)
        shadow = simulate_shadow_writeback(
            tight_pred,
            vl_pred,
            gold,
            page=int(gold_row.get("page") or 1),
            bbox=list(gold_row.get("bbox_pdf_tight") or gold_row.get("bbox_pdf") or []),
        )
        shadows.append(shadow)
        per_eq[eq] = {
            "gold": gold,
            "prod_pred": prod_pred[:200],
            "tight_pred": tight_pred[:200],
            "vl_pred": vl_pred[:200],
            "exact_prod": exact_prod,
            "exact_tight": exact_tight,
            "exact_vl": bool(vl.get("exact")),
            "prod_layer": prod_layer,
            "tight_layer": tight_layer,
            "vl_layer": layer_or_ok(exact=bool(vl.get("exact")), pred=vl_pred, gold=gold),
            "consensus_p1_p3": cons.to_dict(),
            "shadow_writeback": shadow.to_dict(),
            "crop_quality": gold_row.get("crop_quality") or [],
        }

    shadow_sum = summarize_shadow(shadows)
    prod_clipped = sum(1 for v in crop_layers["prod"].values() if v == "CROP_CLIPPED")
    tight_ok = sum(1 for v in crop_layers["tight"].values() if v == "OK")
    verdict = [
        f"PP-M 生产 crop 有 {prod_clipped}/5 判为 CROP_CLIPPED；紧 crop OK {tight_ok}/5。",
        "同一模型 0/5 → 4/5 是裁图，不是该训练 PP-FormulaNet。",
        (
            f"PP-M + VL 影子写回 precision={shadow_sum.get('precision')} "
            f"false_accept={shadow_sum.get('false_accept')} "
            f"coverage={shadow_sum.get('coverage')}。"
        ),
        "eq1 Gold 保持 Var/y canary；纸面是 V / mathcal Y。共识若因 hat/widehat 不一致会 abstain，有利于 precision。",
        "n=5 不能换生产，也不能选 L 换 M。",
    ]
    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "shadow_only": True,
        "production_unchanged": True,
        "do_not_train": True,
        "source_compare": COMPARE,
        "shadow_pp_m_vl": shadow_sum,
        "crop_vs_ocr": crop_layers,
        "per_eq": per_eq,
        "verdict": verdict,
    }
    out = K5_RESULTS_DIR / "o018_k5_taxonomy.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out)
    print(json.dumps({"shadow": shadow_sum, "verdict": verdict}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
