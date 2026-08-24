# -*- coding: utf-8 -*-
"""O-028：占位符上下文 / 假编号 / macro metric Gate 回归。"""
from __future__ import annotations

import re

from app.formula.equation_identity import meaningful_context_window
from app.formula.gain import evaluate_recovery_gain
from app.formula.tokens import sanitize_recovery_context, token_consistency
from app.formula.types import FormulaCandidate, FormulaQuality
from app.ocr.prioritization import NUM_NON_EQ, classify_equation_number_plausibility


def test_equation_index_zero_is_non_eq():
    cand = FormulaCandidate(
        text="<!-- formula-not-decoded -->",
        page=16,
        equation_number="0",
        context_before="(0)",
    )
    plaus = classify_equation_number_plausibility(cand)
    assert plaus["class"] == NUM_NON_EQ
    assert "equation_index_zero" in plaus["reasons"]


def test_sanitize_recovery_context_strips_placeholders():
    raw = (
        "<!-- formula-not-decoded -->\n"
        "Macro-average metric:\n"
        "<!-- formula-not-decoded -->"
    )
    clean = sanitize_recovery_context(raw)
    assert "formula-not-decoded" not in clean
    assert "Macro-average" in clean


def test_meaningful_context_skips_placeholder_stack():
    md = (
        "Intro paragraph about models.\n\n"
        "<!-- formula-not-decoded -->\n\n"
        "<!-- formula-not-decoded -->\n\n"
        "Macro-average metric:\n\n"
        "<!-- formula-not-decoded -->"
    )
    pos = list(re.finditer(r"<!-- formula-not-decoded -->", md))[-1].start()
    ctx = meaningful_context_window(md, pos, before=True)
    assert "Macro-average" in ctx
    assert "formula-not-decoded" not in ctx


def test_macro_metric_formula_not_killed_by_placeholder_context():
    ctx = (
        "<!-- formula-not-decoded -->\n"
        "Macro-average metric:\n"
        "<!-- formula-not-decoded -->"
    )
    ratio, reasons = token_consistency(
        sanitize_recovery_context(ctx),
        r"M_{\mathrm{macro}}=\frac{1}{C}\sum_{c=1}^{C} P_c",
    )
    assert "ocr_context_conflict" not in reasons
    assert ratio > 0


def test_gain_accepts_macro_metric_after_context_sanitize():
    ctx = (
        "<!-- formula-not-decoded -->\n"
        "Macro-average metric:\n"
        "<!-- formula-not-decoded -->"
    )
    d = evaluate_recovery_gain(
        before_quality=FormulaQuality(corruption_score=0.95, valid=False),
        after_quality=FormulaQuality(corruption_score=0.05, valid=True, syntax_score=1.0),
        before_latex="",
        after_latex=r"M_{\mathrm{macro}}=\frac{1}{C}\sum_{c=1}^{C} P_c",
        context_before=ctx,
        context_after="",
        after_valid=True,
    )
    assert "ocr_context_conflict" not in d.reasons
    assert d.accept is True
