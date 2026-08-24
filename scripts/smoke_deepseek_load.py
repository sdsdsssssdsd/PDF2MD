# -*- coding: utf-8 -*-
"""只测 DeepSeek-OCR-2 能否在 GPU 上加载；权重下到 os.environ.get("PDF2MD_HF_HOME", ".cache/hf")。"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

HF_ROOT = Path(r"E:\Ollama\hf-cache")
HF_ROOT.mkdir(parents=True, exist_ok=True)
os.environ["HF_HOME"] = str(HF_ROOT)
os.environ["HUGGINGFACE_HUB_CACHE"] = str(HF_ROOT / "hub")
os.environ["TRANSFORMERS_CACHE"] = str(HF_ROOT / "transformers")
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["TRANSFORMERS_NO_TF"] = "1"
os.environ["USE_TF"] = "0"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ocr.deepseek_paths import resolve_deepseek_model_name

from PIL import Image  # noqa: E402

from app.ocr import OCRMode  # noqa: E402
from app.ocr.deepseek_ocr2 import DeepSeekOCR2Recognizer  # noqa: E402


def main() -> int:
    DeepSeekOCR2Recognizer.reset_class_model()
    local = resolve_deepseek_model_name()
    rec = DeepSeekOCR2Recognizer(
        model_name=local,
        device="cuda:0",
        allow_cpu=False,
        image_size=640,
        base_size=1024,
    )
    print("loading...", flush=True)
    t0 = time.perf_counter()
    rec._ensure_loaded()
    print(
        "loaded in",
        round(time.perf_counter() - t0, 1),
        "s device=",
        DeepSeekOCR2Recognizer._device,
        "load_s=",
        round(DeepSeekOCR2Recognizer._load_seconds, 1),
        flush=True,
    )
    img = Image.new("RGB", (512, 256), color=(255, 255, 255))
    # 写点黑字太麻烦；空白图只测 infer 通路
    from PIL import ImageDraw

    d = ImageDraw.Draw(img)
    d.text((20, 100), "Recall = TP / (TP + FN)  (4)", fill=(0, 0, 0))
    print("infer...", flush=True)
    out = rec.recognize(img, mode=OCRMode.FORMULA)
    print("success", out.success, "err", out.error, flush=True)
    print("device_meta", out.metadata.get("device"), flush=True)
    print("text", (out.text or "")[:300], flush=True)
    print("sec", round(out.elapsed_seconds, 2), flush=True)
    return 0 if out.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
