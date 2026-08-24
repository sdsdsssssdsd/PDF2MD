# -*- coding: utf-8 -*-
"""Phase 6：OCR utilization — crop extract / salvage / failure class / context v2。"""
from __future__ import annotations

from app.formula.gain import evaluate_recovery_gain
from app.formula.tokens import token_consistency
from app.formula.types import FormulaQuality
from app.ocr.failure_class import (
    RecoveryFailureClass,
    classify_recovery_failure,
    recovery_yield,
)
from app.ocr.formula_crop_extract import extract_formula_crop, salvage_formula_from_raw


def test_salvage_plain_latex_no_dollars():
    raw = r"\mathrm{TPR}=\frac{\mathrm{TP}}{\mathrm{TP}+\mathrm{FN}}"
    er = salvage_formula_from_raw(raw)
    assert er.latex
    assert "TPR" in er.latex
    assert er.method.startswith("formula_crop")


def test_salvage_prose_wrapped():
    raw = "The formula is:\n\\[\nF(x)=x^2\n\\]\n"
    er = salvage_formula_from_raw(raw)
    assert "F(x)" in er.latex or "x^2" in er.latex


def test_formula_crop_ignores_missing_eq_number():
    # OCR 未带 (6)，但 crop 已是目标式
    raw = r"$$\mathrm{TPR}=\frac{\mathrm{TP}}{\mathrm{TP}+\mathrm{FN}}$$"
    er = extract_formula_crop(raw, eq_number="6")
    assert er.latex
    assert "TPR" in er.latex
    assert er.failure_reason == ""


def test_no_matching_becomes_best_block():
    raw = (
        r"$$A=1$$"
        "\n"
        r"$$\mathrm{FPR}=\frac{\mathrm{FP}}{\mathrm{FP}+\mathrm{TN}}$$"
    )
    er = extract_formula_crop(raw, eq_number="99")
    assert er.latex
    # 不应再因 no_matching_equation_block 空手离开
    assert er.failure_reason != "no_matching_equation_block"


def test_strong_conflict_still_hard_veto():
    ratio, reasons = token_consistency(
        "False Positive Rate (FPR) using Eq. (7)",
        r"E[(y-\hat{f})^{2}]=Bias^{2}+V+\varepsilon",
    )
    assert "ocr_context_conflict" in reasons
    assert ratio == 0.0


def test_insufficient_context_not_conflict():
    ratio, reasons = token_consistency(
        "The metric is defined as follows:",
        r"F_{1}=2\times\frac{P\times R}{P+R}",
    )
    assert "ocr_context_conflict" not in reasons
    assert "ocr_context_insufficient" in reasons or ratio > 0


def test_gain_accepts_insufficient_with_clean_latex():
    d = evaluate_recovery_gain(
        before_quality=FormulaQuality(corruption_score=0.95, valid=False),
        after_quality=FormulaQuality(corruption_score=0.05, valid=True, syntax_score=1.0),
        before_latex=r"\quad garbage",
        after_latex=r"F_{1}=2\times\frac{P\times R}{P+R}",
        context_before="The metric is defined as follows:",
        context_after="",
        after_valid=True,
    )
    assert d.accept is True
    assert "ocr_context_conflict" not in d.reasons


def test_failure_class_extraction():
    fc = classify_recovery_failure(
        gate_accepted=False,
        error="no_equation_blocks",
        raw_output=r"\frac{a}{b}=c",
        selected_latex="",
    )
    assert fc == RecoveryFailureClass.EXTRACTION_FAILURE


def test_recovery_yield_metric():
    assert recovery_yield(ocr_calls=13, accepted=4) == 0.3077
    assert recovery_yield(ocr_calls=0, accepted=0) is None
