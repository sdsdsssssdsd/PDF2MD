# -*- coding: utf-8 -*-
"""Phase 5F：Formula Fast Path 消融 + O-018×10 稳定性。

  C:\\python\\python3-12.3\\python.exe -u scripts/run_phase5f_formula_fastpath.py
  C:\\python\\python3-12.3\\python.exe -u scripts/run_phase5f_formula_fastpath.py --runs 10
  C:\\python\\python3-12.3\\python.exe -u scripts/run_phase5f_formula_fastpath.py --ablate-only
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from dataclasses import replace
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
from app.ocr.deepseek_profiles import DEEPSEEK_FORMULA_PROFILE, DeepSeekOCRProfile
from app.ocr.deepseek_worker_client import (
    get_deepseek_worker_client,
    reset_deepseek_worker_client,
)
from app.utils.paths import BENCHMARK_RUNS, ensure_dirs

PDF = Path(os.environ["PDF2MD_BENCH_PDF"]) if os.environ.get("PDF2MD_BENCH_PDF") else (ROOT / "input" / "O-018_Abdo2025_Stacking_SHAP.pdf")


def _restart_worker() -> None:
    """强制重启 Worker，加载 Phase 5F 新代码。"""
    try:
        c = get_deepseek_worker_client()
        if c.ensure_started():
            try:
                c._rpc("quit", {}, timeout=5)  # noqa: SLF001
            except Exception:
                pass
    except Exception:
        pass
    reset_deepseek_worker_client(kill_worker=True)
    # 清掉残留 meta 端口
    meta = ROOT / ".cache" / "deepseek_worker.json"
    if meta.exists():
        try:
            meta.unlink()
        except Exception:
            pass


def _stats(vals: list[float]) -> dict:
    if not vals:
        return {}
    vals = sorted(vals)
    n = len(vals)

    def pct(p: float) -> float:
        if n == 1:
            return vals[0]
        i = min(n - 1, max(0, int(round(p * (n - 1)))))
        return vals[i]

    return {
        "n": n,
        "median": round(statistics.median(vals), 3),
        "mean": round(statistics.mean(vals), 3),
        "p90": round(pct(0.90), 3),
        "p95": round(pct(0.95), 3),
        "min": round(vals[0], 3),
        "max": round(vals[-1], 3),
    }


def _extract_timings(shadow: dict) -> list[dict]:
    out: list[dict] = []
    for row in (shadow.get("summary") or {}).get("would_replace") or []:
        t = row.get("timing") or {}
        if t:
            out.append(t)
    return out


def run_lean(
    label: str,
    out_dir: Path,
    *,
    formula_profile: DeepSeekOCRProfile | None = None,
) -> dict:
    """E2E Lean；Worker 侧 profile 由服务端默认 Formula Fast Path 决定。

    formula_profile 仅用于记录期望配置；真正覆盖通过重启 Worker 环境变量较重，
    消融用 RPC 参数在后续 microbench。此处跑默认 5F production profile。
    """
    del formula_profile
    out_dir.mkdir(parents=True, exist_ok=True)
    reset_docling_telemetry()
    client = get_deepseek_worker_client()
    warm = client.warmup_async()
    t0 = time.perf_counter()
    parsed = docling_engine.convert_pdf(
        PDF,
        out_dir,
        keep_images=True,
        keep_tables=True,
        keep_formulas=False,
        ocr_mode="auto",
        images_scale=3.0,
        progress=lambda m: print(f"[{label}] {m}", flush=True),
    )
    doc_s = time.perf_counter() - t0
    if warm.is_alive():
        warm.join(timeout=240)
    md = parsed.markdown_path.read_text(encoding="utf-8")
    cfg = formula_config_for_deepseek_limited_production(fallback_mode="clean")
    t1 = time.perf_counter()
    fres = FormulaPipeline(cfg).process_markdown(md, pdf_path=PDF)
    formula_s = time.perf_counter() - t1
    total = time.perf_counter() - t0
    sh = fres.report.deepseek_shadow or {}
    summ = (sh.get("summary") if isinstance(sh, dict) else {}) or {}
    wb = fres.report.writeback or {}
    timings = _extract_timings(sh)
    per_infer = [
        float(t.get("worker_inference_seconds") or t.get("recognize_wall_seconds") or 0)
        for t in timings
    ]
    row = {
        "label": label,
        "docling_seconds": round(doc_s, 3),
        "formula_pipeline_seconds": round(formula_s, 3),
        "total_seconds": round(total, 3),
        "deepseek_seconds": summ.get("actual_seconds"),
        "ocr_inference_seconds": summ.get("ocr_inference_seconds"),
        "writeback_applied": wb.get("applied_count"),
        "deepseek_accepted": summ.get("accepted"),
        "coverage_rate": summ.get("coverage_rate"),
        "per_formula_timings": timings,
        "per_formula_infer_stats": _stats(per_infer),
        "sample_breakdown": (timings[0].get("timing_breakdown") if timings else None),
        "sample_profile": (timings[0].get("profile") if timings else None),
    }
    (out_dir / "final.md").write_text(fres.markdown, encoding="utf-8")
    (out_dir / "formula_qa.json").write_text(
        json.dumps(fres.report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "run.json").write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"[{label}] total={row['total_seconds']} ds={row['deepseek_seconds']} "
        f"wb={row['writeback_applied']} profile={row['sample_profile']}",
        flush=True,
    )
    return row


def micro_ablate(raw_md: Path, out_root: Path) -> list[dict]:
    """在同一 raw.md 上换 Worker profile（tokens / crop_mode）。"""
    from app.ocr.deepseek_worker_client import get_deepseek_worker_client
    from app.ocr import OCRMode, PROMPT_FREE_OCR
    from app.formula.pipeline import FormulaPipeline
    from app.formula.config import formula_config_for_deepseek_limited_production
    import base64
    import io

    # 简化：直接 E2E 但先写 meta 让 worker 用不同 override — 通过临时改 recognizer
    # 更稳：跑完整 FormulaPipeline，并在 recognize RPC 注入参数。
    # 为此扩展 client.recognize 支持 override。
    variants = [
        {"id": "tok256_crop1", "max_new_tokens": 256, "crop_mode": True},
        {"id": "tok512_crop1", "max_new_tokens": 512, "crop_mode": True},
        {"id": "tok1024_crop1", "max_new_tokens": 1024, "crop_mode": True},
        {"id": "legacy_save", "max_new_tokens": 8192, "crop_mode": True, "note": "near-old defaults"},
    ]
    rows = []
    md = raw_md.read_text(encoding="utf-8")
    for v in variants:
        # monkeypatch client.recognize to pass overrides
        client = get_deepseek_worker_client()
        client.ensure_started()
        orig = client.recognize

        def recognize_ov(*, image_b64, mode="formula", prompt=None, _v=v):
            if client.disabled:
                return {"ok": False, "error": "disabled", "success": False}
            if not client.ensure_started():
                return {"ok": False, "error": client.last_error, "success": False}
            try:
                return client._rpc(  # noqa: SLF001
                    "recognize",
                    {
                        "image_b64": image_b64,
                        "mode": mode,
                        "prompt": prompt,
                        "model_name": None,
                        **{k: _v[k] for k in ("max_new_tokens", "crop_mode") if k in _v},
                    },
                    timeout=client.infer_timeout_seconds + 30,
                )
            except Exception as e:
                return {"ok": False, "error": str(e), "success": False}

        client.recognize = recognize_ov  # type: ignore[method-assign]
        try:
            label = f"ablate_{v['id']}"
            out = out_root / label
            out.mkdir(parents=True, exist_ok=True)
            cfg = formula_config_for_deepseek_limited_production(fallback_mode="clean")
            t0 = time.perf_counter()
            fres = FormulaPipeline(cfg).process_markdown(md, pdf_path=PDF)
            elapsed = time.perf_counter() - t0
            sh = fres.report.deepseek_shadow or {}
            summ = (sh.get("summary") or {})
            wb = fres.report.writeback or {}
            timings = _extract_timings(sh)
            per = [
                float(t.get("worker_inference_seconds") or 0) for t in timings
            ]
            row = {
                "variant": v,
                "formula_only_seconds": round(elapsed, 3),
                "deepseek_seconds": summ.get("actual_seconds"),
                "writeback_applied": wb.get("applied_count"),
                "accepted": summ.get("accepted"),
                "per_formula_infer_stats": _stats(per),
                "sample_breakdown": timings[0].get("timing_breakdown") if timings else None,
                "sample_profile": timings[0].get("profile") if timings else None,
                "sample_max_new_tokens": timings[0].get("max_new_tokens") if timings else None,
                "sample_crop_mode": timings[0].get("crop_mode") if timings else None,
            }
            (out / "formula_qa.json").write_text(
                json.dumps(fres.report.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            rows.append(row)
            print(
                f"[ablate {v['id']}] ds={row['deepseek_seconds']} wb={row['writeback_applied']} "
                f"per={row['per_formula_infer_stats']}",
                flush=True,
            )
        finally:
            client.recognize = orig  # type: ignore[method-assign]
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--ablate-only", action="store_true")
    ap.add_argument("--skip-ablate", action="store_true")
    ap.add_argument("--skip-restart", action="store_true")
    args = ap.parse_args()
    if not PDF.is_file():
        print("PDF missing", PDF)
        return 2
    ensure_dirs()
    out = BENCHMARK_RUNS / "phase5f_formula_fastpath"
    out.mkdir(parents=True, exist_ok=True)

    if not args.skip_restart:
        print("Restarting DeepSeek worker for Phase 5F code…", flush=True)
        _restart_worker()

    # 先跑一遍 lean 拿 raw.md，供 ablate 复用
    first = run_lean("warm0_seed", out / "warm0_seed")
    raw = out / "warm0_seed" / f"{PDF.stem}.raw.md"

    ablate_rows = []
    if not args.skip_ablate:
        print("=== token/crop ablation on fixed raw.md ===", flush=True)
        ablate_rows = micro_ablate(raw, out / "ablate")

    if args.ablate_only:
        payload = {"ablate": ablate_rows, "seed": first}
        (out / "summary_ablate.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("WROTE", out / "summary_ablate.json", flush=True)
        return 0

    rows = [first]
    for i in range(1, args.runs + 1):
        rows.append(run_lean(f"run{i}", out / f"run{i}"))

    totals = [float(r["total_seconds"]) for r in rows]
    ds = [float(r["deepseek_seconds"] or 0) for r in rows]
    # pick best ablate by ds time among quality-ok
    best_ablate = None
    ok = [a for a in ablate_rows if int(a.get("writeback_applied") or 0) >= 7]
    if ok:
        best_ablate = min(ok, key=lambda a: float(a.get("deepseek_seconds") or 1e9))

    payload = {
        "pdf": str(PDF),
        "phase": "5F",
        "default_formula_profile": DEEPSEEK_FORMULA_PROFILE.to_dict(),
        "targets": {
            "total_median_lt": 60,
            "total_p95_lt": 90,
            "deepseek_7_median_lt": 45,
        },
        "runs": rows,
        "stats_total_seconds": _stats(totals),
        "stats_deepseek_seconds": _stats(ds),
        "ablate": ablate_rows,
        "suggested_ablate": best_ablate,
        "batching_note": (
            "官方 model.infer() 无真实 multi-image batch API；"
            "batch 1/2/4 需自研 collate，本期不做 production 接入。"
        ),
    }
    dest = out / "summary_x10.json"
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        "stats_total": payload["stats_total_seconds"],
        "stats_deepseek": payload["stats_deepseek_seconds"],
        "suggested_ablate": best_ablate,
    }, ensure_ascii=False, indent=2), flush=True)
    print("WROTE", dest, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
