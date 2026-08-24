# -*- coding: utf-8 -*-
"""Phase 7：Failure Memory / Anomaly 检测（只观察，不改 OCR/Gate）。"""
from __future__ import annotations

from app.diagnostics.anomaly_detector import (
    AnomalyAssessment,
    assess_anomaly,
)
from app.diagnostics.document_profile import (
    build_accept_curve,
    build_document_recovery_profile,
    classify_document_profile,
)
from app.diagnostics.failure_memory import (
    FailureMemory,
    default_failure_memory_root,
    record_shadow_failures,
)

__all__ = [
    "AnomalyAssessment",
    "FailureMemory",
    "assess_anomaly",
    "build_accept_curve",
    "build_document_recovery_profile",
    "classify_document_profile",
    "default_failure_memory_root",
    "record_shadow_failures",
]
