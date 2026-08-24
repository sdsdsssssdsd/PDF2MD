# -*- coding: utf-8 -*-
"""Phase 5D：O-018 连续两跑（cold/warm）墙钟回归。

用法（建议 dsocr2 已可启动 Worker；主环境跑本脚本即可）：
  python -u scripts/run_phase5d_o018_warm_double.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
os.environ.setdefault("USE_TF", "0")

from app.engines import docling_engine
from app.engines.docling_telemetry import get_docling_telemetry, reset_docling_telemetry
from app.formula.config import formula_config_for_deepseek_limited_production
from app.formula.pipeline import FormulaPipeline
from app.ocr.deepseek_worker_client import get_deepseek_worker_client, reset_deepseek_worker_client
from app.utils.paths import BENCHMARK_RUNS, ensure_dirs

PDF = Path(os.environ["PDF2MD_BENCH_PDF"]) if os.environ.get("PDF2MD_BENCH_PDF") else (ROOT / "input" / "O-018_Abdo2025_Stacking_SHAP.pdf")


def _one_run(label: str, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    run_wall0 = time.time()
    client = get_deepseek_worker_client()
    warm = client.warmup_async()
    t_doc0 = time.time()
    parsed = docling_engine.convert_pdf(
        PDF,
        out_dir,
        keep_images=True,
        keep_tables=True,
        keep_formulas=True,
        ocr_mode="auto",
        images_scale=3.0,
        image_path_mode="relative",
        progress=lambda m: print(f"[{label}] {m}", flush=True),
    )
    docling_s = time.time() - t_doc0
    if warm.is_alive():
        warm.join(timeout=240)
    ds, de = t_doc0, t_doc0 + docling_s
    ls, lf = client.timings.load_started_at, client.timings.load_finished_at
    overlap = 0.0
    load_s = float(client.timings.load_seconds or 0)
    # 仅统计「本趟」内完成的 load；跨 run 复用不计 blocking
    if lf and lf >= run_wall0 and ls:
        overlap = max(0.0, min(lf, de) - max(ls, ds))
        blocking = max(0.0, load_s - overlap)
    else:
        load_s = 0.0
        blocking = 0.0
    md = parsed.markdown_path.read_text(encoding="utf-8")
    cfg = formula_config_for_deepseek_limited_production(fallback_mode="clean")
    t_f0 = time.perf_counter()
    fres = FormulaPipeline(cfg).process_markdown(md, pdf_path=PDF)
    formula_s = time.perf_counter() - t_f0
    total = time.perf_counter() - t0
    sh = (fres.report.deepseek_shadow or {}).get("summary") or fres.report.deepseek_shadow or {}
    wb = fres.report.writeback or {}
    telem = get_docling_telemetry().to_dict()
    row = {
        "label": label,
        "total_seconds": round(total, 3),
        "docling_seconds": round(docling_s, 3),
        "docling_telemetry": parsed.metadata.get("docling"),
        "docling_session_telemetry": telem,
        "deepseek_load_seconds": round(load_s, 3),
        "deepseek_load_overlap": round(overlap, 3),
        "deepseek_blocking_load": round(blocking, 3),
        "formula_pipeline_seconds": round(formula_s, 3),
        "shadow_ocr_calls": sh.get("ocr_calls") if isinstance(sh, dict) else None,
        "shadow_accepted": sh.get("accepted") if isinstance(sh, dict) else None,
        "coverage_rate": sh.get("coverage_rate") if isinstance(sh, dict) else None,
        "writeback_applied": wb.get("applied_count"),
        "writeback_skips": [
            (e.get("candidate_id"), e.get("skip_reason"))
            for e in (wb.get("entries") or [])
            if e.get("skip_reason")
        ],
        "recognizer_via": sh.get("recognizer_via") if isinstance(sh, dict) else None,
    }
    (out_dir / f"{label}.md").write_text(fres.markdown, encoding="utf-8")
    (out_dir / f"{label}.formula_qa.json").write_text(
        json.dumps(fres.report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return row


def main() -> int:
    if not PDF.is_file():
        print("PDF missing:", PDF, flush=True)
        return 2
    ensure_dirs()
    out = BENCHMARK_RUNS / "phase5d_o018_warm_double"
    out.mkdir(parents=True, exist_ok=True)
    reset_deepseek_worker_client(kill_worker=True)
    reset_docling_telemetry()

    rows = []
    rows.append(_one_run("run1_coldish", out / "run1"))
    rows.append(_one_run("run2_warm", out / "run2"))

    payload = {
        "pdf": str(PDF),
        "picture_export_scale": 3.0,
        "runs": rows,
        "notes": [
            "run2 应 converter_reused=true 且 deepseek_blocking_load≈0",
            "若 run2 docling 仍≈run1，瓶颈在 convert 本身而非 converter init",
        ],
    }
    dest = out / "summary.json"
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)
    print("WROTE", dest, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
