# -*- coding: utf-8 -*-
from __future__ import annotations

from app.formula.gain import evaluate_recovery_gain
from app.formula.spaced_letter_salvage import salvage_spaced_letter_latex
from app.formula.types import FormulaQuality
from app.formula.validator import validate_latex
from app.formula.config import FormulaConfig


def test_salvage_o028_f1():
    raw = (
        r"F 1 _ { c } = \frac { 2 \cdot \Pr e c i s i o _ { c } \cdot \Re c a l l _ { c } }"
        r" { \Pr e c i s i o _ { c } + \Re c a l l _ { c } } ."
    )
    out = salvage_spaced_letter_latex(raw)
    assert out
    assert "F1_" in out or "F1{" in out


def test_salvage_course_level_zscore_gate():
    before = r"z = ( x - \mu ) / \sigma & & ( 1 ) & & \stackrel { 1 2 } { \ s t }"
    after = salvage_spaced_letter_latex(before) or r"z=(x-\mu)/\sigma"
    cfg = FormulaConfig()
    vr = validate_latex(after, cfg)
    gain = evaluate_recovery_gain(
        before_quality=FormulaQuality(corruption_score=0.85),
        after_quality=vr.quality,
        before_latex=before,
        after_latex=after,
        context_before="remained comparable:",
        context_after="This approach transforms each numeric feature",
        after_valid=bool(vr.valid),
    )
    assert gain.accept
    assert "ocr_context_conflict" not in gain.reasons


def test_salvage_rejects_clean_original():
    raw = r"E=mc^2"
    assert salvage_spaced_letter_latex(raw) is None
