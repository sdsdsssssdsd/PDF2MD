#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全量 verified Gold：PP-M + PaddleVL 双模型影子写回 Gate 校准（不写生产 Markdown）。"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.formula.consensus import dual_model_consensus  # noqa: E402
from app.ocr.k5_taxonomy import simulate_shadow_writeback, summarize_shadow  # noqa: E402
from app.utils.paths import K5_GOLD_DIR, K5_RESULTS_DIR, ensure_dirs  # noqa: E402

PP_FILE = "pp_m_verified_all_tight.json"
VL_FILE = "paddlevl_verified_all_tight.json"


def _load_preds(name: str) -> dict[str, str]:
    path = K5_RESULTS_DIR / name
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {str(d["id"]): str(d.get("pred") or "") for d in data.get("details") or []}


def main() -> int:
    ensure_dirs()
    pp = _load_preds(PP_FILE)
    vl = _load_preds(VL_FILE)
    if not pp:
        print(f"missing {PP_FILE}; run PP-M benchmark first", file=sys.stderr)
        return 2
    gold_path = K5_GOLD_DIR / "verified_all.jsonl"
    shadows = []
    details = []
    for line in gold_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        rid = str(row.get("id") or "")
        gold = str(row.get("gold_latex_raw") or "")
        if not gold.strip():
            continue
        pred_pp = pp.get(rid, "")
        pred_vl = vl.get(rid, "") if vl else ""
        peer = pred_vl if pred_vl.strip() else pred_pp  # 无 VL 时退化为自检（coverage↓）
        sh = simulate_shadow_writeback(
            pred_pp,
            peer,
            gold,
            page=int(row.get("page") or 1),
            bbox=list(row.get("bbox_pdf_tight") or row.get("bbox_pdf") or []),
        )
        shadows.append(sh)
        cons = dual_model_consensus(pred_pp, peer)
        details.append(
            {
                "id": rid,
                "language": row.get("language"),
                "consensus": cons.to_dict(),
                "shadow": sh.to_dict(),
            }
        )
    summary = summarize_shadow(shadows)
    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "gold": str(gold_path),
        "primary": PP_FILE,
        "peer": VL_FILE if vl else "(pp_only_fallback)",
        "shadow_only": True,
        "production_unchanged": True,
        "summary": summary,
        "release_gate_target": {"auto_writeback_precision": 0.99, "false_accept_max": 0.01},
        "gate_pass": (
            summary.get("precision") is not None
            and summary["precision"] >= 0.99
            and (summary.get("false_accept") or 0) <= max(1, int(summary.get("n_gold", 0) * 0.01))
        ),
        "details": details,
        "do_not_train": True,
    }
    out = K5_RESULTS_DIR / "shadow_gate_calibration_verified_all.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out)
    print(json.dumps({"summary": summary, "gate_pass": payload["gate_pass"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
