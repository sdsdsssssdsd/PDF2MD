# -*- coding: utf-8 -*-
"""Phase 5E：Lean Balanced 连跑 + Docling GPU 释放 A/B。

  C:\\python\\python3-12.3\\python.exe -u scripts/run_phase5e_lean_repeat.py
  C:\\python\\python3-12.3\\python.exe -u scripts/run_phase5e_lean_repeat.py --runs 5
  C:\\python\\python3-12.3\\python.exe -u scripts/run_phase5e_lean_repeat.py --gpu-ab
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
os.environ.setdefault("USE_TF", "0")

from app.engines import docling_engine
from app.engines.docling_gpu_release import docling_gpu_snapshot, release_docling_gpu
from app.engines.docling_telemetry import reset_docling_telemetry
from app.formula.config import formula_config_for_deepseek_limited_production
from app.formula.pipeline import FormulaPipeline
from app.ocr.deepseek_worker_client import get_deepseek_worker_client
from app.utils.paths import BENCHMARK_RUNS, ensure_dirs

PDF = Path(os.environ["PDF2MD_BENCH_PDF"]) if os.environ.get("PDF2MD_BENCH_PDF") else (ROOT / "input" / "O-018_Abdo2025_Stacking_SHAP.pdf")


def _per_formula_timings(shadow: dict) -> list[dict]:
    out: list[dict] = []
    for page in shadow.get("pages") or []:
        for c in page.get("candidates") or []:
            if isinstance(c, dict) and c.get("timing"):
                out.append(c["timing"])
    # fallback: would_replace 无 timing 时从 summary 挖
    if not out:
        for row in (shadow.get("summary") or {}).get("would_replace") or []:
            if isinstance(row, dict) and row.get("timing"):
                out.append(row["timing"])
    return out


def run_once(label: str, out_dir: Path, *, release_gpu: bool, empty_cache: bool) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    reset_docling_telemetry()
    # 同配置复用 converter；GPU-AB 时强制新建
    if release_gpu:
        docling_engine._converter_cache.clear()  # noqa: SLF001

    client = get_deepseek_worker_client()
    warm = client.warmup_async()
    t0 = time.perf_counter()
    gpu_pre = docling_gpu_snapshot()
    parsed = docling_engine.convert_pdf(
        PDF,
        out_dir,
        keep_images=True,
        keep_tables=True,
        keep_formulas=False,  # Lean
        ocr_mode="auto",
        images_scale=3.0,
        progress=lambda m: print(f"[{label}] {m}", flush=True),
    )
    docling_s = time.perf_counter() - t0
    if warm.is_alive():
        warm.join(timeout=240)

    release_meta = None
    if release_gpu:
        release_meta = release_docling_gpu(empty_cache=empty_cache)
        print(f"[{label}] GPU release: {release_meta}", flush=True)

    md = parsed.markdown_path.read_text(encoding="utf-8")
    cfg = formula_config_for_deepseek_limited_production(fallback_mode="clean")
    assert cfg.recognizer_primary == "null"
    assert cfg.lean_docling_balanced is True

    t1 = time.perf_counter()
    fres = FormulaPipeline(cfg).process_markdown(md, pdf_path=PDF)
    formula_s = time.perf_counter() - t1
    total = time.perf_counter() - t0

    sh = fres.report.deepseek_shadow or {}
    summ = (sh.get("summary") if isinstance(sh, dict) else {}) or {}
    wb = fres.report.writeback or {}
    timings = []
    # 从 execution candidates 收集 timing（shadow pages 结构）
    for page in sh.get("pages") or []:
        for r in page.get("results") or page.get("candidates") or []:
            if isinstance(r, dict) and r.get("timing"):
                timings.append(r["timing"])
    # Shadow may nest under execution
    exe = sh.get("execution") or {}
    for r in exe.get("candidates") or []:
        if isinstance(r, dict) and r.get("timing"):
            timings.append(r["timing"])

    # Also walk would_replace — timing may be attached in newer executor via shadow serializer
    for page in sh.get("pages") or []:
        dec = page.get("decision") or {}
        for r in (page.get("execution") or {}).get("candidates") or []:
            if isinstance(r, dict) and r.get("timing"):
                timings.append(r["timing"])

    row = {
        "label": label,
        "release_gpu": release_gpu,
        "empty_cache": empty_cache,
        "docling_seconds": round(docling_s, 3),
        "formula_pipeline_seconds": round(formula_s, 3),
        "total_seconds": round(total, 3),
        "deepseek_seconds": summ.get("actual_seconds"),
        "ocr_inference_seconds": summ.get("ocr_inference_seconds"),
        "deepseek_ocr_calls": summ.get("ocr_calls"),
        "deepseek_accepted": summ.get("accepted"),
        "coverage_rate": summ.get("coverage_rate"),
        "writeback_applied": wb.get("applied_count"),
        "gpu_pre_docling": gpu_pre,
        "gpu_release": release_meta,
        "gpu_post": docling_gpu_snapshot(),
        "per_formula_timings": timings or _per_formula_timings(sh),
        "recognizer_primary": cfg.recognizer_primary,
        "lean": cfg.lean_docling_balanced,
    }
    (out_dir / "final.md").write_text(fres.markdown, encoding="utf-8")
    (out_dir / "formula_qa.json").write_text(
        json.dumps(fres.report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "run.json").write_text(
        json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return row


def _stats(vals: list[float]) -> dict:
    if not vals:
        return {}
    vals = sorted(vals)
    return {
        "n": len(vals),
        "median": round(statistics.median(vals), 3),
        "mean": round(statistics.mean(vals), 3),
        "p95": round(vals[max(0, int(round(0.95 * (len(vals) - 1))))], 3),
        "min": round(vals[0], 3),
        "max": round(vals[-1], 3),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--gpu-ab", action="store_true", help="B1 vs B2 GPU release compare")
    ap.add_argument("--empty-cache", action="store_true", help="B2 also torch.cuda.empty_cache")
    args = ap.parse_args()
    if not PDF.is_file():
        print("PDF missing", PDF)
        return 2
    ensure_dirs()
    out = BENCHMARK_RUNS / "phase5e_lean_repeat"
    out.mkdir(parents=True, exist_ok=True)

    rows = []
    if args.gpu_ab:
        rows.append(
            run_once("B1_no_release", out / "B1", release_gpu=False, empty_cache=False)
        )
        rows.append(
            run_once(
                "B2_release",
                out / "B2",
                release_gpu=True,
                empty_cache=bool(args.empty_cache),
            )
        )
        dest_name = "summary_gpu_ab.json"
    else:
        for i in range(1, args.runs + 1):
            rows.append(
                run_once(
                    f"run{i}",
                    out / f"run{i}",
                    release_gpu=False,
                    empty_cache=False,
                )
            )
        dest_name = "summary_x5.json" if args.runs >= 5 else "summary.json"

    totals = [float(r["total_seconds"]) for r in rows]
    ds = [float(r["deepseek_seconds"] or 0) for r in rows]
    payload = {
        "pdf": str(PDF),
        "profile": "lean_balanced",
        "picture_export_scale": 3,
        "target_warm_median_lt": 110,
        "target_p95_lt": 140,
        "runs": rows,
        "stats_total_seconds": _stats(totals),
        "stats_deepseek_seconds": _stats(ds),
    }
    dest = out / dest_name
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    # 同步一份 summary.json 方便查看
    (out / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)
    print("WROTE", dest, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
