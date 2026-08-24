"""Phase 4B.1 — O-018 真实文档 Shadow Validation（不改 Markdown）。"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from app.formula.benchmark import resolve_case_bbox
from app.formula.config import FormulaConfig
from app.formula.session import FormulaRecoverySession
from app.formula.types import FormulaCandidate, FormulaLifecycle
from app.ocr.cost_model import RecoveryCostModel, default_profile_path
from app.ocr.deepseek_benchmark import DEFAULT_O018_CASES, build_o018_cases
from app.ocr.deepseek_ocr2 import DeepSeekOCR2Recognizer
from app.ocr.match_eval import FormulaMatchEvaluator
from app.ocr.shadow import ShadowRecoveryRunner
from app.utils.paths import BENCHMARK_RUNS, ensure_dirs

ProgressCB = Callable[[str], None]


def build_o018_shadow_candidates(
    pdf: Path, session: FormulaRecoverySession
) -> list[FormulaCandidate]:
    """用 O-018 五个回归坏式构造 corrupted candidates（带 page/bbox）。"""
    cases = build_o018_cases(pdf)
    out: list[FormulaCandidate] = []
    for case in cases:
        page, bbox = resolve_case_bbox(case, session)
        # 故意用损坏原文，模拟待恢复状态
        garbage = r"\quad\quad\quad\quad \omega_{nd} garbage"
        out.append(
            FormulaCandidate(
                text=garbage,
                raw_text=garbage,
                page=page,
                bbox=bbox,
                context_before=case.context_before,
                context_after=case.context_after,
                source_type="parser_math",
                display_mode="display",
                lifecycle=FormulaLifecycle.CORRUPTED,
                status="corrupted",
                issues=["phase4b1_fixture_corrupted"],
            )
        )
    return out


def run_o018_shadow_validation(
    pdf_path: str | Path,
    *,
    model_name: str,
    device: str = "cuda:0",
    progress: ProgressCB | None = None,
    out_path: Path | None = None,
    profile_path: Path | None = None,
) -> dict[str, Any]:
    """整篇 session + 单 recognizer 实例；正文不修改。"""
    ensure_dirs()
    pdf = Path(pdf_path)

    def emit(m: str) -> None:
        if progress:
            progress(m)

    cfg = FormulaConfig(
        deepseek_shadow_enabled=True,
        deepseek_scheduler_enabled=True,
        deepseek_experiment_only=True,
        deepseek_recovery_enabled=False,  # 不进生产写回
        deepseek_min_page_formula_count=8,
        deepseek_page_safety_factor=1.2,
        deepseek_max_formulas_per_document=10,
        deepseek_max_total_recovery_seconds=270.0,  # 硬验收：不得拖到失控
        crop_render_scale=2.0,
    )

    # 单实例：禁止在页循环里 new recognizer
    DeepSeekOCR2Recognizer.reset_class_model()
    recognizer = DeepSeekOCR2Recognizer(
        model_name=model_name,
        device=device,
        dtype="bf16",
        base_size=1024,
        image_size=640,
        crop_mode=True,
        allow_cpu=False,
    )

    profile = profile_path or default_profile_path()
    cost = RecoveryCostModel(
        profile_path=profile,
        auto_load=True,
        auto_save=True,
        max_outlier_multiplier=float(cfg.deepseek_outlier_multiplier),
    )
    try:
        import torch

        gpu_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"
    except Exception:
        gpu_name = "unknown"
    cost.set_runtime(
        model_loaded=False,
        device=gpu_name,
        recognizer="deepseek-ocr-2",
        model="DeepSeek-OCR-2",
        dtype="bf16",
    )
    ema_before = {
        "formula_seconds_ema": cost.snap.formula_seconds_ema,
        "page_seconds_ema": cost.snap.page_seconds_ema,
        "model_load_seconds_ema": cost.snap.model_load_seconds_ema,
        "formula_samples": cost.snap.formula_samples,
        "page_samples": cost.snap.page_samples,
    }

    t_doc = time.perf_counter()
    with FormulaRecoverySession(pdf, cfg) as session:
        emit("resolve O-018 corrupted candidates")
        t_parse = time.perf_counter()
        candidates = build_o018_shadow_candidates(pdf, session)
        parse_seconds = time.perf_counter() - t_parse

        runner = ShadowRecoveryRunner(
            config=cfg,
            recognizer=recognizer,
            cost_model=cost,
        )
        emit(f"shadow run: {len(candidates)} corrupted formulas")
        shadow = runner.run(candidates, session=session, pdf_path=pdf)

    total_seconds = time.perf_counter() - t_doc
    load_count = DeepSeekOCR2Recognizer.model_load_count()

    matcher = FormulaMatchEvaluator()
    gold_by_eq = {str(s["eq_number"]): str(s["gold_latex"]) for s in DEFAULT_O018_CASES}
    human_rows = []
    for row in (shadow.summary.get("would_replace") or []):
        gold = gold_by_eq.get(str(row.get("eq_number") or ""), "")
        m = matcher.compare(row.get("recovered") or "", gold) if gold else None
        human_rows.append(
            {
                **row,
                "human_usable": bool(m.human_usable) if m else False,
                "exact_normalized_match": bool(m.exact_normalized_match) if m else False,
            }
        )

    ema_after = {
        "formula_seconds_ema": cost.snap.formula_seconds_ema,
        "page_seconds_ema": cost.snap.page_seconds_ema,
        "model_load_seconds_ema": cost.snap.model_load_seconds_ema,
        "formula_samples": cost.snap.formula_samples,
        "page_samples": cost.snap.page_samples,
        "last_raw_formula_seconds": cost.snap.last_raw_formula_seconds,
        "last_clipped_formula_seconds": cost.snap.last_clipped_formula_seconds,
    }

    inference = float(shadow.summary.get("ocr_inference_seconds") or 0.0)
    load_sec = float(shadow.summary.get("model_load_seconds") or 0.0)
    # 验收：总时间不得回到 270s 失控；warm OCR 应远小于 load
    acceptance = {
        "model_load_count_le_1": load_count <= 1,
        "write_markdown": False,
        "total_under_270s": total_seconds < 270.0,
        "ocr_inference_under_90s": inference < 90.0,
        "scheduler_no_page_for_n_lt_8": all(
            (p.scheduler.get("decision") != "page")
            or (p.corrupted_count >= 8)
            for p in shadow.pages
        ),
    }
    acceptance["passed"] = all(
        [
            acceptance["model_load_count_le_1"],
            acceptance["total_under_270s"],
            acceptance["ocr_inference_under_90s"],
            acceptance["scheduler_no_page_for_n_lt_8"],
        ]
    )

    payload: dict[str, Any] = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "phase": "4B.1",
        "pdf": str(pdf),
        "write_markdown": False,
        "config": {
            "deepseek_shadow_enabled": True,
            "deepseek_scheduler_enabled": True,
            "deepseek_recovery_writeback_enabled": False,
            "min_page_formula_count": cfg.deepseek_min_page_formula_count,
            "model_name": model_name,
            "device": device,
        },
        "timing": {
            "document_total_seconds": round(total_seconds, 3),
            "candidate_resolve_seconds": round(parse_seconds, 3),
            "model_load_seconds": round(load_sec, 3),
            "ocr_inference_seconds": round(inference, 3),
            "shadow_actual_seconds": shadow.summary.get("actual_seconds"),
            "shadow_estimated_seconds": shadow.summary.get("estimated_seconds"),
        },
        "model_load_count": load_count,
        "deepseek_shadow": shadow.to_dict(),
        "would_replace_review": human_rows,
        "ema_before": ema_before,
        "ema_after": ema_after,
        "acceptance": acceptance,
        "notes": [
            "正文未修改；would_replace 仅供 4C 前人工 diff。",
            "单 DeepSeekOCR2Recognizer 实例覆盖整篇 session。",
        ],
    }

    qa_sidecar = {
        "phase": "4B.1_shadow",
        "corrupted_formula_count": shadow.summary.get("corrupted_formula_count"),
        "deepseek_shadow": shadow.to_dict(),
        "would_replace_review": human_rows,
        "timing": payload["timing"],
        "model_load_count": load_count,
        "acceptance": acceptance,
    }
    payload["formula_qa"] = qa_sidecar

    dest = out_path or (BENCHMARK_RUNS / "phase4b1_o018_shadow.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    qa_path = BENCHMARK_RUNS / "O018_phase4b1.formula_qa.json"
    qa_path.write_text(json.dumps(qa_sidecar, ensure_ascii=False, indent=2), encoding="utf-8")
    payload["output_path"] = str(dest)
    payload["qa_path"] = str(qa_path)
    return payload
