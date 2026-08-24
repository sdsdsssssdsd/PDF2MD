# -*- coding: utf-8 -*-
"""7.3B：looks_truncated 窄修 + insufficient 放行。"""
from __future__ import annotations

from app.formula.gain import evaluate_recovery_gain, looks_truncated
from app.formula.types import FormulaQuality
from app.formula.validator import validate_latex


def test_trailing_comma_not_truncated():
    assert looks_truncated(r"R(t;H)=H^{T}(\Pi e^{-tI}-\pi^{T}\pi)H,") is False
    assert looks_truncated(r"\mathbf{p}(t)=\mathbf{p}(0)e^{-t}.") is False


def test_left_brace_cases_not_truncated():
    latex = (
        r"H_{lc}=\left\{\begin{aligned}&1&if node i belongs to community c\\"
        r"&0&otherwise\end{aligned}\right."
    )
    assert looks_truncated(latex) is False


def test_real_truncation_still_detected():
    assert looks_truncated(r"Recall = \frac{TP}{TP+") is True
    assert looks_truncated(r"E=mc^2+") is True
    assert looks_truncated(r"\frac{a}{b") is True


def test_o003_style_insufficient_now_accepts():
    """#9/#10 风格：insufficient + clean → accept；conflict 仍拒。"""
    before = FormulaQuality(corruption_score=0.95, valid=False)
    prose = "see clustering details in the text."

    for latex in (
        r"R(t;H)=H^{T}(\Pi e^{-tI}-\pi^{T}\pi)H,",
        r"H_{lc}=\left\{\begin{aligned}&1&if node i belongs to community c\\"
        r"&0&otherwise\end{aligned}\right.",
    ):
        vr = validate_latex(latex)
        d = evaluate_recovery_gain(
            before_quality=before,
            after_quality=vr.quality,
            before_latex="<!-- formula-not-decoded -->",
            after_latex=latex,
            context_before=prose,
            context_after="",
            after_valid=bool(vr.valid),
        )
        assert d.accept, (latex[:40], d.reasons)
        assert "accept_despite_insufficient_context" in d.reasons

    # conflict 硬拒不变
    d_bad = evaluate_recovery_gain(
        before_quality=before,
        after_quality=FormulaQuality(corruption_score=0.0, valid=True, syntax_score=1.0),
        before_latex=r"\quad",
        after_latex=r"E=mc^2",
        context_before="The expected MSE is Bias-Variance:",
        context_after="",
        after_valid=True,
    )
    assert not d_bad.accept
    assert "ocr_context_conflict" in d_bad.reasons
