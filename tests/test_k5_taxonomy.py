# -*- coding: utf-8 -*-
from __future__ import annotations

from app.ocr.k5_taxonomy import (
    classify_crop_vs_ocr,
    pred_looks_contaminated,
    simulate_shadow_writeback,
    summarize_shadow,
)


def test_tight_ok_prod_fail_is_crop():
    prod, tight = classify_crop_vs_ocr(
        exact_prod=False,
        exact_tight=True,
        prod_pred=r"\begin{array}{r}TPR ... FPR",
        tight_pred=r"FPR=\frac{FP}{FP+TN}",
    )
    assert prod == "CROP_CLIPPED"
    assert tight == "OK"


def test_both_fail_contaminated_prod():
    prod, tight = classify_crop_vs_ocr(
        exact_prod=False,
        exact_tight=False,
        prod_pred=r"the model \hat{f} can be expressed by Eq.(1)",
        tight_pred=r"E[(\mathcal{Y}-\hat{f})^2]=Bias^2+V+\varepsilon",
    )
    assert prod == "CROP_CLIPPED"
    assert tight == "OCR_FAILURE"


def test_contaminated_heuristic():
    assert pred_looks_contaminated(r"\begin{array}{ll}identified.Recall")
    assert not pred_looks_contaminated(r"FPR=\frac{FP}{FP+TN}")


def test_shadow_consensus_accept_is_true_accept():
    s = simulate_shadow_writeback(
        r"\mathrm{FPR}=\frac{\mathrm{FP}}{\mathrm{FP}+\mathrm{TN}}\tag{7}",
        r"FPR=\frac{FP}{FP+TN}",
        r"FPR=\frac{FP}{FP+TN}",
    )
    assert s.decision == "accept"
    assert s.outcome == "true_accept"


def test_shadow_hat_vs_widehat_abstains():
    s = simulate_shadow_writeback(
        r"E\left[\left(\mathcal{Y}-\hat{f}\right)^{2}\right]=Bias^{2}+V+\varepsilon",
        r"E\left[\left(\mathcal{Y}-\widehat{f}\right)^{2}\right]=Bias^{2}+V+\varepsilon",
        r"E[(y-\hat{f})^2]=Bias^2+Var+\varepsilon",
    )
    assert s.decision == "abstain"
    assert s.outcome == "abstain_correct"
    assert s.gold_exact is False


def test_shadow_agreeing_wrong_is_false_accept():
    wrong = r"E[(\mathcal{Y}-\hat{f})^2]=Bias^2+V+\varepsilon"
    s = simulate_shadow_writeback(
        wrong,
        wrong,
        r"E[(y-\hat{f})^2]=Bias^2+Var+\varepsilon",
    )
    assert s.decision == "accept"
    assert s.outcome == "false_accept"


def test_shadow_summary_precision():
    rows = [
        simulate_shadow_writeback(r"a=1", r"a=1", r"a=1"),
        simulate_shadow_writeback(r"x_i", r"x_l", r"x_i"),
    ]
    sm = summarize_shadow(rows)
    assert sm["auto_accept"] == 1
    assert sm["false_accept"] == 0
    assert sm["precision"] == 1.0
    assert sm["coverage"] == 0.5
