# -*- coding: utf-8 -*-
"""Phase 5E Lean：不触达 UniMERNet。"""
from __future__ import annotations

from app.formula.config import formula_config_for_deepseek_limited_production
from app.formula.recognizer import NullFormulaRecognizer, build_recognizer
from app.formula.recovery_route import RecoveryRoute, route_corrupted_formula
from app.formula.types import FormulaCandidate


def test_lean_config_null_recognizer():
    cfg = formula_config_for_deepseek_limited_production()
    assert cfg.lean_docling_balanced is True
    assert cfg.recognizer_primary == "null"
    rec = build_recognizer(cfg)
    assert isinstance(rec, NullFormulaRecognizer)
    assert rec.name == "null"


def test_lean_route_always_deepseek():
    cand = FormulaCandidate(text=r"x=1", display_mode="display")
    r = route_corrupted_formula(
        cand,
        deepseek_available=True,
        prefer_deepseek_primary=True,
        lean_deepseek_only=True,
    )
    assert r == RecoveryRoute.DEEPSEEK_DIRECT
