# -*- coding: utf-8 -*-
from __future__ import annotations

from app.formula.config import adaptive_hard_limit_seconds, formula_config_for_deepseek_limited_production
from app.formula.equation_numbers import display_equation_number_from_latex
from app.formula.gain import evaluate_recovery_gain
from app.formula.types import FormulaQuality
from app.formula.writeback import (
    FormulaWritebackManager,
    RecoveryWritebackItem,
    resolve_multi_formula_alignment_conflicts,
    register_display_formulas_by_order,
)


def test_adaptive_hard_limit_scales_with_slots():
    assert adaptive_hard_limit_seconds(6) == 300.0
    assert adaptive_hard_limit_seconds(9) == 360.0


def test_display_equation_number_from_latex_tail():
    raw = r"VI(H,H') = ... , & & ( 8 ) \\"
    assert display_equation_number_from_latex(raw) == "8"


def test_resolve_duplicate_ocr_keeps_better_original_match():
    md = "# t\n\n$$a$$\n\n$$b$$\n"
    reg = register_display_formulas_by_order(md, ["page8_eqi8", "page8_eqi7"])
    cfg = formula_config_for_deepseek_limited_production()
    dup = r"\mathbf{p}_{t+1}=\mathbf{p}_{t}Q,"
    items = [
        RecoveryWritebackItem(
            candidate_id="page8_eqi8",
            original=r"p _ { t + 1 } = p _ { t } \, Q",
            recovered_latex=dup,
            gate_accepted=True,
            would_replace=True,
            gate_reason="gain_accept",
            page=8,
        ),
        RecoveryWritebackItem(
            candidate_id="page8_eqi7",
            original=r"\mathfrak { p } ( t ) = \mathfrak { p } ( 0 ) \, e ^ { - t l }",
            recovered_latex=dup,
            gate_accepted=True,
            would_replace=True,
            gate_reason="gain_accept",
            page=8,
        ),
    ]
    blocked = resolve_multi_formula_alignment_conflicts(items)
    assert "page8_eqi7" in blocked
    assert "page8_eqi8" not in blocked
    report = FormulaWritebackManager(cfg).apply(md, items, reg)
    assert report.applied_count == 1


def test_membership_subscript_mismatch_rejects_h_lc():
    before = r"H_{ic}=\begin{cases}1\end{cases}"
    after = r"H_{lc}=\begin{cases}1\end{cases}"
    gain = evaluate_recovery_gain(
        before_quality=FormulaQuality(corruption_score=0.9),
        after_quality=FormulaQuality(corruption_score=0.2),
        before_latex=before,
        after_latex=after,
        context_before="membership matrix",
        context_after="goodness of the partition",
        after_valid=True,
    )
    assert gain.accept
    assert "membership_subscript_mismatch" not in gain.reasons


def test_exp_original_supports_p_continuous_gate():
    before = r"w h e n \, p \quad \mathfrak { p } ( t ) = \mathfrak { p } ( 0 ) \, e ^ { - t l } ."
    after = r"\mathbf{p}(t)=\mathbf{p}(0)e^{-t\mathbf{l}}."
    gain = evaluate_recovery_gain(
        before_quality=FormulaQuality(corruption_score=0.85),
        after_quality=FormulaQuality(corruption_score=0.15),
        before_latex=before,
        after_latex=after,
        context_before="Laplacian L = D -A has the time-dependent solution:",
        context_after="The time t is denoted the Markov time",
        after_valid=True,
    )
    assert gain.accept
    assert "ocr_context_conflict" not in gain.reasons
