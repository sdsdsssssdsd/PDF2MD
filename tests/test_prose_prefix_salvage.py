# -*- coding: utf-8 -*-
from app.formula.config import FormulaConfig
from app.formula.gain import evaluate_recovery_gain
from app.formula.prose_prefix_salvage import salvage_prose_prefixed_latex
from app.formula.types import FormulaQuality


def test_reject_truncated_f1_ocr():
    before = (
        r"F 1 & = \frac { 2 \Pr e c { R e c } } { \Pr e c { + R e c } } , "
        r"\quad \Pr e c { = \frac { T P } { T P + F P } } , "
        r"\quad R e c = \frac { T P } { T P + F N } . \\"
    )
    after = r"F1 = \frac{2}{P}"
    ctx = "F1 score at threshold 0.5 precision and recall for the positive class"
    gain = evaluate_recovery_gain(
        before_quality=FormulaQuality(corruption_score=0.9, valid=False),
        after_quality=FormulaQuality(corruption_score=0.0, valid=True, syntax_score=1.0),
        before_latex=before,
        after_latex=after,
        context_before=ctx,
        context_after="",
        after_valid=True,
    )
    assert not gain.accept
    assert "classification_metrics_incomplete" in gain.reasons


def test_reject_f1_ocr_in_brier_context():
    from app.formula.gain import evaluate_recovery_gain
    from app.formula.types import FormulaQuality

    gain = evaluate_recovery_gain(
        before_quality=FormulaQuality(corruption_score=0.9, valid=False),
        after_quality=FormulaQuality(corruption_score=0.0, valid=True, syntax_score=1.0),
        before_latex=r"\text{wein} Brier = \frac{1}{n}",
        after_latex=r"F_{1} = \frac{2}{P}",
        context_before="Brier score mean squared error between outcomes and predicted probabilities",
        context_after="",
        after_valid=True,
    )
    assert not gain.accept
    assert "brier_context_conflict" in gain.reasons
