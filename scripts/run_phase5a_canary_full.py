# -*- coding: utf-8 -*-
"""Phase 5A：跑满 manifest canary（Limited Production，冻结识别参数）。"""
from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ocr.deepseek_paths import ensure_deepseek_hf_env, resolve_deepseek_model_name

ensure_deepseek_hf_env()
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from app.formula.canary_runner import run_canary_batch  # noqa: E402


def main() -> int:
    limit = None
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        limit = int(sys.argv[1])
    print("python", sys.executable, flush=True)
    try:
        import torch

        print("cuda", torch.cuda.is_available(), flush=True)
        if torch.cuda.is_available():
            print("gpu", torch.cuda.get_device_name(0), flush=True)
    except Exception as e:
        print("torch?", e, flush=True)

    try:
        payload = run_canary_batch(
            model_name=resolve_deepseek_model_name(),
            device="cuda:0",
            max_formulas_per_doc=8,
            progress=lambda m: print(m, flush=True),
            limit=limit,
        )
    except Exception:
        traceback.print_exc()
        return 1

    print("WROTE", payload.get("output_path"), flush=True)
    print("REVIEW", payload.get("human_review_path"), flush=True)
    print(json.dumps(payload.get("summary"), ensure_ascii=False, indent=2), flush=True)
    print(json.dumps(payload.get("gates"), ensure_ascii=False, indent=2), flush=True)
    print(
        json.dumps(payload.get("coverage_histogram"), ensure_ascii=False, indent=2),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
