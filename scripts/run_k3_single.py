# -*- coding: utf-8 -*-
"""单篇验证（t0 调优用）。

用法:
  python scripts/run_k3_single.py O-003
  python scripts/run_k3_single.py O-003 --reuse-raw
  python scripts/run_k3_single.py O-003 --raw path/to/stem.raw.md
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.utils.paths import BENCHMARK_RUNS, ensure_dirs
from scripts.run_k3_geometry_batch import CORPUS, run_one


def main() -> int:
    ap = argparse.ArgumentParser(description="k3 单篇验证")
    ap.add_argument("stem", nargs="?", default="O-003")
    ap.add_argument(
        "--reuse-raw",
        action="store_true",
        help="复用已有 raw.md，不重跑 Docling",
    )
    ap.add_argument("--raw", type=Path, default=None, help="指定 raw.md 路径")
    args = ap.parse_args()
    matches = [Path(p) for p in CORPUS if args.stem in Path(p).stem]
    if not matches:
        print(f"no pdf matching {args.stem!r}", file=sys.stderr)
        return 1
    pdf = matches[0]
    ensure_dirs()
    out = BENCHMARK_RUNS / f"k3_verify_{pdf.stem}_{time.strftime('%H%M%S')}"
    out.mkdir(parents=True, exist_ok=True)
    row = run_one(
        pdf,
        geometry_only=False,
        out_dir=out,
        reuse_raw=args.reuse_raw,
        raw_path=args.raw,
    )
    print(json.dumps(row, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
