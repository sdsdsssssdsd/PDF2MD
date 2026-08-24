#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""三模型投票 Gate 仿真（PP-M / PP-L / PaddleVL，只用已有 pred）。"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.formula.consensus import canonicalize_latex, dual_model_consensus  # noqa: E402
from app.ocr.match_eval_v2 import FormulaMatchEvaluatorV2, compile_rate_ok  # noqa: E402
from app.utils.paths import K5_GOLD_DIR, K5_RESULTS_DIR, ensure_dirs  # noqa: E402

BACKENDS = (
    ("PP-M", "pp_m_verified_all_tight.json"),
    ("PP-L", "pp_l_verified_all_tight.json"),
    ("PaddleVL", "paddlevl_verified_all_tight.json"),
)


def _load(fname: str) -> dict[str, str]:
    data = json.loads((K5_RESULTS_DIR / fname).read_text(encoding="utf-8"))
    return {str(d["id"]): str(d.get("pred") or "") for d in data.get("details") or []}


def _pair_agree(a: str, b: str) -> bool:
    if not a.strip() or not b.strip():
        return False
    c = dual_model_consensus(a, b)
    return c.decision in {"ACCEPT", "ACCEPT_VISUAL"}


def _majority_vote(preds: list[str]) -> tuple[bool, str]:
    """2-of-3 canonical pairwise agreement."""
    good = [p for p in preds if p.strip() and compile_rate_ok(p)]
    if len(good) < 2:
        return False, "INCOMPLETE"
    pairs = [(good[0], good[1]), (good[0], good[2]), (good[1], good[2])] if len(good) == 3 else [(good[0], good[1])]
    agree = sum(1 for a, b in pairs if _pair_agree(a, b))
    if len(good) == 3 and agree >= 2:
        return True, "MAJORITY_2OF3"
    if len(good) == 2 and agree >= 1:
        return True, "PAIR_AGREE"
    return False, "DISAGREE"


def _eval_rule(
    rows: list[dict],
    preds: dict[str, dict[str, str]],
    *,
    rule: str,
    write_pred: str,
) -> dict:
    ev = FormulaMatchEvaluatorV2(compute_cdm=False)
    true_a = false_a = abstain = 0
    for row in rows:
        rid = str(row.get("id") or "")
        gold = str(row.get("gold_latex_raw") or "")
        pm, pl, vl = preds["PP-M"].get(rid, ""), preds["PP-L"].get(rid, ""), preds["PaddleVL"].get(rid, "")
        accept = False
        if rule == "dual_pp_m_vl":
            accept = _pair_agree(pm, vl) and compile_rate_ok(pm)
            pred = pm
        elif rule == "dual_pp_l_vl":
            accept = _pair_agree(pl, vl) and compile_rate_ok(pl)
            pred = pl
        elif rule == "majority_2of3":
            accept, _ = _majority_vote([pm, pl, vl])
            pred = {"PP-M": pm, "PP-L": pl, "PaddleVL": vl}.get(write_pred, pm)
        elif rule == "triple_canonical":
            ca, cb, cc = canonicalize_latex(pm), canonicalize_latex(pl), canonicalize_latex(vl)
            vals = [v for v in (ca, cb, cc) if v]
            if len(vals) >= 2:
                top = Counter(vals).most_common(1)[0]
                accept = top[1] >= 2 and compile_rate_ok(pm)
                pred = pm
            else:
                accept = False
                pred = pm
        else:
            pred = pm
            accept = False
        if not accept:
            abstain += 1
            continue
        exact = ev.compare(pred, gold).strict_canonical_exact
        if exact:
            true_a += 1
        else:
            false_a += 1
    n = len(rows)
    acc = true_a + false_a
    return {
        "rule": rule,
        "write_pred": write_pred,
        "n_gold": n,
        "auto_accept": acc,
        "true_accept": true_a,
        "false_accept": false_a,
        "abstain": abstain,
        "precision": round(true_a / acc, 4) if acc else None,
        "coverage": round(true_a / n, 4) if n else None,
        "gate_pass": (true_a / acc >= 0.99 if acc else False) and false_a <= max(1, int(n * 0.01)),
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
    preds = {name: _load(fname) for name, fname in BACKENDS}
    rules = [
        ("dual_pp_m_vl", "PP-M"),
        ("dual_pp_l_vl", "PP-L"),
        ("majority_2of3", "PP-M"),
        ("triple_canonical", "PP-M"),
    ]
    results = [_eval_rule(rows, preds, rule=r, write_pred=w) for r, w in rules]
    results.sort(key=lambda x: (-(x.get("precision") or 0), -(x.get("coverage") or 0)))
    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "n_gold": len(rows),
        "shadow_only": True,
        "results": results,
        "best": results[0] if results else None,
        "any_gate_pass": any(r.get("gate_pass") for r in results),
    }
    out = K5_RESULTS_DIR / "gate_triple_model_simulation.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out)
    print(json.dumps({"best": payload["best"], "any_gate_pass": payload["any_gate_pass"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
