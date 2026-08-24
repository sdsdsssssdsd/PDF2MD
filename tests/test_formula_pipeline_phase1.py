# -*- coding: utf-8 -*-
"""Formula Pipeline Phase 1 regression（适配 Phase2 clean fallback）。"""
from __future__ import annotations

from pathlib import Path

from app.formula.config import FormulaConfig
from app.formula.detector import detect_unwrapped, score_span
from app.formula.pipeline import FormulaPipeline
from app.formula.validator import validate_latex

FIXTURE = Path(__file__).parent / "fixtures" / "formulas" / "phase1_cases.md"


def test_case1_ece_unwrapped_detected_not_invented():
    text = "Let n b={i:pi ˛ (b -1B,bB]} be the index set of predictions in bin b."
    sc, reasons = score_span(text)
    assert sc >= 0.65, (sc, reasons)
    hits = detect_unwrapped(text)
    assert hits
    out = FormulaPipeline().process_markdown(text).markdown
    assert "\\in" not in out or "˛" in out


def test_case2_recall_quad_spam_invalid():
    body = r"\Gamma " + r"\quad " * 20
    vr = validate_latex(body)
    assert not vr.valid


def test_case3_f1_hallucination_invalid():
    body = r"|^{n}_{e} F1 = 2 \times \frac{\Pr_{\ } c a r {\lfloor}}{\Pr_{\ } c a r {\rfloor}}"
    vr = validate_latex(body)
    assert not vr.valid


def test_case4_valid_tpr_kept():
    md = "$$\nTPR = \\frac{TP}{TP+FN}\n$$"
    out = FormulaPipeline().process_markdown(md).markdown
    assert "TPR" in out and r"\frac" in out
    assert "formula-not-decoded" not in out


def test_case5_prose_pi_not_whole_formula():
    text = "The value π is approximately 3.14."
    sc, reasons = score_span(text)
    assert sc < 0.65 or "mostly_english" in reasons


def test_case6_valid_inline_not_fallback():
    md = "We set $B=15$ bins."
    out = FormulaPipeline().process_markdown(md).markdown
    assert "$B=15$" in out


def test_pipeline_fixture_file():
    raw = FIXTURE.read_text(encoding="utf-8")
    res = FormulaPipeline(FormulaConfig(fallback_mode="clean")).process_markdown(raw)
    assert res.report.corrupted_formula_count >= 2 or res.report.recovery_failed_count >= 2
    assert "TPR" in res.markdown
    assert "$B=15$" in res.markdown
    assert res.report.suspected_unwrapped >= 1
    assert "formula-not-decoded" not in res.markdown  # clean 不用 HTML 注释
    assert "公式未能可靠提取" in res.markdown  # 失败必须可见


def test_normalizer_never_on_invalid_clean():
    md = "$$\\intertext{seftime} w h e n p$$"
    out = FormulaPipeline(FormulaConfig(fallback_mode="clean")).process_markdown(md).markdown
    assert "formula-not-decoded" not in out
    assert r"\mathbf{p}" not in out
    assert "公式未能可靠提取" in out
