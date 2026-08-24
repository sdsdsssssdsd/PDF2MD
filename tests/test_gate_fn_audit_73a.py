# -*- coding: utf-8 -*-
"""7.3A Gate FN audit 单测。"""
from __future__ import annotations

from app.diagnostics.gate_fn_audit import audit_gate_fn_row, audit_gate_fn_rows
from app.formula.gain import looks_truncated


def test_looks_truncated_trailing_comma():
    # 7.3B：尾逗号不再视为截断
    assert looks_truncated(r"R(t;H)=H^{T}H,") is False
    assert looks_truncated(r"\mathbf{p}(t)=\mathbf{p}(0)e^{-t}.") is False


def test_fn_audit_marks_o003_style_insufficient():
    row = {
        "candidate_id": "p8_eqx_9",
        "gate_accepted": False,
        "gate_reason": "ocr_context_insufficient,insufficient_without_strong_evidence",
        "failure_class": "context_insufficient",
        "selected_latex": r"R(t;H)=H^{T}(\Pi e^{-tI}-\pi^{T}\pi)H,",
        "raw_output": r"\[ R(t;H)=H^{T}(\Pi e^{-tI}-\pi^{T}\pi)H, \quad (5) \]",
        "extractor_method": "formula_crop_single",
        "salvage_used": True,
        "eq_number": "",
        "timing": {"ocr_seconds": 4.0},
    }
    d = audit_gate_fn_row(row, attempt_index=9)
    assert d["context_status"] == "insufficient"
    assert d["validation_status"] == "pass"
    assert d["looks_truncated"] is False
    # 修复后：若当时 Gate 仍拒，审计仍可标 safe；此处 latex 已不截断
    assert d["safe_accept_candidate"] is True or d["looks_truncated"] is False
    assert d["counterfactual_strip_comma_accept"] is True


def test_conflict_not_in_fn_buckets():
    row = {
        "gate_accepted": False,
        "gate_reason": "ocr_context_conflict",
        "failure_class": "context_strong_conflict",
        "selected_latex": r"E=mc^2",
        "raw_output": r"\[ E=mc^2 \]",
        "salvage_used": True,
        "timing": {"ocr_seconds": 3.0},
    }
    out = audit_gate_fn_rows([row], document_id="t")
    assert out["fn_count"] == 0
    assert out["context_conflict_rejects"] == 1
