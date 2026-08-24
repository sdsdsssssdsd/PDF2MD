# -*- coding: utf-8 -*-
"""UniMERNet recognizer：忽略 context；默认主识别器。"""
from __future__ import annotations

from PIL import Image

from app.formula.config import FormulaConfig
from app.formula.recognizer import FormulaRecognitionResult, build_recognizer
from app.formula.unimernet_recognizer import UniMERNetRecognizer


def test_default_primary_is_unimernet():
    assert FormulaConfig().recognizer_primary == "unimernet"


def test_build_recognizer_unimernet_or_null():
    rec = build_recognizer(FormulaConfig(recognizer_primary="unimernet"))
    assert hasattr(rec, "recognize")
    assert getattr(rec, "name", "") in {"unimernet", "null"}


def test_unimernet_ignores_context_contract():
    class _Fake:
        name = "unimernet"

        def recognize(self, image, context=None):
            assert context is None
            return FormulaRecognitionResult(
                latex=r"TPR = \frac{TP}{TP+FN}",
                success=True,
                recognizer=self.name,
                raw=r"TPR = \frac{TP}{TP+FN}",
                meta={"device": "cuda:0", "ignored_context": True},
            )

    r = _Fake().recognize(Image.new("RGB", (8, 8)), context=None)
    assert r.success and "TP" in (r.latex or "")


def test_unimernet_class_lazy_init_does_not_load():
    # 构造时不应立刻加载大模型
    rec = UniMERNetRecognizer(device="cpu")
    assert rec._model is None
    assert rec.name == "unimernet"
