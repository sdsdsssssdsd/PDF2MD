# -*- coding: utf-8 -*-
"""debug4.md：Corruption → Recovery → ReleaseGate 闭环回归。"""
from __future__ import annotations

from app.formula.config import FormulaConfig
from app.formula.corruption import assess_corruption, strip_spacing
from app.formula.pipeline import FormulaPipeline
from app.formula.release_gate import check_release
from app.formula.types import FormulaLifecycle
from app.formula.validator import validate_latex


def _recall_garbage() -> str:
    return r"\Gamma " + (r"\quad " * 40) + r"\ \ \ \ \ " * 20


def _f1_hallucination() -> str:
    return (
        r"|^{n}_{e} F1 = 2 \times "
        r"\frac{\Pr_{\ } c a r {\lfloor}}{\Pr_{\ } c a r {\rfloor}}"
    )


def test_corruption_recall_quad_spam():
    q = assess_corruption(_recall_garbage())
    assert not q.valid
    assert q.corruption_score >= 0.8
    assert q.recoverable
    assert any(
        r in q.reasons
        for r in ("quad_run", "spacing_only_ratio", "degenerate_after_strip", "long_low_information")
    )
    # spacing 剔除后几乎只剩 Gamma
    assert len(strip_spacing(_recall_garbage())) < 20


def test_corruption_pix2tex_hbar_and_nn_frac():
    hbar = r"{{=}} \\ {{}} \\ {{-}} \\ {{\frac{\hbar}{\hbar}}}"
    nn = r"{{\frac{n}{n}}} \\ {{\frac{n}{n}}} \\ {{\frac{n}{n}}} \\ {{\frac{n}{n}}}"
    tests = r"= \frac{TP}{TP+FN} \quad (6) \quad \text{tests}"
    for body in (hbar, nn, tests):
        q = assess_corruption(body)
        assert not q.valid, body
        assert q.corruption_score >= 0.9


def test_validator_does_not_mean_immediate_fallback_markup():
    """invalid 必须先走 recovery；失败后 MD 留可见报错，不得静默消失。"""
    md = (
        "Recall can be calculated using Eq. (4):\n\n"
        f"$${_recall_garbage()}$$\n\n"
        "The F1-score:\n\n"
        f"$${_f1_hallucination()}$$\n\n"
        "$$TPR = \\frac{TP}{TP+FN}$$\n\n"
        "$$FPR = \\frac{FP}{FP+TN}$$\n"
    )
    cfg = FormulaConfig(fallback_mode="clean", recovery_enabled=True)
    res = FormulaPipeline(cfg).process_markdown(md, pdf_path=None)
    assert "formula-not-decoded" not in res.markdown  # clean 不用 HTML 注释
    assert r"\quad \quad \quad" not in res.markdown
    assert "公式未能可靠提取" in res.markdown  # 可见报错，不消失
    assert "TPR" in res.markdown and "FPR" in res.markdown
    assert res.report.corrupted_formula_count >= 2
    assert res.report.recovery_attempted_count >= 2
    assert res.report.recovery_failed_count >= 2
    assert res.report.formula_failures
    lifecycles = {d.get("lifecycle") for d in res.report.details if d.get("mode") == "display"}
    assert FormulaLifecycle.RECOVERY_FAILED.value in lifecycles
    assert FormulaLifecycle.VALID.value in lifecycles


def test_failed_formula_never_silent():
    md = "Recall using Eq. (4):\n\n$$\\Gamma$$\n"
    out = FormulaPipeline(FormulaConfig(fallback_mode="clean")).process_markdown(md).markdown
    assert "公式未能可靠提取" in out
    assert "Eq. (4)" in out


def test_debug_fallback_mode_allows_comment():
    md = f"$$\n{_f1_hallucination()}\n$$"
    cfg = FormulaConfig(fallback_mode="debug", recovery_enabled=True)
    res = FormulaPipeline(cfg).process_markdown(md)
    assert "formula-not-decoded" in res.markdown
    assert "reason=" in res.markdown


def test_forbid_context_invention_guard():
    """即使上下文是 Recall，也不得直接写出标准公式（Null OCR 路径）。"""
    md = "Recall can be calculated using Eq. (4):\n\n$$\\Gamma$$\n"
    res = FormulaPipeline(FormulaConfig(fallback_mode="clean")).process_markdown(md)
    assert "TP+FN" not in res.markdown.replace(" ", "")
    assert r"\frac{TP}" not in res.markdown


def test_release_gate_marks_incomplete():
    md = "ok text"
    from app.formula.types import FormulaQAReport

    report = FormulaQAReport(recovery_failed_count=3, corrupted_formula_count=3)
    dq = check_release(md, report, FormulaConfig(fallback_mode="clean"))
    assert dq.status == "formula_incomplete"
    assert not dq.publishable


def test_valid_metrics_survive():
    md = "$$\nTPR = \\frac{TP}{TP+FN}\n$$\n$$\nFPR = \\frac{FP}{FP+TN}\n$$"
    res = FormulaPipeline(FormulaConfig()).process_markdown(md)
    assert "TPR" in res.markdown and "FPR" in res.markdown
    assert res.report.recovery_failed_count == 0
    assert res.report.document_quality is None or res.report.document_quality.publishable


def test_context_mismatch_triggers_corruption():
    body = r"\Gamma"
    vr = validate_latex(
        body,
        FormulaConfig(),
        context_before="Recall can be calculated using Eq. (4):",
        context_after="The F1-score",
    )
    assert not vr.valid
    assert any("context_mismatch" in x for x in vr.issues)


def _o024_brier_garbage() -> str:
    return (
        r"\text {wein out comes and predicted probabinities} \, [ 9 ] \colon \\ "
        r"\text {Brier} \, = \, \frac { 1 } { n } \sum _ { i = 1 } ^ { n } "
        r"( y _ { i } - \hat { p } _ { i } ) ^ { 2 } ."
    )


def _o024_f1_garbage() -> str:
    return (
        r"F 1 & = \frac { 2 \Pr e c { R e c } } { \Pr e c { + R e c } } , "
        r"\quad \Pr e c { = \frac { T P } { T P + F P } } , "
        r"\quad R e c = \frac { T P } { T P + F N } . \\"
    )


def test_o024_brier_and_f1_garbage_marked_corrupted():
    brier_ctx = (
        "Calibration: we report the Brier score (lower is better), "
        "defined as the mean squared error between outcomes and predicted probabilities [9]:"
    )
    f1_ctx = (
        "Fixed-threshold performance: we report the F1 score at threshold 0.5 (F1@0.5), "
        "which balances precision and recall for the positive class [22]."
    )
    vb = validate_latex(_o024_brier_garbage(), FormulaConfig(), context_before=brier_ctx)
    vf = validate_latex(_o024_f1_garbage(), FormulaConfig(), context_before=f1_ctx)
    assert not vb.valid
    assert not vf.valid
    assert vb.quality.corruption_score >= 0.75
    assert vf.quality.corruption_score >= 0.75


def test_o024_canary_writeback_artifacts_rejected():
    brier_wb = r"\frac{1}{n}\sum_{i=1}^{n}(y_{i}-\hat{p}_{i})^{2} \) ."
    f1_wb = r"\begin{aligned}&=\frac{TP}{TP+FP},\quad Rec=\frac{TP}{TP+FN}.\end{aligned}"
    qb = assess_corruption(brier_wb)
    qf = assess_corruption(f1_wb)
    assert not qb.valid
    assert not qf.valid
    assert "stray_inline_close" in qb.reasons
    assert "aligned_missing_lhs" in qf.reasons
