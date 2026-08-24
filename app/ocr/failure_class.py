# -*- coding: utf-8 -*-
"""Phase 6A：Recovery 失败归因（不重新 OCR）。"""
from __future__ import annotations

from enum import Enum
from typing import Any


class RecoveryFailureClass(str, Enum):
    RECOGNITION_FAILURE = "recognition_failure"
    EXTRACTION_FAILURE = "extraction_failure"
    VALIDATION_FAILURE = "validation_failure"
    IDENTITY_FAILURE = "identity_failure"
    ALIGNMENT_FAILURE = "alignment_failure"
    CONTEXT_STRONG_CONFLICT = "context_strong_conflict"
    CONTEXT_INSUFFICIENT = "context_insufficient"
    ACCEPTED = "accepted"
    UNKNOWN = "unknown"


_EXTRACT_MARKERS = {
    "no_equation_blocks",
    "no_matching_equation_block",
    "formula_not_found_in_ocr",
    "empty",
}
_VALIDATE_MARKERS = {
    "ocr_still_invalid",
    "ocr_truncated",
    "no_significant_gain",
    "latex_invalid",
    "high_corruption",
}
_IDENTITY_MARKERS = {
    "identity_content_conflict",
    "identity_unresolved",
}
_ALIGN_MARKERS = {
    "multi_formula_alignment_ambiguous",
}


def classify_recovery_failure(
    *,
    gate_accepted: bool = False,
    gate_reason: str = "",
    error: str = "",
    extractor_method: str = "",
    raw_output: str = "",
    selected_latex: str = "",
) -> RecoveryFailureClass:
    if gate_accepted and (selected_latex or "").strip():
        return RecoveryFailureClass.ACCEPTED

    blob = f"{gate_reason or ''},{error or ''},{extractor_method or ''}".lower()
    parts = {p.strip() for p in blob.replace("|", ",").split(",") if p.strip()}

    if "ocr_context_conflict" in parts or "strong_conflict" in blob:
        return RecoveryFailureClass.CONTEXT_STRONG_CONFLICT
    if "ocr_context_insufficient" in parts or "weak_mismatch" in blob:
        return RecoveryFailureClass.CONTEXT_INSUFFICIENT

    if parts & _IDENTITY_MARKERS or "identity" in blob:
        return RecoveryFailureClass.IDENTITY_FAILURE
    if parts & _ALIGN_MARKERS:
        return RecoveryFailureClass.ALIGNMENT_FAILURE

    if parts & _EXTRACT_MARKERS or extractor_method in {"none", ""}:
        # raw 里其实有数学痕迹 → 提取失败；完全空/乱码 → 识别失败
        raw = (raw_output or "").strip()
        if raw and _raw_looks_mathy(raw) and not (selected_latex or "").strip():
            return RecoveryFailureClass.EXTRACTION_FAILURE
        if not raw or len(raw) < 3:
            return RecoveryFailureClass.RECOGNITION_FAILURE
        if parts & _EXTRACT_MARKERS:
            return RecoveryFailureClass.EXTRACTION_FAILURE

    if parts & _VALIDATE_MARKERS:
        return RecoveryFailureClass.VALIDATION_FAILURE

    if "timeout" in blob or "ocr_timeout" in blob or "worker_session" in blob:
        return RecoveryFailureClass.RECOGNITION_FAILURE

    return RecoveryFailureClass.UNKNOWN


def _raw_looks_mathy(raw: str) -> bool:
    t = raw or ""
    if re_search_math(t):
        return True
    return False


def re_search_math(t: str) -> bool:
    import re

    return bool(
        re.search(
            r"[=\\^_{}]|\\frac|\\times|\\left|\\mathrm|\\begin|\$\$|\\\(|\\\[|"
            r"(?<![A-Za-z])(?:TP|FP|FN|TN|TPR|FPR|MSE|Bias)(?![A-Za-z])",
            t,
        )
    )


def recovery_yield(*, ocr_calls: int, accepted: int) -> float | None:
    if ocr_calls <= 0:
        return None
    return round(float(accepted) / float(ocr_calls), 4)


def attribute_row(row: dict[str, Any]) -> dict[str, Any]:
    """给 shadow/writeback 行附加 failure_class。"""
    fc = classify_recovery_failure(
        gate_accepted=bool(row.get("gate_accepted")),
        gate_reason=str(row.get("gate_reason") or ""),
        error=str(row.get("error") or ""),
        extractor_method=str(row.get("extractor_method") or ""),
        raw_output=str(row.get("raw_output") or row.get("original") or ""),
        selected_latex=str(row.get("selected_latex") or row.get("recovered") or ""),
    )
    out = dict(row)
    out["failure_class"] = fc.value
    return out
