#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""汇总 verified Gold 上 L2 / PP-M / PP-L / PaddleVL Recognition-only 结果（只读 json）。"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.utils.paths import K5_GOLD_DIR, K5_RESULTS_DIR, ensure_dirs  # noqa: E402

SOURCES = (
    ("L2_DeepSeek", "deepseek_l2_verified_all.json", "deepseek_l2_verified"),
    ("P1_PP-M_tight", "pp_m_verified_all_tight.json", None),
    ("P2_PP-L_tight", "pp_l_verified_all_tight.json", None),
    ("P3_PaddleVL_tight", "paddlevl_verified_all_tight.json", None),
)


def _merge_l2() -> dict:
    by_id: dict[str, dict] = {}
    for f in sorted(K5_RESULTS_DIR.glob("deepseek_l2_verified*.json")):
        if f.name == "deepseek_l2_verified_all.json":
            continue
        data = json.loads(f.read_text(encoding="utf-8"))
        for d in data.get("details") or []:
            by_id[str(d["id"])] = d
    if not by_id:
        return {}
    details = list(by_id.values())
    from app.ocr.match_eval_v2 import MatchReportV2, summarize_reports

    reports = []
    for d in details:
        if d.get("strict_canonical_exact") is not None:
            reports.append(
                MatchReportV2(
                    strict_canonical_exact=bool(d.get("strict_canonical_exact")),
                    token_edit_distance=int(d.get("token_edit_distance") or 0),
                    token_edit_ratio=float(d.get("token_edit_ratio") or 0.0),
                    compile_ok=bool(d.get("compile_ok")),
                    reasons=list(d.get("reasons") or []),
                )
            )
    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "model": "DeepSeek-OCR-2",
        "experiment_id": "L2",
        "summary": summarize_reports(reports),
        "details": details,
        "shadow_only": True,
        "prefer_tight": True,
        "do_not_train": True,
    }
    out = K5_RESULTS_DIR / "deepseek_l2_verified_all.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"file": out.name, "summary": payload["summary"]}


def main() -> int:
    ensure_dirs()
    rows: dict[str, dict] = {}
    rows["L2_DeepSeek"] = _merge_l2()
    for key, fname, _ in SOURCES:
        path = K5_RESULTS_DIR / fname
        if not path.is_file():
            rows[key] = {"missing": True, "expected": fname}
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        rows[key] = {
            "file": fname,
            "model": data.get("model") or data.get("experiment_id"),
            "summary": data.get("summary"),
            "prefer_tight": data.get("prefer_tight"),
        }
    gold_n = sum(
        1
        for line in (K5_GOLD_DIR / "verified_all.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "gold": "benchmarks/gold/verified_all.jsonl",
        "n_gold": gold_n,
        "shadow_only": True,
        "production_unchanged": True,
        "backends": rows,
    }
    out = K5_RESULTS_DIR / "k5_full_recognition_compare.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out)
    slim = {k: (v.get("summary") if isinstance(v, dict) else v) for k, v in rows.items()}
    print(json.dumps(slim, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
