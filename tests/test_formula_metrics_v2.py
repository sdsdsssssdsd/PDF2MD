# -*- coding: utf-8 -*-
from __future__ import annotations

from app.formula.gold_schema import validate_gold_record
from app.ocr.match_eval import FormulaMatchEvaluator
from app.ocr.match_eval_v2 import (
    FormulaMatchEvaluatorV2,
    canonicalize_latex,
    classify_production_failure,
    compile_rate_ok,
    token_edit_distance,
)


def test_strict_exact_rejects_substring():
    gold = r"\frac{a}{b}"
    cand = r"\frac{a}{b} + extra"
    legacy = FormulaMatchEvaluator().compare(cand, gold)
    v2 = FormulaMatchEvaluatorV2(compute_cdm=False).compare(cand, gold)
    assert legacy.exact_normalized_match is True
    assert v2.strict_canonical_exact is False
    assert v2.legacy_exact_substring is True


def test_strict_exact_accepts_canonical_equal():
    gold = r"$$\frac{a}{b}$$"
    cand = r"\dfrac{a}{b}"
    v2 = FormulaMatchEvaluatorV2(compute_cdm=False).compare(cand, gold)
    assert canonicalize_latex(gold) == canonicalize_latex(cand)
    assert v2.strict_canonical_exact is True
    assert v2.compile_ok is True


def test_token_edit_distance_zero_on_same():
    assert token_edit_distance(r"x_i", r"x_i") == 0
    assert token_edit_distance(r"x_i", r"x_l") >= 1


def test_compile_rate_detects_unbalanced():
    assert compile_rate_ok(r"\frac{a}{b}") is True
    assert compile_rate_ok(r"\frac{a{b}") is False


def test_failure_layer_gate_false_accept():
    assert (
        classify_production_failure(
            ocr_ok=True,
            exact=False,
            gate_accepted=True,
            gold_correct=False,
        )
        == "GATE_FALSE_ACCEPT"
    )


def test_array_colspec_not_left_in_canonical():
    gold = r"FPR=\frac{FP}{FP+TN}"
    cand = r"\begin{array}{r}{\mathrm{FPR}=\frac{\mathrm{FP}}{\mathrm{FP}+\mathrm{TN}}\quad(7).}\end{array}"
    assert canonicalize_latex(cand) == canonicalize_latex(gold)


def test_mathrm_and_tag_are_style_not_mismatch():
    gold = r"FPR=\frac{FP}{FP+TN}"
    cand = r"\mathrm{FPR}=\frac{\mathrm{FP}}{\mathrm{FP}+\mathrm{TN}}\tag{7}"
    v2 = FormulaMatchEvaluatorV2(compute_cdm=False).compare(cand, gold)
    assert canonicalize_latex(cand) == canonicalize_latex(gold)
    assert v2.strict_canonical_exact is True


def test_trailing_paren_eqnum_stripped_when_equation():
    gold = r"Recall=\frac{TP}{TP+FN}"
    cand = r"Recall=\frac{TP}{TP+FN}\quad(4)"
    assert canonicalize_latex(cand) == canonicalize_latex(gold)
    assert FormulaMatchEvaluatorV2(compute_cdm=False).compare(cand, gold).strict_canonical_exact
    dotted = r"\mathrm{T P R}=\frac{\mathrm{T P}}{\mathrm{T P}+\mathrm{F N}}\quad(6)."
    assert canonicalize_latex(dotted) == canonicalize_latex(r"TPR=\frac{TP}{TP+FN}")
    eqno = r"E[(y-\hat{f})^2]=Bias^2+V+\varepsilon\eqno(1)"
    assert "(1)" not in canonicalize_latex(eqno)


def test_p0_call_not_stripped_as_eqnum():
    gold = r"P(0)"
    assert canonicalize_latex(gold) == "P(0)"
    assert canonicalize_latex(r"P(0)") == canonicalize_latex(gold)


def test_trailing_comma_is_style():
    gold = r"k_{l}(x,y)=e^{-D_{l}(x,y)/\sigma^{2}}"
    cand = r"k_{l}(x,y)=e^{-D_{l}(x,y)/\sigma^{2}},"
    assert canonicalize_latex(cand) == canonicalize_latex(gold)


def test_no_semantic_alias_fold():
    """Var≠V、mathcal Y≠y：这是内容差异，不是样式。"""
    v2 = FormulaMatchEvaluatorV2(compute_cdm=False)
    assert v2.compare(r"Bias^2+V", r"Bias^2+Var").strict_canonical_exact is False
    assert v2.compare(r"\mathcal{Y}", r"y").strict_canonical_exact is False
    assert v2.compare(r"a\times b", r"a*b").strict_canonical_exact is False


def test_gold_rejects_tag_in_latex():
    issues = validate_gold_record(
        {
            "id": "x",
            "pdf_id": "p",
            "page": 1,
            "gold_latex_raw": r"E=mc^2\tag{12}",
            "verified": True,
        }
    )
    assert "gold_must_not_contain_tag" in issues
