#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hard-200：四路 Recognition 对比（只读已有 json，不跑 GPU）。"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ocr.match_eval_v2 import FormulaMatchEvaluatorV2, summarize_reports  # noqa: E402
from app.utils.paths import K5_GOLD_DIR, K5_MANIFESTS_DIR, K5_RESULTS_DIR, ensure_dirs  # noqa: E402

BACKENDS = (
    ("L2", "deepseek_l2_verified_all.json"),
    ("PP-M", "pp_m_verified_all_tight.json"),
    ("PP-L", "pp_l_verified_all_tight.json"),
    ("PaddleVL", "paddlevl_verified_all_tight.json"),
)


def _preds(fname: str) -> dict[str, dict]:
    p = K5_RESULTS_DIR / fname
    if not p.is_file():
        return {}
    return {str(d["id"]): d for d in json.loads(p.read_text(encoding="utf-8")).get("details") or []}


def main() -> int:
    ensure_dirs()
    hard_path = K5_MANIFESTS_DIR / "hard200_v1.jsonl"
    if not hard_path.is_file():
        print("run build_hard200_manifest.py first", file=sys.stderr)
        return 2
    hard_ids = {json.loads(l)["id"] for l in hard_path.read_text(encoding="utf-8").splitlines() if l.strip()}
    gold_by_id: dict[str, str] = {}
    meta_by_id: dict[str, dict] = {}
    for line in (K5_GOLD_DIR / "verified_all.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        rid = str(row.get("id") or "")
        if rid in hard_ids:
            gold_by_id[rid] = str(row.get("gold_latex_raw") or "")
            meta_by_id[rid] = row
    backend_preds = {name: _preds(fname) for name, fname in BACKENDS}
    ev = FormulaMatchEvaluatorV2(compute_cdm=False)
    summaries: dict[str, dict] = {}
    by_lang: dict[str, dict[str, dict]] = {"en": {}, "zh": {}}
    for name in backend_preds:
        reports = []
        for rid in hard_ids:
            gold = gold_by_id.get(rid, "")
            if not gold:
                continue
            d = backend_preds[name].get(rid) or {}
            pred = str(d.get("pred") or "")
            rep = ev.compare(pred, gold)
            reports.append(rep)
        summaries[name] = summarize_reports(reports)
        for lang in ("en", "zh"):
            lr = []
            for rid in hard_ids:
                row = meta_by_id.get(rid) or {}
                if row.get("language") != lang:
                    continue
                gold = gold_by_id.get(rid, "")
                if not gold:
                    continue
                pred = str((backend_preds[name].get(rid) or {}).get("pred") or "")
                lr.append(ev.compare(pred, gold))
            by_lang[lang][name] = summarize_reports(lr)
    l2_exact = summaries.get("L2", {}).get("strict_canonical_exact")
    beats_l2 = {
        k: (
            summaries[k].get("strict_canonical_exact") is not None
            and l2_exact is not None
            and summaries[k]["strict_canonical_exact"] > l2_exact
        )
        for k in summaries
        if k != "L2"
    }
    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "manifest": str(hard_path),
        "n_hard200": len(hard_ids),
        "shadow_only": True,
        "production_unchanged": True,
        "summaries": summaries,
        "by_language": by_lang,
        "beats_l2_on_exact": beats_l2,
        "release_gate_hard200": "优于旧系统(L2)" if any(beats_l2.values()) else "未优于 L2 baseline",
    }
    out = K5_RESULTS_DIR / "hard200_recognition_compare.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out)
    print(json.dumps({"summaries": summaries, "beats_l2": beats_l2}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
