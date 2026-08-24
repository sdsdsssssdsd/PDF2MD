# -*- coding: utf-8 -*-
from __future__ import annotations

from app.formula.backends import uses_deepseek_pending
from app.formula.config import formula_config_for_k5_specialist
from app.formula.recovery_route import RecoveryRoute, route_corrupted_formula
from app.formula.types import FormulaCandidate, FormulaLifecycle, FormulaQuality


def _severe() -> FormulaCandidate:
    return FormulaCandidate(
        text=r"\quad " * 20,
        raw_text=r"\quad " * 20,
        lifecycle=FormulaLifecycle.CORRUPTED,
        quality=FormulaQuality(corruption_score=0.95, valid=False),
    )


def _mild() -> FormulaCandidate:
    return FormulaCandidate(
        text=r"x=1",
        raw_text=r"x=1",
        lifecycle=FormulaLifecycle.CORRUPTED,
        quality=FormulaQuality(corruption_score=0.2, valid=False),
    )


def test_legacy_lean_still_deepseek():
    r = route_corrupted_formula(
        _mild(),
        deepseek_available=True,
        prefer_deepseek_primary=True,
        lean_deepseek_only=True,
    )
    assert r == RecoveryRoute.DEEPSEEK_DIRECT


def test_k5_fast_never_vlm():
    r = route_corrupted_formula(
        _severe(),
        deepseek_available=False,
        backend_mode="k5_specialist",
        recovery_preset="fast",
        specialist_available=True,
        vlm_available=True,
    )
    assert r == RecoveryRoute.SPECIALIST_PRIMARY


def test_k5_balanced_hard_goes_vlm():
    r = route_corrupted_formula(
        _severe(),
        deepseek_available=False,
        backend_mode="k5_specialist",
        recovery_preset="balanced",
        specialist_available=True,
        vlm_available=True,
    )
    assert r == RecoveryRoute.VLM_FALLBACK


def test_k5_balanced_easy_specialist():
    r = route_corrupted_formula(
        _mild(),
        deepseek_available=False,
        backend_mode="k5_specialist",
        recovery_preset="balanced",
        specialist_available=True,
        vlm_available=True,
    )
    assert r == RecoveryRoute.SPECIALIST_PRIMARY


def test_k5_abstain_when_nothing_available():
    r = route_corrupted_formula(
        _severe(),
        deepseek_available=False,
        backend_mode="k5_specialist",
        recovery_preset="balanced",
        specialist_available=False,
        vlm_available=False,
    )
    assert r == RecoveryRoute.ABSTAIN


def test_k5_config_is_shadow_not_production():
    cfg = formula_config_for_k5_specialist("balanced")
    assert cfg.formula_backend_mode == "k5_specialist"
    assert cfg.k5_shadow_only is True
    assert cfg.deepseek_limited_production_enabled is False
    assert cfg.recognizer_primary == "pp_formulanet_plus_m"
    cfg_q = formula_config_for_k5_specialist("quality")
    assert cfg_q.recognizer_primary == "pp_formulanet_plus_l"


def test_k5_mode_does_not_use_deepseek_pending():
    assert uses_deepseek_pending("k5_specialist", "paddleocr_vl_1_6") is False
    assert uses_deepseek_pending("legacy_deepseek", "paddleocr_vl_1_6") is True
    assert uses_deepseek_pending("k5_specialist", "deepseek_ocr2") is True
