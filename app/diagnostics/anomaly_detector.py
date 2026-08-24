# -*- coding: utf-8 -*-
"""Phase 7A：从 shadow QA 行判断是否值得进 Failure Memory。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.ocr.failure_class import re_search_math

# recovery 失败值得观察（未必都是系统异常）
INTERESTING_FAILURES = frozenset(
    {
        "recognition_failure",
        "extraction_failure",
        "validation_failure",
        "identity_failure",
        "alignment_failure",
        "unknown",
        "context_insufficient",
    }
)

# Gate 明确正确否决：记 failure，但 anomaly 优先级低
LOW_ANOMALY_FAILURES = frozenset({"context_strong_conflict"})


@dataclass(frozen=True)
class AnomalyAssessment:
    is_anomaly: bool
    anomaly_class: str
    actionability: str  # high | medium | low
    reason: str = ""


def assess_anomaly(row: dict[str, Any]) -> AnomalyAssessment:
    """规则化：不调用 LLM。"""
    if bool(row.get("gate_accepted")) and bool(row.get("would_replace")):
        return AnomalyAssessment(False, "", "low", "accepted")

    fc = str(row.get("failure_class") or "unknown").strip() or "unknown"
    raw = str(row.get("raw_output") or "")
    selected = str(row.get("selected_latex") or row.get("recovered") or "").strip()
    gate = str(row.get("gate_reason") or "")
    method = str(row.get("extractor_method") or "")
    salvage = bool(row.get("salvage_used"))
    mathy = re_search_math(raw)

    # 纯强冲突且 Gate 拒：recovery failure，但通常不是系统异常
    if fc == "context_strong_conflict" or "ocr_context_conflict" in gate:
        return AnomalyAssessment(
            is_anomaly=True,
            anomaly_class="ocr_bad_output",
            actionability="low",
            reason="strong_context_conflict_gate_ok",
        )

    if fc == "extraction_failure" and mathy and not selected:
        return AnomalyAssessment(
            True,
            "extractor_missed_valid_raw",
            "high",
            "raw_mathy_but_no_latex",
        )

    skip = str(row.get("skip_reason") or "")
    if skip in {"candidate_page_mismatch", "eq_order_monotonic_conflict"} or (
        skip.startswith("semantic_context_conflict")
    ):
        return AnomalyAssessment(
            True,
            "writeback_alignment_blocked",
            "high",
            skip,
        )

    if (
        selected
        and "ocr_context_conflict" not in gate
        and "ocr_still_invalid" not in gate
        and "ocr_truncated" not in gate
        and not bool(row.get("gate_accepted"))
    ):
        # 有候选式、无明显 conflict/invalid，却拒 → 可能 FN
        if "no_significant_gain" in gate or "insufficient" in gate or fc == "validation_failure":
            return AnomalyAssessment(
                True,
                "gate_false_negative",
                "high",
                "selected_cleanish_but_rejected",
            )

    if fc == "identity_failure":
        return AnomalyAssessment(True, "identity_ambiguous", "medium", fc)

    if fc == "alignment_failure":
        return AnomalyAssessment(True, "alignment_ambiguous", "medium", fc)

    if fc == "recognition_failure":
        return AnomalyAssessment(True, "ocr_bad_output", "medium", fc)

    if fc == "unknown":
        return AnomalyAssessment(True, "unexpected_pipeline_state", "high", "unknown_class")

    if fc in INTERESTING_FAILURES:
        act = "medium"
        if salvage and not selected:
            act = "high"
        return AnomalyAssessment(True, f"recovery_{fc}", act, method or fc)

    if fc in LOW_ANOMALY_FAILURES:
        return AnomalyAssessment(True, "ocr_bad_output", "low", fc)

    # 默认：未接受且非空错误 → 记一条低优先级
    if not bool(row.get("gate_accepted")):
        return AnomalyAssessment(True, "unexpected_pipeline_state", "low", fc or "reject")

    return AnomalyAssessment(False, "", "low", "skip")
