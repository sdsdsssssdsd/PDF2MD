# -*- coding: utf-8 -*-
"""Phase 3C：两页真实 GPU 验证（不接 Scheduler）。"""
from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

HF_ROOT = Path(r"E:\Ollama\hf-cache")
HF_ROOT.mkdir(parents=True, exist_ok=True)
os.environ["HF_HOME"] = str(HF_ROOT)
os.environ["HUGGINGFACE_HUB_CACHE"] = str(HF_ROOT / "hub")
os.environ["TRANSFORMERS_CACHE"] = str(HF_ROOT / "transformers")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ocr.deepseek_paths import resolve_deepseek_model_name

from app.ocr.deepseek_benchmark import DeepSeekBenchmarkConfig  # noqa: E402
from app.ocr.phase3c_two_page import run_phase3c_two_page  # noqa: E402
from app.utils.paths import BENCHMARK_RUNS  # noqa: E402


def main() -> int:
    pdfs = list(
        Path(os.environ.get("PDF2MD_BENCH_ROOT") or (ROOT / "input")).rglob(
            "O-018_Abdo2025_Stacking_SHAP.pdf"
        )
    )
    if not pdfs:
        print("PDF not found", flush=True)
        return 2
    pdf = pdfs[0]
    print("pdf", pdf, flush=True)
    print("python", sys.executable, flush=True)

    import torch

    print("cuda", torch.cuda.is_available(), flush=True)
    if torch.cuda.is_available():
        print("gpu", torch.cuda.get_device_name(0), flush=True)

    cfg = DeepSeekBenchmarkConfig(
        experiment_only=True,
        model_name=resolve_deepseek_model_name(),
        allow_cpu=False,
        device="cuda:0",
        # 与 Phase1 真实跑一致，不改参数
        base_size=1024,
        image_size=640,
        crop_mode=True,
        page_render_scale=1.35,
        formula_render_scale=2.0,
        run_baseline=False,
        run_deepseek_formula=True,
        run_deepseek_region=False,
        run_deepseek_page=False,
    )
    out = BENCHMARK_RUNS / "phase3c_two_page_gpu.json"
    try:
        payload = run_phase3c_two_page(
            pdf,
            cfg=cfg,
            progress=lambda m: print(m, flush=True),
            out_path=out,
            safety_factor=1.2,
        )
    except Exception:
        traceback.print_exc()
        return 1

    print("WROTE", payload.get("output_path"), flush=True)
    print(
        json.dumps(
            {
                "single_acceptance": (payload.get("single_formula") or {}).get("acceptance"),
                "comparison": payload.get("comparison"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
