# -*- coding: utf-8 -*-
"""Phase 5A：Canary 评估种子（冻结识别链路，只做统计）。"""
from __future__ import annotations

import os

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.formula.canary import (  # noqa: E402
    discover_pdfs,
    run_phase5a_canary_seed,
    write_canary_manifest,
)


def main() -> int:
    # 可选：登记本机论文目录（不自动跑 GPU）
    roots = [
        Path(os.environ.get("PDF2MD_BENCH_ROOT") or (ROOT / "input")),
    ]
    pdfs = discover_pdfs(roots, limit=50)
    if pdfs:
        man = write_canary_manifest(pdfs)
        print("manifest", man, "n=", len(pdfs), flush=True)

    payload = run_phase5a_canary_seed()
    print("WROTE", payload.get("output_path"), flush=True)
    print(json.dumps(payload.get("summary"), ensure_ascii=False, indent=2), flush=True)
    print(json.dumps(payload.get("gates"), ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
