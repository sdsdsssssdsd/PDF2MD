#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在 verified Gold 上扫描共识/CDM 阈值，找 precision≥99% 的 Gate 工作点。"""
from __future__ import annotations

import json
import sys
from dataclasses import replace
from datetime import datetime
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.formula.consensus import ConsensusResult, dual_model_consensus  # noqa: E402
from app.formula.risk import assess_formula_risk  # noqa: E402
from app.ocr.k5_taxonomy import ShadowWriteback, summarize_shadow  # noqa: E402
from app.ocr.match_eval_v2 import FormulaMatchEvaluatorV2  # noqa: E402
from app.utils.paths import K5_GOLD_DIR, K5_RESULTS_DIR, ensure_dirs  # noqa: E402

PAIRINGS = (
    ("PP-M", "PaddleVL", "pp_m_verified_all_tight.json", "paddlevl_verified_all_tight.json"),
    ("PP-L", "PaddleVL", "pp_l_verified_all_tight.json", "paddlevl_verified_all_tight.json"),
    ("PP-M", "PP-L", "pp_m_verified_all_tight.json", "pp_l_verified_all_tight.json"),
)


def _load_preds(fname: str) -> dict[str, str]:
    data = json.loads((K5_RESULTS_DIR / fname).read_text(encoding="utf-8"))
    return {str(d["id"]): str(d.get("pred") or "") for d in data.get("details") or []}


def _shadow_one(
    row: dict,
    pred_a: str,
    pred_b: str,
    *,
    cdm_threshold: float,
    canonical_only: bool,
) -> ShadowWriteback:
    gold = str(row.get("gold_latex_raw") or "")
    cons = dual_model_consensus(pred_a, pred_b, visual_cdm_threshold=cdm_threshold)
    if canonical_only and cons.decision == "ACCEPT_VISUAL":
        cons = replace(cons, decision="DISAGREE", reason="canonical_only_gate")
    box = list(row.get("bbox_pdf_tight") or row.get("bbox_pdf") or [10.0, 10.0, 80.0, 40.0])
    risk = assess_formula_risk(
        latex=pred_a,
        page=int(row.get("page") or 1),
        bbox=box,
        consensus=cons,
        require_consensus=True,
    )
    exact: bool | None = None
    if gold.strip() and (pred_a or "").strip():
        exact = FormulaMatchEvaluatorV2(compute_cdm=False).compare(pred_a, gold).strict_canonical_exact
    elif gold.strip():
        exact = False
    if risk.decision == "accept":
        if exact is None:
            outcome = "no_gold"
        elif exact:
            outcome = "true_accept"
        else:
            outcome = "false_accept"
    else:
        if exact is None:
            outcome = "no_gold"
        elif exact:
            outcome = "abstain_miss"
        else:
            outcome = "abstain_correct"
    return ShadowWriteback(
        decision=risk.decision,
        consensus=cons.decision,
        gold_exact=exact,
        outcome=outcome,
        reasons=list(risk.reasons),
    )


def _eval_combo(
    *,
    primary: dict[str, str],
    peer: dict[str, str],
    cdm_threshold: float,
    canonical_only: bool,
    label: str,
) -> dict:
    shadows: list[ShadowWriteback] = []
    for line in (K5_GOLD_DIR / "verified_all.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        rid = str(row.get("id") or "")
        gold = str(row.get("gold_latex_raw") or "")
        if not gold.strip():
            continue
        shadows.append(
            _shadow_one(
                row,
                primary.get(rid, ""),
                peer.get(rid, ""),
                cdm_threshold=cdm_threshold,
                canonical_only=canonical_only,
            )
        )
    summary = summarize_shadow(shadows)
    return {
        "label": label,
        "cdm_threshold": cdm_threshold,
        "canonical_only": canonical_only,
        **summary,
        "gate_pass": (
            summary.get("precision") is not None
            and summary["precision"] >= 0.99
            and (summary.get("false_accept") or 0) <= max(1, int(summary.get("n_gold", 0) * 0.01))
        ),
    }


def main() -> int:
    ensure_dirs()
    rows: list[dict] = []
    for pname, peer_name, pf, vf in PAIRINGS:
        primary = _load_preds(pf)
        peer = _load_preds(vf)
        if not primary or not peer:
            continue
        for cdm, canon in product((1.0, 0.99, 0.98, 0.95), (False, True)):
            label = f"{pname}+{peer_name}|cdm={cdm}|canonical_only={canon}"
            rows.append(
                _eval_combo(
                    primary=primary,
                    peer=peer,
                    cdm_threshold=cdm,
                    canonical_only=canon,
                    label=label,
                )
            )
    rows.sort(key=lambda r: (-(r.get("precision") or 0), -(r.get("coverage") or 0)))
    passing = [r for r in rows if r.get("gate_pass")]
    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "n_gold": 361,
        "shadow_only": True,
        "production_unchanged": True,
        "passing_configs": passing,
        "top10": rows[:10],
        "all_configs": rows,
        "note": "sweep on verified_all; does not change production gate",
    }
    out = K5_RESULTS_DIR / "gate_threshold_sweep_verified361.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out)
    print(json.dumps({"passing_n": len(passing), "top3": rows[:3]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
