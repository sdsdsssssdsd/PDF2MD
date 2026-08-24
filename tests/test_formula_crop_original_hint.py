# -*- coding: utf-8 -*-
from __future__ import annotations

from app.ocr.formula_crop_extract import extract_formula_crop

_MULTI_EQ_RAW = (
    "<|ref|>equation<|/ref|><|det|>[[42, 19, 884, 199]]<|/det|>\n"
    r" \[ r(t,H)=\min_{r\in\mathcal{T}}\operatorname{Tr}\left[R(\tau,H)\right], \quad (6) \] "
    "\n\n<|ref|>equation<|/ref|><|det|>[[36, 479, 884, 666]]<|/det|>\n"
    r" \[ r^{*}\left(t\right)=\max_{H}r(t,H)and H^{*}\left(t\right)=\arg\max_{H}r(t,H). \quad (7) \] "
)


def test_pick_max_block_when_original_has_max():
    orig = (
        r"\begin{array}{ccc} r^{*}(t)=\max_{H} r(t,H) \end{array}"
    )
    er = extract_formula_crop(_MULTI_EQ_RAW, original_latex=orig)
    assert er.latex
    assert "max" in er.latex.lower()
    assert er.method == "formula_crop_original_hint"


def test_pick_min_block_when_original_has_min():
    orig = r"r(t,H)=\min_{t}\mathrm{Tr}\left[R(\tau,H)\right]"
    er = extract_formula_crop(_MULTI_EQ_RAW, original_latex=orig)
    assert er.latex
    assert "min" in er.latex.lower()
    assert "formula_crop_original_hint" == er.method
