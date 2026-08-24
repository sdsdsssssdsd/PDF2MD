#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""361 verified Gold：coverage–precision 曲线（只用已有 pred，不跑 GPU）。"""
from __future__ import annotations

import json
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.formula.consensus import dual_model_consensus  # noqa: E402
from app.formula.risk import assess_formula_risk  # noqa: E402
from app.ocr.k5_taxonomy import ShadowWriteback, summarize_shadow  # noqa: E402
from app.ocr.match_eval_v2 import FormulaMatchEvaluatorV2, compile_rate_ok  # noqa: E402
from app.utils.paths import K5_GOLD_DIR, K5_RESULTS_DIR, ensure_dirs  # noqa: E402

PAIRINGS = (
    ("PP-M", "PaddleVL", "pp_m_verified_all_tight.json", "paddlevl_verified_all_tight.json"),
    ("PP-L", "PaddleVL", "pp_l_verified_all_tight.json", "paddlevl_verified_all_tight.json"),
)


def _load(fname: str) -> dict[str, str]:
    p = K5_RESULTS_DIR / fname
    data = json.loads(p.read_text(encoding="utf-8"))
    return {str(d["id"]): str(d.get("pred") or "") for d in data.get("details") or []}


def _eval(
    rows: list[dict],
    primary: dict[str, str],
    peer: dict[str, str],
    *,
    cdm_threshold: float,
    canonical_only: bool,
    require_both_compile: bool,
    label: str,
) -> dict:
    ev = FormulaMatchEvaluatorV2(compute_cdm=False)
    shadows: list[ShadowWriteback] = []
    for row in rows:
        rid = str(row.get("id") or "")
        gold = str(row.get("gold_latex_raw") or "")
        pred_a = primary.get(rid, "")
        pred_b = peer.get(rid, "")
        cons = dual_model_consensus(pred_a, pred_b, visual_cdm_threshold=cdm_threshold)
        if canonical_only and cons.decision == "ACCEPT_VISUAL":
            cons = replace(cons, decision="DISAGREE", reason="canonical_only")
        if require_both_compile and not (compile_rate_ok(pred_a) and compile_rate_ok(pred_b)):
            cons = replace(cons, decision="DISAGREE", reason="compile_gate")
        risk = assess_formula_risk(
            latex=pred_a,
            page=int(row.get("page") or 1),
            bbox=list(row.get("bbox_pdf_tight") or row.get("bbox_pdf") or []),
            consensus=cons,
            require_consensus=True,
        )
        exact: bool | None = None
        if gold.strip() and pred_a.strip():
            exact = ev.compare(pred_a, gold).strict_canonical_exact
        elif gold.strip():
            exact = False
        if risk.decision == "accept":
            outcome = "true_accept" if exact else "false_accept" if exact is not None else "no_gold"
        else:
            outcome = "abstain_miss" if exact else "abstain_correct" if exact is not None else "no_gold"
        shadows.append(
            ShadowWriteback(
                decision=risk.decision,
                consensus=cons.decision,
                gold_exact=exact,
                outcome=outcome,  # type: ignore[arg-type]
                reasons=list(risk.reasons),
            )
        )
    s = summarize_shadow(shadows)
    return {
        "label": label,
        "cdm_threshold": cdm_threshold,
        "canonical_only": canonical_only,
        "require_both_compile": require_both_compile,
        **s,
        "gate_pass": (
            s.get("precision") is not None
            and s["precision"] >= 0.99
            and (s.get("false_accept") or 0) <= max(1, int(s.get("n_gold", 0) * 0.01))
        ),
    }


def main() -> int:
    ensure_dirs()
    rows = []
    for line in (K5_GOLD_DIR / "verified_all.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if str(row.get("gold_latex_raw") or "").strip():
            rows.append(row)

    points: list[dict] = []
    for pname, peer_name, pf, vf in PAIRINGS:
        primary, peer = _load(pf), _load(vf)
        if not primary or not peer:
            continue
        for cdm in (1.0, 0.995, 0.99, 0.98, 0.95, 0.90):
            for canon in (False, True):
                for compile_gate in (False, True):
                    label = f"{pname}+{peer_name}|cdm={cdm}|canon={canon}|compile={compile_gate}"
                    points.append(
                        _eval(
                            rows,
                            primary,
                            peer,
                            cdm_threshold=cdm,
                            canonical_only=canon,
                            require_both_compile=compile_gate,
                            label=label,
                        )
                    )
    passing = [p for p in points if p.get("gate_pass")]
    # Pareto: sort by precision desc, then coverage desc
    points.sort(key=lambda p: (-(p.get("precision") or 0), -(p.get("coverage") or 0)))
    # coverage-precision frontier: for each precision bin, best coverage
    frontier = []
    best_cov = -1.0
    for p in sorted(points, key=lambda x: (-(x.get("precision") or 0), -(x.get("coverage") or 0))):
        prec = p.get("precision") or 0
        cov = p.get("coverage") or 0
        if prec >= 0.99 and p.get("gate_pass"):
            frontier.append(p)
    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "n_gold": len(rows),
        "shadow_only": True,
        "production_unchanged": True,
        "passing_configs": passing,
        "passing_n": len(passing),
        "best_precision": points[0] if points else None,
        "top10_by_precision": points[:10],
        "recommendation": (
            "无配置达 99%：下一版应改 Gate 规则或路由，而非继续堆 GPU benchmark。"
            if not passing
            else f"可选 {len(passing)} 个达标配置，取 coverage 最高者。"
        ),
        "all_points": points,
    }
    out = K5_RESULTS_DIR / "gate_coverage_precision_curve.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    slim = {
        "passing_n": len(passing),
        "best": points[0] if points else None,
        "recommendation": payload["recommendation"],
    }
    print(out)
    print(json.dumps(slim, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
