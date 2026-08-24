# -*- coding: utf-8 -*-
from __future__ import annotations

from app.formula.config import FormulaConfig
from app.formula.ppformula_worker_recognizer import PPFormulaWorkerRecognizer
from app.formula.recognizer import FormulaRecognitionResult, NullFormulaRecognizer, build_recognizer


class _FakeClient:
    def __init__(self, payload: dict | None = None, ping_ok: bool = False) -> None:
        self.payload = payload or {"ok": False, "error": "down"}
        self.ping_ok = ping_ok

    def ping(self) -> bool:
        return self.ping_ok

    def recognize(self, **kwargs):
        del kwargs
        return self.payload


def test_worker_recognizer_does_not_invent_confidence():
    rec = PPFormulaWorkerRecognizer(
        model_name="PP-FormulaNet_plus-M",
        client=_FakeClient({"ok": True, "rec_formula": r"\frac{a}{b}"}),
    )
    try:
        from PIL import Image

        img = Image.new("RGB", (8, 8), "white")
    except Exception:
        return
    out = rec.recognize(img)
    assert isinstance(out, FormulaRecognitionResult)
    assert out.success is True
    assert out.confidence is None
    assert out.latex == r"\frac{a}{b}"


def test_worker_error_is_not_success():
    rec = PPFormulaWorkerRecognizer(client=_FakeClient({"ok": False, "error": "no_paddle"}))
    # 给一个可编码的假图会走 recognize RPC
    try:
        from PIL import Image

        img = Image.new("RGB", (8, 8), "white")
    except Exception:
        return
    out = rec.recognize(img)
    assert out.success is False
    assert out.confidence is None
    assert out.latex is None


def test_factory_pp_without_worker_is_null_or_inprocess_guard():
    cfg = FormulaConfig(recognizer_primary="pp_formulanet_plus_m")
    rec = build_recognizer(cfg)
    assert rec.name != "unimernet"
    assert isinstance(rec, (PPFormulaWorkerRecognizer, NullFormulaRecognizer)) or rec.name.startswith(
        "pp-formulanet"
    )


def test_factory_unknown_is_null():
    rec = build_recognizer(FormulaConfig(recognizer_primary="no-such-model"))
    assert isinstance(rec, NullFormulaRecognizer)
