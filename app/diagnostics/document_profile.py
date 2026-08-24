# -*- coding: utf-8 -*-
"""Phase 7.1D：文档级 Recovery Profile（确定性，不改恢复行为）。"""
from __future__ import annotations

from collections import Counter
from typing import Any


def classify_document_profile(
    *,
    ocr_calls: int,
    accepted: int,
    failure_class_counts: dict[str, int] | None = None,
    ocr_inference_seconds: float = 0.0,
    model_load_seconds: float = 0.0,
    cold_start_seconds: float = 0.0,
) -> str:
    """返回 profile 标签（单标签，优先级：cold → healthy → dominated → low_yield）。"""
    fcc = {str(k): int(v) for k, v in (failure_class_counts or {}).items() if k}
    rejected = max(0, int(ocr_calls) - int(accepted))
    accept_rate = (accepted / ocr_calls) if ocr_calls else 1.0
    cold = float(cold_start_seconds or 0) or float(model_load_seconds or 0)

    if cold >= 30.0:
        return "cold_start_affected"

    if ocr_calls <= 0:
        return "no_recovery"

    if accept_rate >= 0.85 and accepted >= 1:
        return "healthy"

    # 去掉 accepted 计数后再看失败主导
    fail_counts = Counter(
        {k: v for k, v in fcc.items() if k and k != "accepted"}
    )
    if fail_counts:
        top_fc, top_n = fail_counts.most_common(1)[0]
        if top_n >= max(2, int(0.4 * rejected)) if rejected else top_n >= 2:
            if top_fc == "extraction_failure":
                return "extraction_dominated"
            if top_fc in {"context_strong_conflict", "context_insufficient"}:
                return "context_conflict_dominated"
            if top_fc == "unknown":
                return "unknown_failure_dominated"
            if top_fc in {
                "validation_failure",
                "identity_failure",
                "alignment_failure",
                "recognition_failure",
            }:
                return f"{top_fc}_dominated"

    if accept_rate < 0.35 and ocr_calls >= 6:
        return "low_yield"

    if accept_rate < 0.5 and rejected >= 3:
        return "low_yield"

    return "mixed"


def build_accept_curve(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """按执行顺序统计 accept 曲线（只观察；为 prioritization 对照预留）。

    cumulative_accept_curve[i-1] = 前 i 次 attempt 累计 accepted。
    accept_curve_auc = sum(curve) / (n * accepted)：越接近 1 表示 accept 越靠前。
    """
    curve: list[int] = []
    positions: list[int] = []
    cum = 0
    for i, r in enumerate(rows or [], start=1):
        if bool(r.get("gate_accepted")):
            cum += 1
            positions.append(i)
        curve.append(cum)
    n = len(curve)
    accepted = cum
    auc: float | None = None
    if n > 0 and accepted > 0:
        auc = round(sum(curve) / float(n * accepted), 4)
    return {
        "accept_positions": positions,
        "first_accept_attempt": positions[0] if positions else None,
        "last_accept_attempt": positions[-1] if positions else None,
        "cumulative_accept_curve": curve,
        "accept_curve_auc": auc,
    }


def build_document_recovery_profile(
    rows: list[dict[str, Any]],
    *,
    document_id: str = "",
    ocr_calls: int | None = None,
    accepted: int | None = None,
    rejected: int | None = None,
    ocr_inference_seconds: float = 0.0,
    model_load_seconds: float = 0.0,
    cold_start_seconds: float = 0.0,
    actual_seconds: float = 0.0,
) -> dict[str, Any]:
    """从 shadow would_replace 行构建文档 profile（只观察）。"""
    rows = list(rows or [])
    curve_info = build_accept_curve(rows)
    if ocr_calls is None:
        ocr_calls = len(rows)
    if accepted is None:
        accepted = sum(
            1 for r in rows if r.get("gate_accepted") and r.get("would_replace", True)
        )
        # 宽松：gate_accepted 即算
        if accepted == 0:
            accepted = sum(1 for r in rows if r.get("gate_accepted"))
    if rejected is None:
        rejected = max(0, int(ocr_calls) - int(accepted))

    fcc: Counter[str] = Counter()
    wasted_by_fc: Counter[str] = Counter()
    wasted_calls_by_fc: Counter[str] = Counter()
    high_fail = 0
    low_fail = 0
    for r in rows:
        fc = str(r.get("failure_class") or "unknown")
        fcc[fc] += 1
        timing = r.get("timing") if isinstance(r.get("timing"), dict) else {}
        ocr_s = float(
            timing.get("ocr_seconds")
            or timing.get("worker_inference_seconds")
            or r.get("ocr_seconds")
            or 0.0
        )
        if not r.get("gate_accepted"):
            wasted_by_fc[fc] += ocr_s
            wasted_calls_by_fc[fc] += 1
            act = str(r.get("actionability") or "")
            if act == "high":
                high_fail += 1
            elif act == "low":
                low_fail += 1

    cold = float(cold_start_seconds or 0.0)
    if cold < 0.05:
        cold = float(model_load_seconds or 0.0)
    infer = float(ocr_inference_seconds or 0.0)
    wall = float(actual_seconds or 0.0)
    steady = max(0.0, wall - cold) if wall else infer

    spa = (infer / accepted) if accepted else None
    cpa = (wall / accepted) if accepted and wall else (infer / accepted if accepted else None)
    opa = (ocr_calls / accepted) if accepted else None
    efficiency = (accepted / infer) if infer > 1e-6 else None

    profile = classify_document_profile(
        ocr_calls=int(ocr_calls),
        accepted=int(accepted),
        failure_class_counts=dict(fcc),
        ocr_inference_seconds=infer,
        model_load_seconds=float(model_load_seconds or 0),
        cold_start_seconds=cold,
    )

    return {
        "document": document_id,
        "attempted": int(ocr_calls),
        "accepted": int(accepted),
        "rejected": int(rejected),
        "accept_rate": round(accepted / ocr_calls, 4) if ocr_calls else None,
        "failure_class_counts": dict(fcc),
        "ocr_seconds": round(infer, 3),
        "cold_start_seconds": round(cold, 3),
        "steady_state_seconds": round(steady, 3),
        "actual_seconds": round(wall, 3) if wall else None,
        "seconds_per_accept": round(spa, 3) if spa is not None else None,
        "cost_per_recovered_formula": round(cpa, 3) if cpa is not None else None,
        "ocr_calls_per_accept": round(opa, 3) if opa is not None else None,
        "recovery_efficiency": round(efficiency, 4) if efficiency is not None else None,
        "wasted_ocr_seconds_by_class": {
            k: round(v, 3) for k, v in wasted_by_fc.most_common()
        },
        "wasted_ocr_calls_by_class": dict(wasted_calls_by_fc.most_common()),
        "high_actionability_failures": high_fail,
        "low_actionability_failures": low_fail,
        "profile": profile,
        "cold_start_affected": profile == "cold_start_affected" or cold >= 30.0,
        # Phase 7.1+：accept timing（prioritization 对照基线）
        **curve_info,
        # Phase 7.2B0：反事实预算（只观察，不真停）
        "counterfactual_budget": build_counterfactual_budget(rows),
    }


def build_counterfactual_budget(
    rows: list[dict[str, Any]],
    *,
    budgets: tuple[int, ...] = (4, 6, 8, 10),
) -> dict[str, Any]:
    """委托 ocr.prioritization，避免 document_profile ↔ ocr 循环时可内联。"""
    from app.ocr.prioritization import build_counterfactual_budget as _cf

    return _cf(rows, budgets=budgets)
