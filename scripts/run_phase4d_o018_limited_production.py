# -*- coding: utf-8 -*-
"""Phase 4D：O-018 有限生产写回（默认用 4B.1 shadow 产物，无需 GPU）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.formula.phase4d_limited_production import (  # noqa: E402
    run_o018_limited_production_from_shadow,
)


def main() -> int:
    try:
        payload = run_o018_limited_production_from_shadow()
    except Exception as e:
        print("FAIL", e, flush=True)
        return 1
    print("WROTE", payload.get("output_path"), flush=True)
    print("MD", payload.get("markdown_path"), flush=True)
    print(json.dumps(payload.get("acceptance"), ensure_ascii=False, indent=2), flush=True)
    return 0 if (payload.get("acceptance") or {}).get("passed") else 3


if __name__ == "__main__":
    raise SystemExit(main())
