# -*- coding: utf-8 -*-
from __future__ import annotations

from app.formula.gain import evaluate_recovery_gain
from app.formula.tokens import operator_direction_conflict, token_consistency
from app.formula.types import FormulaQuality


def test_max_context_min_ocr_conflicts_without_original():
    ctx = "we maximise r*(t) by searching arg max over partitions H"
    ocr = r"r(t,H)=\min_{r\in\mathcal{T}}\operatorname{Tr}\left[R(\tau,H)\right]"
    conflict, reasons = operator_direction_conflict(ctx, ocr)
    assert conflict
    assert "operator_direction_conflict" in reasons


def test_original_min_allows_min_ocr_despite_max_context():
    ctx = "which is to be maximised at every time t"
    ocr = r"r(t,H)=\min_{r<t}\operatorname{Tr}\left[R(\tau,H)\right]"
    orig = r"r(t,H)=\min_{t}\mathrm{Tr}\left[R(\tau,H)\right]"
    conflict, _ = operator_direction_conflict(ctx, ocr, original_latex=orig)
    assert not conflict


def test_max_context_min_ocr_conflicts():
    ctx = "we maximise r*(t) by searching arg max over partitions H"
    ocr = r"r(t,H)=\min_{r\in\mathcal{T}}\operatorname{Tr}\left[R(\tau,H)\right]"
    orig = r"r^{*}(t)=\max_{H} r(t,H)"
    conflict, reasons = operator_direction_conflict(ctx, ocr, original_latex=orig)
    assert conflict
    assert "operator_direction_conflict" in reasons
    d = evaluate_recovery_gain(
        before_quality=FormulaQuality(corruption_score=1.0, valid=False),
        after_quality=FormulaQuality(corruption_score=0.1, syntax_score=0.9, valid=True),
        before_latex=orig,
        after_latex=ocr,
        context_before=ctx,
        context_after="",
        after_valid=True,
    )
    assert not d.accept
    assert "ocr_context_conflict" in d.reasons


def test_markov_rth_still_accepts():
    ctx = "block autocovariance R(t;H) Markov Stability partition pi"
    ocr = r"R(t;H)=H^{T}(\Pi e^{-tL}-\pi^{T}\pi)H"
    conflict, _ = operator_direction_conflict(ctx, ocr)
    assert not conflict
