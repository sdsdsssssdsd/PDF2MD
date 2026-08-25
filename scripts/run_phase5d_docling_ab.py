# -*- coding: utf-8 -*-
"""Phase 5D / debug10：Docling E2E 消融（picture 固定 x3）+ picture OFF diagnostic。

  C:\\python\\python3-12.3\\python.exe -u scripts/run_phase5d_docling_ab.py
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
os.environ.setdefault("USE_TF", "0")

from app.engines import docling_engine
from app.engines.docling_telemetry import reset_docling_telemetry
from app.formula.config import formula_config_for_deepseek_limited_production
from app.formula.pipeline import FormulaPipeline
from app.ocr.deepseek_worker_client import get_deepseek_worker_client
from app.utils.paths import BENCHMARK_RUNS, ensure_dirs

PDF = (
    Path(os.environ["PDF2MD_BENCH_PDF"])
    if os.environ.get("PDF2MD_BENCH_PDF")
    else (ROOT / "input" / "O-018_Abdo2025_Stacking_SHAP.pdf")
)

VARIANTS = [
    {"id": "A", "keep_formulas": True, "keep_tables": True, "keep_images": True},
    {"id": "B", "keep_formulas": False, "keep_tables": True, "keep_images": True},
    {"id": "C", "keep_formulas": True, "keep_tables": False, "keep_images": True},
    {"id": "D", "keep_formulas": False, "keep_tables": False, "keep_images": True},
]


def _count_raw_formulas(md: str) -> dict:
    displays = len(re.findall(r"\$\$.+?\$\$", md, re.S))
    not_dec = len(re.findall(r"formula-not-decoded", md))
    return {
        "raw_display_count": displays,
        "raw_not_decoded_count": not_dec,
        "raw_formula_slots": displays + not_dec,
    }


def run_variant(v: dict, out_root: Path, *, pages_hint: int | None = None) -> dict:
    vid = v["id"]
    out_dir = out_root / vid
    out_dir.mkdir(parents=True, exist_ok=True)
    docling_engine._converter_cache.clear()  # noqa: SLF001
    reset_docling_telemetry()

    client = get_deepseek_worker_client()
    warm = client.warmup_async()
    t0 = time.perf_counter()
    parsed = docling_engine.convert_pdf(
        PDF,
        out_dir,
        keep_images=bool(v.get("keep_images", True)),
        keep_tables=bool(v["keep_tables"]),
        keep_formulas=bool(v["keep_formulas"]),
        ocr_mode="auto",
        images_scale=3.0,
        image_path_mode="relative",
        progress=lambda m: print(f"[{vid}] {m}", flush=True),
    )
    docling_s = time.perf_counter() - t0
    if warm.is_alive():
        warm.join(timeout=240)

    md = parsed.markdown_path.read_text(encoding="utf-8")
    raw_stats = _count_raw_formulas(md)
    cfg = formula_config_for_deepseek_limited_production(fallback_mode="clean")
    t1 = time.perf_counter()
    fres = FormulaPipeline(cfg).process_markdown(md, pdf_path=PDF)
    formula_s = time.perf_counter() - t1
    total = time.perf_counter() - t0

    sh = fres.report.deepseek_shadow or {}
    summ = (sh.get("summary") if isinstance(sh, dict) else {}) or {}
    wb = fres.report.writeback or {}
    applied = int(wb.get("applied_count") or 0)
    accepted = int(summ.get("accepted") or 0)
    usable = max(applied, accepted)
    unresolved = int(fres.report.recovery_failed_count or 0)
    left_nd = fres.markdown.count("formula-not-decoded")
    pages = pages_hint or 16
    (out_dir / "final.md").write_text(fres.markdown, encoding="utf-8")
    (out_dir / "formula_qa.json").write_text(
        json.dumps(fres.report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    wb_ids = [
        e.get("candidate_id")
        for e in (wb.get("entries") or [])
        if e.get("writeback_applied") or (not e.get("skip_reason") and e.get("accepted"))
    ]
    return {
        "variant": vid,
        "keep_formulas_enrich": v["keep_formulas"],
        "keep_tables": v["keep_tables"],
        "keep_images": v.get("keep_images", True),
        "picture_export_scale": 3.0 if v.get("keep_images", True) else 0.0,
        "docling_seconds": round(docling_s, 3),
        "docling_seconds_per_page": round(docling_s / max(1, pages), 3),
        "docling_detail": (parsed.metadata or {}).get("docling"),
        **raw_stats,
        "formula_count": fres.report.formula_count,
        "valid_before_recovery": fres.report.validated,
        "corrupted_formula_count": fres.report.corrupted_formula_count,
        "formula_pipeline_seconds": round(formula_s, 3),
        "deepseek_attempts": summ.get("ocr_calls"),
        "deepseek_seconds": summ.get("actual_seconds"),
        "deepseek_accepted": accepted,
        "coverage_rate": summ.get("coverage_rate"),
        "recovered_count": fres.report.recovery_success_count,
        "unresolved_count": unresolved,
        "final_not_decoded_left": left_nd,
        "writeback_applied": applied,
        "final_usable_count": usable,
        "formula_incomplete": left_nd > 0 or unresolved > applied,
        "writeback_skips": [
            (e.get("candidate_id"), e.get("skip_reason"))
            for e in (wb.get("entries") or [])
            if e.get("skip_reason")
        ],
        "writeback_candidate_ids": wb_ids
        or [e.get("candidate_id") for e in (wb.get("entries") or [])],
        "total_seconds": round(total, 3),
        "seconds_per_usable_formula": (
            round(total / usable, 3) if usable > 0 else None
        ),
        "seconds_per_recovered_formula": (
            round(float(summ.get("actual_seconds") or formula_s) / max(1, accepted), 3)
            if accepted
            else None
        ),
    }


def run_picture_diagnostic(out_root: Path) -> dict:
    """仅测 picture x3 渲染成本归属；不得作生产降质。"""
    rows = []
    for keep_img, label in ((True, "picture_x3_ON"), (False, "picture_OFF")):
        out_dir = out_root / "picture_diag" / label
        out_dir.mkdir(parents=True, exist_ok=True)
        docling_engine._converter_cache.clear()  # noqa: SLF001
        reset_docling_telemetry()
        t0 = time.perf_counter()
        parsed = docling_engine.convert_pdf(
            PDF,
            out_dir,
            keep_images=keep_img,
            keep_tables=True,
            keep_formulas=True,
            ocr_mode="auto",
            images_scale=3.0,
            image_path_mode="relative",
            progress=lambda m, lb=label: print(f"[{lb}] {m}", flush=True),
        )
        s = time.perf_counter() - t0
        rows.append(
            {
                "label": label,
                "keep_images": keep_img,
                "docling_seconds": round(s, 3),
                "docling_detail": (parsed.metadata or {}).get("docling"),
            }
        )
    delta = None
    if len(rows) == 2:
        delta = round(rows[0]["docling_seconds"] - rows[1]["docling_seconds"], 3)
    return {
        "runs": rows,
        "est_picture_x3_seconds": delta,
        "note": "diagnostic only; production stays picture x3",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--skip-picture-diag", action="store_true")
    ap.add_argument("--picture-diag-only", action="store_true")
    args = ap.parse_args()
    if not PDF.is_file():
        print("PDF missing", PDF, flush=True)
        return 2
    ensure_dirs()
    out = BENCHMARK_RUNS / "phase5d_docling_ab_v2"
    out.mkdir(parents=True, exist_ok=True)

    picture_diag = None
    if args.picture_diag_only:
        picture_diag = run_picture_diagnostic(out)
        payload = {"picture_diagnostic": picture_diag}
        (out / "summary.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)
        return 0

    variants = VARIANTS[: args.limit] if args.limit and args.limit > 0 else VARIANTS
    rows = []
    for v in variants:
        print(
            f"=== {v['id']} enrich={v['keep_formulas']} table={v['keep_tables']} ===",
            flush=True,
        )
        rows.append(run_variant(v, out))
        (out / "partial_summary.json").write_text(
            json.dumps({"runs": rows}, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    if not args.skip_picture_diag:
        print("=== picture diagnostic ===", flush=True)
        picture_diag = run_picture_diagnostic(out)

    usable = [
        r
        for r in rows
        if int(r.get("final_usable_count") or 0) > 0
        or int(r.get("writeback_applied") or 0) > 0
    ]
    best = min(usable, key=lambda r: float(r["total_seconds"])) if usable else None
    payload = {
        "pdf": str(PDF),
        "picture_export_scale_fixed": 3.0,
        "target_warm_total_seconds": 120,
        "runs": rows,
        "suggested_balanced_by_total_and_quality": best,
        "differential_docling_estimates_sec": {
            "formula_enrich_A_minus_B": (
                round(rows[0]["docling_seconds"] - rows[1]["docling_seconds"], 3)
                if len(rows) >= 2
                else None
            ),
            "table_A_minus_C": (
                round(rows[0]["docling_seconds"] - rows[2]["docling_seconds"], 3)
                if len(rows) >= 3
                else None
            ),
            "enrich_and_table_A_minus_D": (
                round(rows[0]["docling_seconds"] - rows[3]["docling_seconds"], 3)
                if len(rows) >= 4
                else None
            ),
        },
        "picture_diagnostic": picture_diag,
        "notes": [
            "比较 total_seconds + final_usable_count，禁止只看 Docling",
            "alignment protection 保持；Eq6/7 应出现 page7_eq6/eq7",
        ],
    }
    dest = out / "summary.json"
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)
    print("WROTE", dest, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
