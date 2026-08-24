#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""汇总 O-018 Recognition-only 各后端结果（只读已有 json）。"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.utils.paths import K5_RESULTS_DIR  # noqa: E402

SOURCES = (
    ("L0_docling", "l0_o018_machine_pred.json"),
    ("P1_PP-M_prod_crop", "pp_m_o018_v1.json"),
    ("P1_PP-M_tight", "pp_m_o018_tight_v1.json"),
    ("P2_PP-L_tight", "pp_l_o018_tight_v1.json"),
    ("L2_DeepSeek_640_doc", "deepseek_l2_o018_tight.json"),
    ("L3_DeepSeek_768_formula", "deepseek_l3_o018_tight.json"),
    ("P3_PaddleVL16_tight", "paddlevl16_o018_tight.json"),
)


def main() -> int:
    rows = {}
    per_eq: dict[str, dict] = {}
    for key, name in SOURCES:
        path = K5_RESULTS_DIR / name
        if not path.is_file():
            rows[key] = {"missing": True}
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        rows[key] = {
            "file": name,
            "summary": data.get("summary"),
            "model": data.get("model") or data.get("experiment_id"),
            "prefer_tight": data.get("prefer_tight"),
        }
        for d in data.get("details") or []:
            eq = str(d.get("equation_number") or d.get("id") or "")
            per_eq.setdefault(eq, {})[key] = {
                "exact": d.get("strict_canonical_exact"),
                "pred": (d.get("pred") or "")[:160],
                "error": d.get("error") or "",
            }
    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "shadow_only": True,
        "production_unchanged": True,
        "summaries": rows,
        "per_eq": per_eq,
    }
    out = K5_RESULTS_DIR / "o018_recognition_only_compare.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out)
    slim = {
        k: (v.get("summary") or v) for k, v in rows.items()
    }
    print(json.dumps(slim, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
