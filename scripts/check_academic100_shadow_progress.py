#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合并 Academic100 regression shadow 部分结果并打印进度。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PART_DIR = ROOT / "benchmarks" / "results" / "paddlevl_academic100_parts"
PP = ROOT / "benchmarks" / "results" / "pp_m_academic100_regression_tight.json"
VL = ROOT / "benchmarks" / "results" / "paddlevl_academic100_regression_tight.json"


def main() -> int:
    parts = sorted(PART_DIR.glob("part_*.json"))
    print({"vl_parts_done": len(parts), "expected": 21})
    if parts:
        n = sum(len(json.loads(p.read_text(encoding="utf-8")).get("details") or []) for p in parts)
        print({"vl_preds_so_far": n})
    if PP.is_file():
        pp = json.loads(PP.read_text(encoding="utf-8"))
        print({"pp_preds": len(pp.get("details") or [])})
    if VL.is_file():
        vl = json.loads(VL.read_text(encoding="utf-8"))
        print({"vl_merged": len(vl.get("details") or []), "summary": vl.get("summary")})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
