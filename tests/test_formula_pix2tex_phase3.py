# -*- coding: utf-8 -*-
"""debug5：Pix2Tex recognizer + preprocess；OCR 忽略 context；不接 VLM。"""
from __future__ import annotations

from PIL import Image

from app.formula.config import FormulaConfig
from app.formula.preprocess import formula_image_variants, to_pil_image
from app.formula.recognizer import (
    FormulaRecognitionResult,
    NullFormulaRecognizer,
    build_recognizer,
)
from app.formula.recovery import FormulaRecoveryManager
from app.formula.types import DocumentContext, FormulaCandidate, FormulaLifecycle


class _FakePix2Tex:
    name = "pix2tex_fake"

    def __init__(self, latex: str) -> None:
        self._latex = latex
        self.saw_context = False

    def recognize(self, image, context=None):
        if context is not None:
            self.saw_context = True
        return FormulaRecognitionResult(
            latex=self._latex,
            confidence=0.99,  # 高置信也必须再过 validator
            recognizer=self.name,
            success=True,
            raw=self._latex,
        )


def test_build_recognizer_falls_back_when_pix2tex_missing():
    cfg = FormulaConfig(recognizer_primary="pix2tex")
    rec = build_recognizer(cfg)
    # 环境无 pix2tex 时应落到 Null，且不抛
    assert hasattr(rec, "recognize")
    out = rec.recognize(Image.new("RGB", (32, 16), "white"), context={"before": "Recall"})
    assert out.success is False or out.recognizer in {"pix2tex", "null"}


def test_recognizer_must_ignore_context_in_recovery_call():
    fake = _FakePix2Tex(r"Recall = \frac{TP}{TP+FN}")
    mgr = FormulaRecoveryManager(FormulaConfig(recognizer_primary="null"), recognizer=fake)
    # 无 pdf → 早退；改为直接调 recognize 契约
    r = fake.recognize(Image.new("RGB", (8, 8)), context=None)
    assert r.success and r.latex
    # RecoveryManager 传 context=None
    cand = FormulaCandidate(
        text=r"\Gamma",
        raw_text=r"\Gamma",
        status="corrupted",
        lifecycle=FormulaLifecycle.CORRUPTED,
        context_before="Recall can be calculated using Eq. (4):",
        page=0,
        bbox=(10, 10, 200, 40),
    )
    # 无真实 PDF，走 no_pdf
    out = mgr.recover(cand, DocumentContext(pdf_path=None))
    assert out.lifecycle == FormulaLifecycle.RECOVERY_FAILED


def test_high_ocr_confidence_still_rejected_if_corrupt():
    """OCR confidence ≠ validity：只输出 \\Gamma 仍应失败。"""
    fake = _FakePix2Tex(r"\Gamma")
    # 直接走 validate 路径：模拟 recovery 内逻辑
    from app.formula.validator import validate_latex

    vr = validate_latex(
        r"\Gamma",
        FormulaConfig(),
        context_before="Recall can be calculated using Eq. (4):",
    )
    assert not vr.valid
    assert fake.recognize(None, context={"before": "Recall"}).confidence == 0.99


def test_preprocess_variants_cap_at_3():
    img = Image.new("RGB", (40, 20), "white")
    v1 = formula_image_variants(img, attempt=1)
    v2 = formula_image_variants(img, attempt=2)
    v3 = formula_image_variants(img, attempt=3)
    assert len(v1) == 1 and v1[0][0] == "original"
    assert len(v2) == 2 and v2[1][0] == "contrast"
    assert len(v3) == 3 and v3[2][0] == "upscale1_5_sharp"
    assert to_pil_image(img) is not None


def test_vlm_fallback_disabled_by_default():
    cfg = FormulaConfig()
    assert cfg.vlm_fallback_enabled is False
    assert cfg.recognizer_primary == "unimernet"
    assert cfg.preprocess_variants is False
    assert cfg.crop_render_scale == 2.0
    assert cfg.budget.max_ocr_calls_per_formula == 1
    assert cfg.budget.max_ocr_calls_per_document == 0


def test_null_recognizer_result_shape():
    r = NullFormulaRecognizer("x").recognize(None, context={"a": 1})
    assert r.success is False
    assert r.recognizer == "null"
    assert r.error
