# -*- coding: utf-8 -*-
"""Phase 7A：Failure Memory 收集 / fingerprint 去重。"""
from __future__ import annotations

from pathlib import Path

from app.diagnostics.anomaly_detector import assess_anomaly
from app.diagnostics.failure_memory import (
    FailureMemory,
    fingerprint_parts,
    record_shadow_failures,
)


def test_fingerprint_stable(tmp_path: Path):
    a = fingerprint_parts(
        failure_class="extraction_failure",
        gate_reason="no_equation_blocks",
        original=r"\quad garbage",
        raw_output=r"\frac{a}{b}=c",
        extractor_method="none",
        anomaly_class="extractor_missed_valid_raw",
    )
    b = fingerprint_parts(
        failure_class="extraction_failure",
        gate_reason="no_equation_blocks",
        original=r"\quad   garbage",
        raw_output=r"\frac{a}{b}=c",
        extractor_method="none",
        anomaly_class="extractor_missed_valid_raw",
    )
    assert a == b
    assert a.startswith("sha256:")


def test_dedupe_increments_occurrence(tmp_path: Path):
    mem = FailureMemory(root=tmp_path / "fm")
    row = {
        "gate_accepted": False,
        "would_replace": False,
        "failure_class": "extraction_failure",
        "gate_reason": "no_equation_blocks",
        "original": "garbage",
        "raw_output": r"F(x)=x^{2}",
        "selected_latex": "",
        "extractor_method": "none",
        "salvage_used": False,
        "candidate_id": "p1_eq1",
        "page": 1,
        "eq_number": "1",
    }
    r1 = record_shadow_failures(
        [row], run_id="runA", document_id="O-003", memory=mem
    )
    r2 = record_shadow_failures(
        [row], run_id="runB", document_id="O-003", memory=mem
    )
    assert r1["recorded"] == 1
    assert r2["recorded"] == 1
    idx = mem._load_index()
    assert len(idx) == 1
    meta = next(iter(idx.values()))
    assert int(meta["occurrence_count"]) == 2
    assert "runA" in meta["runs_seen"] and "runB" in meta["runs_seen"]
    summary = mem.rebuild_summary()
    assert summary["unique_fingerprints"] == 1
    assert summary["repeated_anomalies"] == 1
    assert mem.events_path.is_file()
    lines = [ln for ln in mem.events_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2


def test_strong_conflict_low_actionability():
    a = assess_anomaly(
        {
            "gate_accepted": False,
            "failure_class": "context_strong_conflict",
            "gate_reason": "ocr_context_conflict",
            "raw_output": "TPR=...",
            "selected_latex": "TPR=...",
        }
    )
    assert a.is_anomaly is True
    assert a.actionability == "low"


def test_extraction_miss_high_actionability():
    a = assess_anomaly(
        {
            "gate_accepted": False,
            "failure_class": "extraction_failure",
            "gate_reason": "no_equation_blocks",
            "raw_output": r"\mathrm{TPR}=\frac{TP}{TP+FN}",
            "selected_latex": "",
            "extractor_method": "none",
        }
    )
    assert a.anomaly_class == "extractor_missed_valid_raw"
    assert a.actionability == "high"


def test_accepted_not_recorded(tmp_path: Path):
    mem = FailureMemory(root=tmp_path / "fm2")
    r = record_shadow_failures(
        [
            {
                "gate_accepted": True,
                "would_replace": True,
                "failure_class": "accepted",
                "raw_output": "x=1",
                "recovered": "x=1",
            }
        ],
        document_id="O-018",
        memory=mem,
    )
    assert r["recorded"] == 0
    assert r["skipped"] == 1
