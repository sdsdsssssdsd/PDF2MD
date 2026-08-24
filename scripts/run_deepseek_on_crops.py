#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Recognition-only：DeepSeek-OCR-2 吃冻结 crop（L2/L3）。不写生产 Markdown。"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ocr.deepseek_paths import (  # noqa: E402
    DSOCR2_PYTHON,
    ensure_deepseek_hf_env,
    resolve_deepseek_model_name,
)

ensure_deepseek_hf_env()

try:
    import transformers

    _tf_ver = tuple(int(x) for x in transformers.__version__.split(".")[:2])
    if _tf_ver >= (4, 50):
        print(
            "WARN: transformers "
            f"{transformers.__version__} often breaks DeepSeek-OCR-2 (286 vs 287). "
            f"Prefer {DSOCR2_PYTHON} (4.46.x).",
            file=sys.stderr,
        )
except Exception:
    pass


def _extract_latex(raw: str) -> str:
    from app.ocr.formula_crop_extract import salvage_formula_from_raw

    hit = salvage_formula_from_raw(raw or "")
    if hit.block and (hit.block.latex_or_text or "").strip():
        return hit.block.latex_or_text.strip()
    return (raw or "").strip()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="DeepSeek-OCR-2 on frozen crops (shadow only)")
    ap.add_argument("--gold", required=True)
    ap.add_argument("--crop-root", default=str(ROOT / "benchmarks" / "crops"))
    ap.add_argument("--prefer-tight", action="store_true")
    ap.add_argument("--image-size", type=int, default=640)
    ap.add_argument("--prompt", choices=("document", "formula"), default="document")
    ap.add_argument("--experiment-id", default="L2")
    ap.add_argument("--out", default="")
    args = ap.parse_args(argv)

    from PIL import Image

    from app.ocr import OCRMode, PROMPT_DOCUMENT, PROMPT_FORMULA_LATEX
    from app.ocr.deepseek_ocr2 import DeepSeekOCR2Recognizer
    from app.ocr.deepseek_profiles import DEEPSEEK_FORMULA_PROFILE, DeepSeekOCRProfile
    from app.ocr.match_eval_v2 import FormulaMatchEvaluatorV2, summarize_reports

    prompt = PROMPT_DOCUMENT if args.prompt == "document" else PROMPT_FORMULA_LATEX
    profile = DeepSeekOCRProfile(
        name=f"k5_{args.experiment_id.lower()}",
        base_size=DEEPSEEK_FORMULA_PROFILE.base_size,
        image_size=int(args.image_size),
        crop_mode=True,
        max_new_tokens=DEEPSEEK_FORMULA_PROFILE.max_new_tokens,
        save_results=False,
        eval_mode=True,
        prompt=prompt,
    )
    recg = DeepSeekOCR2Recognizer(
        model_name=resolve_deepseek_model_name(),
        device="cuda:0",
        dtype="bf16",
        image_size=int(args.image_size),
        formula_profile=profile,
        allow_cpu=False,
        default_prompt=prompt,
    )

    gold_path = Path(args.gold)
    crop_root = Path(args.crop_root)
    ev = FormulaMatchEvaluatorV2(compute_cdm=False)
    reports = []
    details = []
    for line in gold_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if not row.get("verified"):
            continue
        rel = (row.get("crop_path_tight") if args.prefer_tight else row.get("crop_path")) or ""
        crop = crop_root / rel if rel else crop_root / "_missing.png"
        raw = ""
        pred = ""
        err = ""
        if not rel:
            err = "tight_crop_missing" if args.prefer_tight else "crop_missing"
        elif not crop.is_file():
            err = "crop_missing"
        else:
            try:
                from app.formula.vlm_crop_pad import letterbox_formula_crop_for_vlm

                im = letterbox_formula_crop_for_vlm(Image.open(crop))
                out = recg.recognize(
                    im,
                    mode=OCRMode.FORMULA,
                    prompt=prompt,
                )
                raw = (out.raw_output or out.markdown or "") if out else ""
                if not getattr(out, "success", False):
                    detail = ""
                    if getattr(out, "metadata", None):
                        detail = str((out.metadata or {}).get("detail") or "")
                    err = str(getattr(out, "error", None) or "deepseek_failed")
                    if detail:
                        err = f"{err}:{detail[:240]}"
                pred = _extract_latex(raw)
            except Exception as e:
                err = f"{type(e).__name__}:{e}"
        report = ev.compare(pred, row.get("gold_latex_raw") or "")
        reports.append(report)
        details.append(
            {
                "id": row.get("id"),
                "equation_number": row.get("equation_number"),
                "pred": pred,
                "raw": raw[:800],
                "gold": row.get("gold_latex_raw"),
                "error": err,
                **report.to_dict(),
            }
        )

    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "experiment_id": args.experiment_id,
        "model": "DeepSeek-OCR-2",
        "image_size": int(args.image_size),
        "prompt": args.prompt,
        "gold": str(gold_path),
        "summary": summarize_reports(reports),
        "details": details,
        "shadow_only": True,
        "prefer_tight": bool(args.prefer_tight),
    }
    default_name = f"deepseek_{args.experiment_id.lower()}_o018_tight.json"
    out = Path(args.out) if args.out else ROOT / "benchmarks" / "results" / default_name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out)
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    return 0 if all(not d.get("error") for d in details) else 2


if __name__ == "__main__":
    raise SystemExit(main())
