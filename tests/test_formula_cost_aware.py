# -*- coding: utf-8 -*-
"""debug6：Cost-aware Recovery — 预算 / Gain / Token 否决 / preset。"""
from __future__ import annotations

from pathlib import Path

from app.formula.config import FormulaConfig, formula_config_for_preset
from app.formula.gain import evaluate_recovery_gain, looks_truncated
from app.formula.pipeline import FormulaPipeline
from app.formula.recognizer import FormulaRecognitionResult
from app.formula.recovery import FormulaRecoveryManager
from app.formula.session import FormulaRecoverySession
from app.formula.tokens import token_consistency
from app.formula.types import (
    DocumentContext,
    FormulaCandidate,
    FormulaLifecycle,
    FormulaQuality,
)


class _CounterRec:
    name = "counter"

    def __init__(self, latex: str = r"\frac{n}{n+\mu_0}") -> None:
        self.latex = latex
        self.n = 0

    def recognize(self, image, context=None):
        del image
        assert context is None
        self.n += 1
        return FormulaRecognitionResult(
            latex=self.latex,
            success=True,
            recognizer=self.name,
            raw=self.latex,
        )


class _SeqRec:
    name = "seq"

    def __init__(self, items: list[str]) -> None:
        self.items = list(items)
        self.n = 0

    def recognize(self, image, context=None):
        del image, context
        latex = self.items[min(self.n, len(self.items) - 1)]
        self.n += 1
        return FormulaRecognitionResult(
            latex=latex, success=True, recognizer=self.name, raw=latex
        )


def _tiny_pdf(tmp_path: Path) -> Path:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Recall can be calculated using Eq. (4)")
    page.insert_text((500, 200), "(4)")
    path = tmp_path / "eq.pdf"
    doc.save(str(path))
    doc.close()
    return path


def _cand(**kw) -> FormulaCandidate:
    data = dict(
        text=r"\Gamma " + (r"\quad " * 20),
        raw_text=r"\Gamma",
        page=0,
        bbox=(40.0, 160.0, 420.0, 230.0),
        context_before="Recall can be calculated using Eq. (4):",
        context_after="The F1-score",
        quality=FormulaQuality(corruption_score=1.0, valid=False, recoverable=True),
        issues=["long_low_information"],
    )
    data.update(kw)
    return FormulaCandidate(**data)


def test_presets_fast_balanced_quality():
    fast = formula_config_for_preset("fast")
    bal = formula_config_for_preset("balanced")
    qual = formula_config_for_preset("quality")
    assert fast.budget.max_ocr_calls_per_formula == 0
    assert fast.budget.max_ocr_calls_per_document == 0
    assert bal.crop_render_scale == 2.0
    assert bal.preprocess_variants is False
    assert bal.budget.max_ocr_calls_per_formula == 1
    assert bal.budget.max_ocr_calls_per_document == 0
    assert qual.crop_render_scale == 2.5
    assert qual.budget.max_ocr_calls_per_formula == 2
    assert qual.budget.max_ocr_calls_per_document == 0
    # 默认 FormulaConfig = Balanced + UniMERNet
    d = FormulaConfig()
    assert d.recovery_preset == "balanced"
    assert d.preprocess_variants is False
    assert d.crop_render_scale == 2.0
    assert d.recognizer_primary == "unimernet"


def test_token_conflict_recall_vs_mu():
    ratio, reasons = token_consistency(
        "Recall can be calculated using Eq. (4) TP FN",
        r"\frac{n}{n+\mu_0}",
    )
    assert ratio == 0.0
    assert "ocr_context_conflict" in reasons


def test_token_conflict_mse_vs_omega():
    ratio, reasons = token_consistency(
        "The expected MSE bias-variance decomposition epsilon",
        r"\frac{\omega_{nd}^{n}}{\omega}",
    )
    assert "ocr_context_conflict" in reasons
    d = evaluate_recovery_gain(
        before_quality=FormulaQuality(corruption_score=1.0, valid=False),
        after_quality=FormulaQuality(corruption_score=0.0, valid=True, syntax_score=1.0),
        before_latex=r"\scriptstyle{\frac{\omega_{nd}^{n}}{\omega}}",
        after_latex=r"\frac{\omega_{nd}^{n}}{\omega}",
        context_before="The expected MSE is given by the bias-variance:",
        context_after="where epsilon is noise.",
        after_valid=True,
    )
    assert not d.accept
    assert not d.promising


