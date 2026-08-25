# -*- coding: utf-8 -*-
"""真实 DeepSeek-OCR 2 benchmark；权重缓存在 PDF2MD_HF_HOME 或 .cache/hf。"""
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

from app.ocr.deepseek_benchmark import (  # noqa: E402
    DeepSeekBenchmarkConfig,
    build_o018_cases,
    run_deepseek_benchmark,
)
from app.utils.paths import BENCHMARK_RUNS  # noqa: E402


def main() -> int:
    bench = Path(os.environ.get("PDF2MD_BENCH_ROOT") or (ROOT / "input"))
    pdfs = list(bench.rglob("O-018_Abdo2025_Stacking_SHAP.pdf"))
    if not pdfs:
        print("PDF not found", flush=True)
        return 2
    pdf = pdfs[0]
    print("pdf", pdf, flush=True)
    print("HF_HOME", os.environ["HF_HOME"], flush=True)
    print("python", sys.executable, flush=True)
    try:
        import transformers

        print("transformers", transformers.__version__, flush=True)
    except Exception as e:
        print("transformers?", e, flush=True)

    import torch

    print("cuda", torch.cuda.is_available(), flush=True)
    if torch.cuda.is_available():
        print("gpu", torch.cuda.get_device_name(0), flush=True)
        print(
            "vram_gb",
            round(torch.cuda.get_device_properties(0).total_memory / 1e9, 1),
            flush=True,
        )

    cfg = DeepSeekBenchmarkConfig(
        experiment_only=True,
        model_name=resolve_deepseek_model_name(),
        baseline_recognizer="unimernet",  # 当前生产主识别器作对照
        run_baseline=True,
        run_deepseek_formula=True,
        run_deepseek_region=True,
        run_deepseek_page=True,
        allow_cpu=False,
        device="cuda:0",
        # 4060 8GB：略收紧，降低 OOM 风险
        base_size=1024,
        image_size=640,
        crop_mode=True,
        page_render_scale=1.35,
        region_render_scale=1.5,
        formula_render_scale=2.0,
    )
    out = BENCHMARK_RUNS / "O018_deepseek_ocr2_real.json"
    try:
        payload = run_deepseek_benchmark(
            pdf,
            cfg=cfg,
            cases=build_o018_cases(pdf),
            progress=lambda m: print(m, flush=True),
            out_path=out,
        )
    except Exception:
        traceback.print_exc()
        return 1

    print("WROTE", payload.get("output_path"), flush=True)
    print(json.dumps(payload.get("summary"), ensure_ascii=False, indent=2), flush=True)
    print("total_seconds", payload.get("total_seconds"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
