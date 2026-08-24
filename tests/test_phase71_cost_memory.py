# -*- coding: utf-8 -*-
"""Phase 7.1：Cost-Aware Failure Memory / document profile。"""
from __future__ import annotations

from pathlib import Path

from app.diagnostics.document_profile import (
    build_document_recovery_profile,
    classify_document_profile,
)
from app.diagnostics.failure_memory import FailureMemory, record_shadow_failures


def test_classify_profiles():
    assert (
        classify_document_profile(
            ocr_calls=7, accepted=7, failure_class_counts={"accepted": 7}
        )
        == "healthy"
    )
    assert (
        classify_document_profile(
            ocr_calls=13,
            accepted=3,
            failure_class_counts={"extraction_failure": 6, "context_strong_conflict": 4},
            ocr_inference_seconds=93,
        )
        == "extraction_dominated"
    )
    assert (
        classify_document_profile(
            ocr_calls=8,
            accepted=3,
            cold_start_seconds=210,
            failure_class_counts={"accepted": 3},
        )
        == "cold_start_affected"
    )


def test_document_profile_seconds_per_accept():
    rows = [
        {
            "gate_accepted": True,
            "would_replace": True,
            "failure_class": "accepted",
            "timing": {"ocr_seconds": 5.0},
        },
        {
            "gate_accepted": False,
            "failure_class": "extraction_failure",
            "actionability": "high",
            "timing": {"ocr_seconds": 7.0},
        },
        {
            "gate_accepted": False,
            "failure_class": "extraction_failure",
            "actionability": "high",
            "timing": {"ocr_seconds": 7.0},
        },
    ]
    p = build_document_recovery_profile(
        rows,
        document_id="O-003",
        ocr_calls=3,
        accepted=1,
        rejected=2,
        ocr_inference_seconds=19.0,
        actual_seconds=19.0,
    )
    assert p["seconds_per_accept"] == 19.0
    assert p["profile"] == "extraction_dominated"
    assert p["wasted_ocr_seconds_by_class"]["extraction_failure"] == 14.0
    assert p["attempted"] == 3
    assert p["accepted"] == 1
    assert p["rejected"] == 2


def test_failure_memory_cost_aggregation(tmp_path: Path):
    mem = FailureMemory(root=tmp_path / "fm")
    row = {
        "gate_accepted": False,
        "failure_class": "extraction_failure",
        "gate_reason": "no_equation_blocks",
        "original": "x",
        "raw_output": r"\frac{a}{b}",
        "selected_latex": "",
        "extractor_method": "none",
        "ocr_seconds": 7.3,
        "recovery_seconds": 7.6,
        "cold_start_seconds": 0,
        "timing": {"ocr_seconds": 7.3},
    }
    r1 = record_shadow_failures([row], run_id="A", document_id="O-003", memory=mem)
    r2 = record_shadow_failures([row], run_id="B", document_id="O-003", memory=mem)
    assert r1["recorded"] == 1 and r2["recorded"] == 1
    assert r2["top_costly_failures"]
    top = r2["top_costly_failures"][0]
    assert float(top["total_ocr_seconds"]) >= 14.0
    assert "extraction_failure" in (r2["wasted_ocr_seconds_by_class"] or {})


def test_accepted_uses_attempted_accepted_rejected_schema():
    p = build_document_recovery_profile(
        [],
        document_id="O-018",
        ocr_calls=7,
        accepted=7,
        rejected=0,
        ocr_inference_seconds=39.0,
        actual_seconds=39.5,
    )
    assert p["attempted"] == 7
    assert p["accepted"] == 7
    assert p["rejected"] == 0
    assert p["accept_rate"] == 1.0
    assert p["seconds_per_accept"] == round(39.0 / 7, 3)


def test_accept_curve_late_vs_early():
    # 晚接受：[4,8,12] → AUC 较低
    late = [
        {"gate_accepted": i in {4, 8, 12}} for i in range(1, 14)
    ]
    p_late = build_document_recovery_profile(late, document_id="O-003")
    assert p_late["accept_positions"] == [4, 8, 12]
    assert p_late["first_accept_attempt"] == 4
    assert p_late["last_accept_attempt"] == 12
    assert p_late["cumulative_accept_curve"][0] == 0
    assert p_late["cumulative_accept_curve"][3] == 1
    assert p_late["cumulative_accept_curve"][-1] == 3

    # 早接受：[1,2,4] → AUC 更高
    early = [
        {"gate_accepted": i in {1, 2, 4}} for i in range(1, 14)
    ]
    p_early = build_document_recovery_profile(early, document_id="O-003b")
    assert p_early["accept_positions"] == [1, 2, 4]
    assert p_early["first_accept_attempt"] == 1
    assert float(p_early["accept_curve_auc"]) > float(p_late["accept_curve_auc"])
