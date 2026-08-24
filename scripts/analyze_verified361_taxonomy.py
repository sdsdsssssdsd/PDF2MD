#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""361 verified Gold：失败层 + 四路 Recognition + PP-M/VL shadow（只读）。"""
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
from app.ocr.k5_taxonomy import (  # noqa: E402
    layer_or_ok,
    simulate_shadow_writeback,
    summarize_shadow,
)
from app.ocr.match_eval_v2 import FormulaMatchEvaluatorV2  # noqa: E402
from app.utils.paths import K5_GOLD_DIR, K5_RESULTS_DIR, ensure_dirs  # noqa: E402

BACKENDS = (
    ("L2", "deepseek_l2_verified_all.json"),
    ("PP-M", "pp_m_verified_all_tight.json"),
    ("PP-L", "pp_l_verified_all_tight.json"),
    ("PaddleVL", "paddlevl_verified_all_tight.json"),
)


def _preds(fname: str) -> dict[str, str]:
    p = K5_RESULTS_DIR / fname
    if not p.is_file():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    return {str(d["id"]): str(d.get("pred") or "") for d in data.get("details") or []}


def main() -> int:
    ensure_dirs()
    ev = FormulaMatchEvaluatorV2(compute_cdm=False)
    preds = {k: _preds(f) for k, f in BACKENDS}
    layers: dict[str, Counter] = {k: Counter() for k, _ in BACKENDS}
    exact_hits = {k: 0 for k, _ in BACKENDS}
    shadows = []
    false_accept_samples: list[dict] = []
    n = 0
    for line in (K5_GOLD_DIR / "verified_all.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        rid = str(row.get("id") or "")
        gold = str(row.get("gold_latex_raw") or "")
        if not gold.strip():
            continue
        n += 1
        for bk, _ in BACKENDS:
            pred = preds.get(bk, {}).get(rid, "")
            rep = ev.compare(pred, gold)
            if rep.strict_canonical_exact:
                exact_hits[bk] += 1
            layers[bk][layer_or_ok(exact=rep.strict_canonical_exact, pred=pred, gold=gold)] += 1
        pp = preds.get("PP-M", {}).get(rid, "")
        vl = preds.get("PaddleVL", {}).get(rid, "")
        sh = simulate_shadow_writeback(
            pp,
            vl,
            gold,
            page=int(row.get("page") or 1),
            bbox=list(row.get("bbox_pdf_tight") or row.get("bbox_pdf") or []),
        )
        shadows.append(sh)
        if sh.outcome == "false_accept":
            false_accept_samples.append(
                {
                    "id": rid,
                    "language": row.get("language"),
                    "equation_number": row.get("equation_number"),
                    "consensus": dual_model_consensus(pp, vl).decision,
                    "pred_pp": pp[:160],
                    "pred_vl": vl[:160],
                    "gold": gold[:160],
                }
            )
    shadow_sum = summarize_shadow(shadows)
    by_lang = {"en": Counter(), "zh": Counter()}
    for line in (K5_GOLD_DIR / "verified_all.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        lang = str(row.get("language") or "en")
        rid = str(row.get("id") or "")
        gold = str(row.get("gold_latex_raw") or "")
        if not gold.strip():
            continue
        pp = preds.get("PP-M", {}).get(rid, "")
        exact = ev.compare(pp, gold).strict_canonical_exact
        by_lang[lang]["n"] += 1
        if exact:
            by_lang[lang]["pp_m_exact"] += 1
    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "n_gold": n,
        "shadow_only": True,
        "production_unchanged": True,
        "exact_rate": {k: round(exact_hits[k] / n, 4) if n else None for k in exact_hits},
        "failure_layers": {k: dict(v) for k, v in layers.items()},
        "shadow_pp_m_vl": shadow_sum,
        "false_accept_n": len(false_accept_samples),
        "false_accept_samples_head20": false_accept_samples[:20],
        "pp_m_by_language": {
            lang: {
                "n": c["n"],
                "exact": c.get("pp_m_exact", 0),
                "exact_rate": round(c.get("pp_m_exact", 0) / c["n"], 4) if c["n"] else None,
            }
            for lang, c in by_lang.items()
        },
    }
    out = K5_RESULTS_DIR / "verified361_k5_taxonomy.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out)
    print(
        json.dumps(
            {
                "exact_rate": payload["exact_rate"],
                "shadow": shadow_sum,
                "false_accept_n": len(false_accept_samples),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
