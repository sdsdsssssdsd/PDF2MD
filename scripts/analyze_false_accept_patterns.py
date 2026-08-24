#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""39 条 false_accept 模式分析（只读 shadow_gate 详情）。"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.formula.consensus import dual_model_consensus  # noqa: E402
from app.ocr.match_eval_v2 import FormulaMatchEvaluatorV2  # noqa: E402
from app.utils.paths import K5_GOLD_DIR, K5_RESULTS_DIR, ensure_dirs  # noqa: E402


def main() -> int:
    ensure_dirs()
    gate_path = K5_RESULTS_DIR / "shadow_gate_calibration_verified_all.json"
    if not gate_path.is_file():
        print("run run_shadow_gate_calibration.py first", file=sys.stderr)
        return 2
    data = json.loads(gate_path.read_text(encoding="utf-8"))
    pp = {
        str(d["id"]): str(d.get("pred") or "")
        for d in json.loads((K5_RESULTS_DIR / "pp_m_verified_all_tight.json").read_text(encoding="utf-8")).get("details") or []
    }
    vl = {
        str(d["id"]): str(d.get("pred") or "")
        for d in json.loads((K5_RESULTS_DIR / "paddlevl_verified_all_tight.json").read_text(encoding="utf-8")).get("details") or []
    }
    ev = FormulaMatchEvaluatorV2(compute_cdm=False)
    gold_by_id = {}
    for line in (K5_GOLD_DIR / "verified_all.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            gold_by_id[str(r["id"])] = r
    false_rows = []
    cons_counter: Counter = Counter()
    lang_counter: Counter = Counter()
    pp_exact_vl_wrong = 0
    vl_exact_pp_wrong = 0
    both_wrong = 0
    for d in data.get("details") or []:
        sh = d.get("shadow") or {}
        if sh.get("outcome") != "false_accept":
            continue
        rid = str(d.get("id") or "")
        row = gold_by_id.get(rid) or {}
        p, v = pp.get(rid, ""), vl.get(rid, "")
        cons = dual_model_consensus(p, v)
        cons_counter[cons.decision] += 1
        lang_counter[str(row.get("language") or "?")] += 1
        pe = ev.compare(p, row.get("gold_latex_raw") or "").strict_canonical_exact
        ve = ev.compare(v, row.get("gold_latex_raw") or "").strict_canonical_exact
        if pe and not ve:
            pp_exact_vl_wrong += 1
        elif ve and not pe:
            vl_exact_pp_wrong += 1
        else:
            both_wrong += 1
        false_rows.append(
            {
                "id": rid,
                "language": row.get("language"),
                "consensus": cons.decision,
                "consensus_reason": cons.reason,
                "pp_exact": pe,
                "vl_exact": ve,
                "equation_number": row.get("equation_number"),
            }
        )
    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "n_false_accept": len(false_rows),
        "consensus_at_false_accept": dict(cons_counter),
        "language": dict(lang_counter),
        "who_was_right": {
            "pp_exact_vl_wrong": pp_exact_vl_wrong,
            "vl_exact_pp_wrong": vl_exact_pp_wrong,
            "both_wrong_agreed_wrong": both_wrong,
        },
        "samples": false_rows[:25],
        "hint": (
            "39/39 false_accept：PP-M 与 PaddleVL 均错但 canonical 一致（ACCEPT）。"
            "共识会把「一致地错」当 accept；需额外校验（如 L2 仲裁、更严 canonical、或 abstain）。"
        ),
        "shadow_only": True,
    }
    out = K5_RESULTS_DIR / "false_accept_pattern_analysis.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out)
    print(json.dumps({k: payload[k] for k in ("n_false_accept", "consensus_at_false_accept", "who_was_right", "hint")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
