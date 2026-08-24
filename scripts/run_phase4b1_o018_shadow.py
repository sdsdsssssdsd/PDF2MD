# -*- coding: utf-8 -*-
"""Phase 4B.1：O-018 真实 GPU Shadow（不改 Markdown）。"""
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

from app.ocr.phase4b1_shadow_validation import run_o018_shadow_validation  # noqa: E402
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

    try:
        payload = run_o018_shadow_validation(
            pdf,
            model_name=resolve_deepseek_model_name(),
            device="cuda:0",
            progress=lambda m: print(m, flush=True),
            out_path=BENCHMARK_RUNS / "phase4b1_o018_shadow.json",
        )
    except Exception:
        traceback.print_exc()
        return 1

    print("WROTE", payload.get("output_path"), flush=True)
    print("QA", payload.get("qa_path"), flush=True)
    print(
        json.dumps(
            {
                "acceptance": payload.get("acceptance"),
                "timing": payload.get("timing"),
                "model_load_count": payload.get("model_load_count"),
                "mode_counts": (payload.get("deepseek_shadow") or {})
                .get("summary", {})
                .get("mode_counts"),
                "ema_before": payload.get("ema_before"),
                "ema_after": payload.get("ema_after"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )
    return 0 if (payload.get("acceptance") or {}).get("passed") else 3


if __name__ == "__main__":
    raise SystemExit(main())
