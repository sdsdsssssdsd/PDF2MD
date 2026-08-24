# -*- coding: utf-8 -*-
from __future__ import annotations

from app.formula.gain import evaluate_recovery_gain
from app.formula.geometry import crop_bbox_suspicious
from app.formula.types import FormulaQuality
from app.ocr.extractor import _looks_like_formula
from app.ocr.formula_crop_extract import extract_formula_crop, salvage_formula_from_raw


_PROSE_OCR = (
    "<|ref|>text<|/ref|><|det|>[[0, 0, 925, 999]]<|/det|>\n"
    "ing methodology of Markov Stability, \\( ^{22,23} \\)  which we apply to our graph"
)


def test_citation_prose_is_not_formula():
    assert not _looks_like_formula("ing methodology of Markov Stability, ^{22,23}")
    assert not _looks_like_formula("^{22,23}")
    assert _looks_like_formula(r"p_{t+1}=p_t Q")
    assert _looks_like_formula(r"E\left[(y-\hat{f})^{2}\right]=Bias^{2}+V")


def test_salvage_rejects_markov_prose():
    er = salvage_formula_from_raw(_PROSE_OCR)
    assert not er.latex
    er2 = extract_formula_crop(_PROSE_OCR)
    assert not er2.latex


def test_gate_rejects_prose_recovery():
    d = evaluate_recovery_gain(
        before_quality=FormulaQuality(corruption_score=1.0, valid=False),
        after_quality=FormulaQuality(corruption_score=0.1, syntax_score=0.9, valid=True),
        before_latex=r"r(t,H)=\min_{t}\mathrm{Tr}\left[R(\tau,H)\right]",
        after_latex="ing methodology of Markov Stability, ^{22,23}",
        context_before="we apply Markov Stability to our graph",
        context_after="",
        after_valid=True,
    )
    assert not d.accept
    assert "ocr_prose_recovery" in d.reasons


def test_narrow_bbox_is_suspicious():
    # 56pt 宽条 < 0.2 * 612
    assert crop_bbox_suspicious(None, 0, (18.0, 470.0, 74.0, 511.0))
    assert not crop_bbox_suspicious(None, 0, (18.0, 100.0, 300.0, 160.0))
