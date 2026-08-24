# -*- coding: utf-8 -*-
from app.formula.classification_metrics_salvage import salvage_classification_metrics_latex
from app.formula.prose_prefix_salvage import salvage_prose_prefixed_latex


def test_salvage_o024_brier_prose_prefix():
    raw = (
        r"\text {wein out comes and predicted probabinities} \, [ 9 ] \colon \\ "
        r"\text {Brier} \, = \, \frac { 1 } { n } \sum _ { i = 1 } ^ { n } "
        r"( y _ { i } - \hat { p } _ { i } ) ^ { 2 } ."
    )
    ctx = "Brier score mean squared error between outcomes and predicted probabilities"
    out = salvage_prose_prefixed_latex(raw, context_before=ctx)
    assert out is not None
    assert "wein" not in out.lower()
    assert r"\frac{1}{n}" in out.replace(" ", "")


def test_salvage_o024_f1_classification_metrics():
    raw = (
        r"F 1 & = \frac { 2 \Pr e c { R e c } } { \Pr e c { + R e c } } , "
        r"\quad \Pr e c { = \frac { T P } { T P + F P } } , "
        r"\quad R e c = \frac { T P } { T P + F N } . \\"
    )
    ctx = (
        "Fixed-threshold performance: we report the F1 score at threshold 0.5 (F1@0.5), "
        "which balances precision and recall for the positive class."
    )
    out = salvage_classification_metrics_latex(raw, context_before=ctx)
    assert out is not None
    assert "TP" in out and "FP" in out and "FN" in out
    assert r"\mathrm{Prec}" in out and r"\mathrm{Rec}" in out
    assert "2" in out and "cdot" in out