def test_truncated_is_promising_not_accept():
    assert looks_truncated(r"Recall = \frac{TP}{TP+")
    d = evaluate_recovery_gain(
        before_quality=FormulaQuality(corruption_score=1.0, valid=False),
        after_quality=FormulaQuality(corruption_score=0.4, valid=False, syntax_score=0.4),
        before_latex=r"\Gamma",
        after_latex=r"Recall = \frac{TP}{TP+",
        context_before="Recall can be calculated using Eq. (4):",
        context_after="",
        after_valid=False,
    )
    assert not d.accept
    assert d.promising


def test_fast_preset_never_calls_ocr(tmp_path):
    pdf = _tiny_pdf(tmp_path)
    cfg = formula_config_for_preset("fast", fallback_mode="clean")
    rec = _CounterRec()
    mgr = FormulaRecoveryManager(cfg, recognizer=rec)
    with FormulaRecoverySession(pdf, cfg) as sess:
        mgr.bind_session(sess)
        out = mgr.recover(_cand(), DocumentContext(pdf_path=str(pdf)), sess)
    assert rec.n == 0
    assert out.lifecycle == FormulaLifecycle.RECOVERY_FAILED
    assert "ocr_skipped_budget" in out.issues


def test_balanced_no_document_call_cap(tmp_path):
    pdf = _tiny_pdf(tmp_path)
    cfg = formula_config_for_preset("balanced")
    assert cfg.budget.max_ocr_calls_per_document == 0
    rec = _CounterRec()
    mgr = FormulaRecoveryManager(cfg, recognizer=rec)
    with FormulaRecoverySession(pdf, cfg) as sess:
        mgr.bind_session(sess)
        for _ in range(6):
            mgr.recover(_cand(), DocumentContext(pdf_path=str(pdf)), sess)
        # 每式 1 次，全文不限 → 6 个坏公式 = 6 次 OCR
        assert rec.n == 6
        assert sess.telemetry.ocr_calls == 6
        assert sess.telemetry.recovery_skipped_budget == 0


def test_quality_second_ocr_only_if_promising(tmp_path):
    pdf = _tiny_pdf(tmp_path)
    cfg = formula_config_for_preset("quality")
    rec = _SeqRec(
        [
            r"Recall = \frac{TP}{TP+",
            r"Recall = \frac{TP}{TP+FN}",
        ]
    )
    mgr = FormulaRecoveryManager(cfg, recognizer=rec)
    with FormulaRecoverySession(pdf, cfg) as sess:
        out = mgr.recover(_cand(), DocumentContext(pdf_path=str(pdf)), sess)
    assert rec.n == 2
    assert out.lifecycle == FormulaLifecycle.RECOVERY_SUCCESS
    assert "TP+FN" in out.text


def test_quality_stops_after_unrelated_ocr(tmp_path):
    pdf = _tiny_pdf(tmp_path)
    cfg = formula_config_for_preset("quality")
    rec = _CounterRec(r"\frac{\omega_{nd}^{n}}{\omega}")
    mgr = FormulaRecoveryManager(cfg, recognizer=rec)
    with FormulaRecoverySession(pdf, cfg) as sess:
        out = mgr.recover(_cand(), DocumentContext(pdf_path=str(pdf)), sess)
    assert rec.n == 1
    assert out.lifecycle == FormulaLifecycle.RECOVERY_FAILED


def test_pipeline_telemetry_and_fast_no_ocr():
    md = (
        "Recall using Eq. (4):\n\n$$\\Gamma$$\n\n"
        "$$TPR = \\frac{TP}{TP+FN}$$\n"
    )
    res = FormulaPipeline(
        formula_config_for_preset("fast", fallback_mode="clean")
    ).process_markdown(md)
    assert "公式未能可靠提取" in res.markdown
    assert "TPR" in res.markdown
    assert res.report.telemetry is not None
    assert res.report.telemetry.ocr_calls == 0
    assert res.report.telemetry.preset == "fast"


def test_pdf_session_opens_once(tmp_path, monkeypatch):
    pdf = _tiny_pdf(tmp_path)
    import pymupdf

    opens = {"n": 0}
    real_open = pymupdf.open

    def wrapped(*a, **k):
        opens["n"] += 1
        return real_open(*a, **k)

    monkeypatch.setattr(pymupdf, "open", wrapped)
    cfg = formula_config_for_preset("balanced")
    rec = _CounterRec()
    mgr = FormulaRecoveryManager(cfg, recognizer=rec)
    with FormulaRecoverySession(pdf, cfg) as sess:
        mgr.bind_session(sess)
        mgr.recover(_cand(), DocumentContext(pdf_path=str(pdf)), sess)
        mgr.recover(_cand(), DocumentContext(pdf_path=str(pdf)), sess)
    assert opens["n"] == 1
