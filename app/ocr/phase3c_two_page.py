"""Phase 3C — 两页真实 GPU 验证（不接 Scheduler，不改模型/Gate/Extractor/bbox）。

Page A：单目标 formula crop（Eq.1）
Page B：同页多式 — formula×N vs page×1+cache（Eq.6+7 on page 7）
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from app.formula.config import FormulaConfig
from app.formula.gain import evaluate_recovery_gain
from app.formula.types import FormulaQuality
from app.formula.validator import validate_latex
from app.ocr.cache import file_sha1
from app.ocr.deepseek_benchmark import (
    DEFAULT_O018_CASES,
    BenchmarkCase,
    DeepSeekBenchmarkConfig,
    FormulaBenchmarkService,
    build_o018_cases,
)
from app.ocr.match_eval import FormulaMatchEvaluator
from app.utils.paths import BENCHMARK_RUNS, ensure_dirs

ProgressCB = Callable[[str], None]

# O-018：page6={1,4,5} page7={6,7}。无「仅 1 式」页；Test A 只恢复 Eq.1 验证单式路径。
PHASE3C_SINGLE_EQ = "1"
PHASE3C_MULTI_EQS = ("6", "7")  # 同页 ≥2


def _spec_by_eq(eq: str) -> dict[str, Any]:
    for s in DEFAULT_O018_CASES:
        if str(s["eq_number"]) == str(eq):
            return s
    raise KeyError(eq)


def _before_quality() -> FormulaQuality:
    return FormulaQuality(
        syntax_score=0.05,
        corruption_score=0.95,
        semantic_score=0.1,
        valid=False,
        recoverable=True,
        reasons=["phase3c_corrupted_fixture"],
    )


def _gate_eval(latex: str, case: BenchmarkCase) -> dict[str, Any]:
    fcfg = FormulaConfig()
    before_q = _before_quality()
    before_latex = r"\quad\quad\quad garbage \omega_{nd}"
    t0 = time.perf_counter()
    vr = validate_latex(
        latex,
        fcfg,
        context_before=case.context_before,
        context_after=case.context_after,
    )
    gain = evaluate_recovery_gain(
        before_quality=before_q,
        after_quality=vr.quality,
        before_latex=before_latex,
        after_latex=latex,
        context_before=case.context_before,
        context_after=case.context_after,
        after_valid=bool(latex) and vr.valid,
    )
    return {
        "gate_accepted": bool(gain.accept),
        "gate_reason": ",".join(gain.reasons) if gain.reasons else "",
        "gate_seconds": round(time.perf_counter() - t0, 6),
        "valid": bool(vr.valid),
    }


def _timing_from_mode(mode_dict: dict[str, Any]) -> dict[str, float]:
    t = mode_dict.get("timing") or {}
    return {
        "model_load_seconds": float(t.get("model_load_seconds") or 0.0),
        "render_seconds": float(t.get("pdf_render_seconds") or 0.0),
        "ocr_seconds": float(t.get("ocr_inference_seconds") or 0.0),
        "extract_seconds": float(t.get("postprocess_seconds") or 0.0),
        "validation_seconds": float(t.get("validation_seconds") or 0.0),
        "total_seconds": float(t.get("total_seconds") or 0.0),
        "cache_hit": bool(t.get("cache_hit")),
    }


def _enrich_case_result(
    *,
    case: BenchmarkCase,
    mode_key: str,
    case_row: dict[str, Any],
    matcher: FormulaMatchEvaluator,
    ocr_calls_delta: int,
) -> dict[str, Any]:
    mode = (case_row.get("modes") or {}).get(mode_key) or {}
    selected = mode.get("extracted_latex") or ""
    raw = mode.get("output") or ""
    match = matcher.compare(selected, case.gold_latex)
    layer = matcher.layer_report(raw_ocr=raw, selected=selected, gold=case.gold_latex)
    gate = _gate_eval(selected, case)
    timing = _timing_from_mode(mode)
    return {
        "equation": f"Eq. ({case.eq_number})",
        "page": case_row.get("page"),
        "formula_bbox": case_row.get("formula_bbox"),
        "ocr_output": (raw or "")[:8000],
        "selected_formula": selected,
        "extractor_method": mode.get("extractor_method"),
        "extractor_failure_reason": mode.get("extractor_failure_reason") or "",
        "human_usable": match.human_usable,
        "exact_normalized_match": match.exact_normalized_match,
        "structural_match": match.structural_match,
        "token_match": match.token_match,
        "layer": layer.to_dict(),
        "match_reasons": match.reasons,
        "gate_accepted": gate["gate_accepted"],
        "gate_reason": gate["gate_reason"],
        "gate_seconds": gate["gate_seconds"],
        "ocr_calls": ocr_calls_delta,
        "error": mode.get("error") or "",
        **timing,
        # wall 含 gate 重算（与 mode total 略不同）
        "pipeline_total_seconds": round(
            timing["total_seconds"] + float(gate["gate_seconds"]), 6
        ),
    }


def run_test_a_single_formula(
    pdf: Path,
    *,
    cfg: DeepSeekBenchmarkConfig,
    svc: FormulaBenchmarkService,
    progress: ProgressCB | None = None,
) -> dict[str, Any]:
    """单式：仅 DeepSeek formula ×1，禁止 region/page/retry。"""
    def emit(m: str) -> None:
        if progress:
            progress(m)

    emit("Phase3C Test A: single formula crop (Eq.1)")
    cases = build_o018_cases(pdf, [_spec_by_eq(PHASE3C_SINGLE_EQ)])
    case = cases[0]
    # 强制只跑 formula
    cfg.run_baseline = False
    cfg.run_deepseek_formula = True
    cfg.run_deepseek_region = False
    cfg.run_deepseek_page = False

    ocr_before = int(svc.telemetry.get("ocr_calls") or 0)
    t_wall = time.perf_counter()
    row = svc.run_case(case, progress=progress)
    ocr_after = int(svc.telemetry.get("ocr_calls") or 0)
    matcher = FormulaMatchEvaluator()
    detail = _enrich_case_result(
        case=case,
        mode_key="deepseek_formula",
        case_row=row,
        matcher=matcher,
        ocr_calls_delta=ocr_after - ocr_before,
    )
    detail["wall_seconds"] = round(time.perf_counter() - t_wall, 3)
    detail["acceptance"] = {
        "ocr_calls_eq_1": detail["ocr_calls"] == 1,
        "human_usable": detail["human_usable"],
        "gate_accepted": detail["gate_accepted"],
        "no_region_page_fallback": True,
        "no_retry": True,
        "passed": bool(
            detail["ocr_calls"] == 1
            and detail["human_usable"]
            and detail["gate_accepted"]
            and not detail.get("error")
        ),
    }
    return detail


def run_test_b_multi_formula(
    pdf: Path,
    *,
    cfg: DeepSeekBenchmarkConfig,
    svc_formula: FormulaBenchmarkService,
    svc_page: FormulaBenchmarkService,
    progress: ProgressCB | None = None,
) -> dict[str, Any]:
    """同页多式：formula×N vs page×1 + cache reuse。"""
    def emit(m: str) -> None:
        if progress:
            progress(m)

    specs = [_spec_by_eq(n) for n in PHASE3C_MULTI_EQS]
    cases = build_o018_cases(pdf, specs)
    matcher = FormulaMatchEvaluator()

    # --- 方案 1：每个公式独立 formula crop ---
    emit("Phase3C Test B.1: formula crop × N")
    cfg.run_baseline = False
    cfg.run_deepseek_formula = True
    cfg.run_deepseek_region = False
    cfg.run_deepseek_page = False
    formula_rows: list[dict[str, Any]] = []
    ocr0 = int(svc_formula.telemetry.get("ocr_calls") or 0)
    t0 = time.perf_counter()
    for case in cases:
        before = int(svc_formula.telemetry.get("ocr_calls") or 0)
        row = svc_formula.run_case(case, progress=progress)
        after = int(svc_formula.telemetry.get("ocr_calls") or 0)
        formula_rows.append(
            _enrich_case_result(
                case=case,
                mode_key="deepseek_formula",
                case_row=row,
                matcher=matcher,
                ocr_calls_delta=after - before,
            )
        )
    formula_wall = time.perf_counter() - t0
    formula_ocr = int(svc_formula.telemetry.get("ocr_calls") or 0) - ocr0

    # --- 方案 2：整页 OCR 一次 + 分别 extract ---
    emit("Phase3C Test B.2: page OCR × 1 + extract per Eq")
    cfg.run_deepseek_formula = False
    cfg.run_deepseek_page = True
    page_rows: list[dict[str, Any]] = []
    ocr0p = int(svc_page.telemetry.get("ocr_calls") or 0)
    t1 = time.perf_counter()
    for case in cases:
        before = int(svc_page.telemetry.get("ocr_calls") or 0)
        row = svc_page.run_case(case, progress=progress)
        after = int(svc_page.telemetry.get("ocr_calls") or 0)
        page_rows.append(
            _enrich_case_result(
                case=case,
                mode_key="deepseek_page",
                case_row=row,
                matcher=matcher,
                ocr_calls_delta=after - before,
            )
        )
    page_wall = time.perf_counter() - t1
    page_ocr = int(svc_page.telemetry.get("ocr_calls") or 0) - ocr0p
    cache_hits = sum(1 for r in page_rows if r.get("cache_hit"))

    def _agg(rows: list[dict[str, Any]], *, ocr_calls: int, wall: float) -> dict[str, Any]:
        return {
            "equations": [r["equation"] for r in rows],
            "page": rows[0]["page"] if rows else None,
            "n": len(rows),
            "ocr_calls": ocr_calls,
            "cache_hits": sum(1 for r in rows if r.get("cache_hit")),
            "human_usable": sum(1 for r in rows if r.get("human_usable")),
            "extractor_success": sum(
                1 for r in rows if (r.get("layer") or {}).get("layer") == "extractor_success"
            ),
            "gate_accepted": sum(1 for r in rows if r.get("gate_accepted")),
            "total_seconds": round(wall, 3),
            "sum_ocr_seconds": round(sum(float(r.get("ocr_seconds") or 0) for r in rows), 3),
            "per_formula": rows,
        }

    formula_mode = _agg(formula_rows, ocr_calls=formula_ocr, wall=formula_wall)
    page_mode = _agg(page_rows, ocr_calls=page_ocr, wall=page_wall)
    page_mode["page_ocr_once"] = page_ocr == 1
    page_mode["cache_hits_on_reuse"] = cache_hits

    return {
        "formula_mode": formula_mode,
        "page_mode": page_mode,
    }


def build_comparison(multi: dict[str, Any], *, safety_factor: float = 1.2) -> dict[str, Any]:
    fm = multi["formula_mode"]
    pm = multi["page_mode"]
    f_sec = float(fm["total_seconds"])
    p_sec = float(pm["total_seconds"])
    f_u = int(fm["human_usable"])
    p_u = int(pm["human_usable"])
    n = int(fm["n"])

    # 质量：page 最多允许少 1 个 usable
    quality_ok = p_u >= max(0, f_u - 1)
    # 成本：page * safety < formula 才推荐 page
    cost_page_better = (p_sec * safety_factor) < f_sec
    if cost_page_better and quality_ok:
        recommended = "PAGE"
    else:
        recommended = "FORMULA_BATCH"

    avg_formula = f_sec / max(1, n)
    # 粗算：多少坏式时 page 才摊平（用本次实测 page 墙钟）
    break_even_n = None
    if avg_formula > 0:
        break_even_n = round((p_sec * safety_factor) / avg_formula, 2)

    return {
        "formula_total_seconds": round(f_sec, 3),
        "page_total_seconds": round(p_sec, 3),
        "formula_usable": f_u,
        "page_usable": p_u,
        "formula_gate_accepted": int(fm["gate_accepted"]),
        "page_gate_accepted": int(pm["gate_accepted"]),
        "formula_ocr_calls": int(fm["ocr_calls"]),
        "page_ocr_calls": int(pm["ocr_calls"]),
        "page_ocr_once_ok": bool(pm.get("page_ocr_once")),
        "quality_loss_ok": quality_ok,
        "cost_page_better_with_safety": cost_page_better,
        "safety_factor": safety_factor,
        "break_even_bad_count_estimate": break_even_n,
        "recommended_mode": recommended,
        "scheduler_v1_hint": (
            "cost-aware：仅当 page_cost * safety_factor < bad_count * avg_formula_seconds "
            "且 usable 不差超过 1 时用 PAGE；否则 FORMULA_BATCH。不要写死 >=2→page。"
        ),
        "scheduler_v1_ready": {
            "single_formula_human_usable_ge_90": None,  # 由顶层填写
            "multi_page_cheaper_and_quality_ok": bool(cost_page_better and quality_ok),
            "note": "进入 Scheduler v1 还需单式验收 passed + false_accept=0（沿用 3B）。",
        },
    }


def run_phase3c_two_page(
    pdf_path: str | Path,
    *,
    cfg: DeepSeekBenchmarkConfig | None = None,
    progress: ProgressCB | None = None,
    out_path: Path | None = None,
    safety_factor: float = 1.2,
) -> dict[str, Any]:
    ensure_dirs()
    pdf = Path(pdf_path)
    cfg = cfg or DeepSeekBenchmarkConfig(experiment_only=True)
    # 共享同一 DeepSeek 实例，避免重复 load；formula / page 分 telemetry
    svc_a = FormulaBenchmarkService(cfg=cfg)
    # Test A
    single = run_test_a_single_formula(pdf, cfg=cfg, svc=svc_a, progress=progress)
    # Test B：formula 与 page 分两个 service 的 cache/telemetry，但复用已 load 的模型
    svc_b_formula = FormulaBenchmarkService(cfg=cfg, doc_recognizer=svc_a.doc_recognizer)
    svc_b_page = FormulaBenchmarkService(cfg=cfg, doc_recognizer=svc_a.doc_recognizer)
    multi = run_test_b_multi_formula(
        pdf,
        cfg=cfg,
        svc_formula=svc_b_formula,
        svc_page=svc_b_page,
        progress=progress,
    )
    comparison = build_comparison(multi, safety_factor=safety_factor)
    single_ok = bool((single.get("acceptance") or {}).get("passed"))
    comparison["scheduler_v1_ready"]["single_formula_passed"] = single_ok
    comparison["scheduler_v1_ready"]["single_formula_human_usable_ge_90"] = bool(
        single.get("human_usable")
    )

    payload: dict[str, Any] = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "phase": "3C",
        "experiment_only": True,
        "pdf": str(pdf),
        "pdf_hash": file_sha1(pdf),
        "boundaries": [
            "no RecoveryScheduler",
            "no DeepSeek param change",
            "no Gate/Extractor/bbox change",
            "no OCR retry",
            "no full-PDF run",
            "no region mode",
        ],
        "page_selection": {
            "page_a": {
                "target_eq": PHASE3C_SINGLE_EQ,
                "note": "O-018 回归集中无「仅 1 坏式」页；Test A 只恢复 Eq.1，验证单式 formula 路径。",
            },
            "page_b": {
                "target_eqs": list(PHASE3C_MULTI_EQS),
                "note": "page 7 上 Eq.6+Eq.7，验证 formula×N vs page×1+cache。",
            },
        },
        "config_snapshot": {
            "model_name": cfg.model_name,
            "device": cfg.device,
            "base_size": cfg.base_size,
            "image_size": cfg.image_size,
            "crop_mode": cfg.crop_mode,
            "formula_render_scale": cfg.formula_render_scale,
            "page_render_scale": cfg.page_render_scale,
        },
        "single_formula": single,
        "multi_formula": multi,
        "comparison": comparison,
        "telemetry": {
            "test_a": dict(svc_a.telemetry),
            "test_b_formula": dict(svc_b_formula.telemetry),
            "test_b_page": dict(svc_b_page.telemetry),
        },
    }

    dest = out_path or (BENCHMARK_RUNS / "phase3c_two_page_gpu.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    payload["output_path"] = str(dest)
    return payload
