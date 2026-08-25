#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build formula crop cache from formula_qa + benchmark PDFs (k5 §28.5)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.formula.crop_cache import CROP_SCALE, build_crop_cache  # noqa: E402
from app.utils.paths import EXPERIMENT_DIR, K5_CROPS_DIR  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Build frozen formula crop cache")
    p.add_argument("--experiment-dir", default=str(EXPERIMENT_DIR))
    p.add_argument("--out-dir", default=str(K5_CROPS_DIR))
    p.add_argument("--scale", type=float, default=CROP_SCALE)
    p.add_argument("--limit", type=int, default=0)
    args = p.parse_args(argv)
    man = build_crop_cache(
        experiment_dir=Path(args.experiment_dir),
        out_dir=Path(args.out_dir),
        scale=float(args.scale),
        limit=int(args.limit),
    )
    print(json.dumps({k: man[k] for k in ("n", "ok", "failed", "scale")}, ensure_ascii=False))
    print(Path(args.out_dir) / "manifest.json")
    return 0 if man.get("ok", 0) or man.get("n", 0) == 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
