# -*- coding: utf-8 -*-
"""k3 Round-2：symbol signature gate。"""
from __future__ import annotations

from app.formula.gain import evaluate_recovery_gain
from app.formula.tokens import token_consistency
from app.formula.types import FormulaQuality


def test_markov_rth_symbol_support_not_conflict():
    ctx = (
        "The goodness of the partition encoded by H at time t under the dynamics "
        "governed by L is defined in terms of the block autocovariance matrix R(t;H). "
        "Markov Stability partition"
    )
    ocr = r"R(t;H)=H^{T}(\Pi e^{-tL}-\pi^{T}\pi)H"
    ratio, reasons = token_consistency(ctx, ocr)
    assert "ocr_context_conflict" not in reasons
    assert "symbol_signature_support" in reasons or ratio >= 0.2


def test_leap_ft_records_symbol_support():
    ctx = (
        "LEAP enforces time truncation before joins. For each instance i, let "
        "Ft(Ri) denote records available by cutoff t."
    )
    ocr = r"\mathcal{F}_{t}(\mathcal{R}_{i})=\mathcal{R}_{i}^{(\leq t)}"
    ratio, reasons = token_consistency(ctx, ocr)
    assert "ocr_context_conflict" not in reasons


def test_classification_hallucination_still_conflicts():
    ctx = "Precision and Recall for class c with macro-average F1"
    ocr = r"\omega + \hbar + sinn"
    ratio, reasons = token_consistency(ctx, ocr)
    assert "ocr_context_conflict" in reasons or ratio < 0.1


def test_markov_gain_accept_path():
    ctx = (
        "block autocovariance matrix R(t;H) where pi is the stationary solution "
        "and Markov Stability partition"
    )
    ocr = r"R(t;H)=H^{T}(\Pi e^{-tL}-\pi^{T}\pi)H"
    d = evaluate_recovery_gain(
        before_quality=FormulaQuality(corruption_score=1.0),
        after_quality=FormulaQuality(corruption_score=0.1, syntax_score=0.9, valid=True),
        before_latex="<!-- formula-not-decoded -->",
        after_latex=ocr,
        context_before=ctx,
        context_after="",
        after_valid=True,
    )
    assert "ocr_context_conflict" not in d.reasons
    assert d.accept
