# -*- coding: utf-8 -*-
"""Phase 5B-Perf：coverage-first / circuit breaker / route（无 GPU）。"""
from __future__ import annotations

from app.formula.recovery_route import RecoveryRoute, route_corrupted_formula
from app.formula.types import FormulaCandidate, FormulaLifecycle, FormulaQuality
from app.ocr.circuit_breaker import CircuitBreaker, OcrFailureClass, classify_ocr_failure
from app.ocr.scheduler import DocumentRecoveryBudget, SchedulerConfig


def test_classify_runtime_error():
    assert classify_ocr_failure("ocr_failed:RuntimeError") == OcrFailureClass.OCR_RUNTIME_ERROR
    assert classify_ocr_failure("formula_not_found") == OcrFailureClass.OCR_RESULT_BAD
    assert classify_ocr_failure("timeout:30s") == OcrFailureClass.OCR_TIMEOUT


def test_circuit_breaker_trips_on_runtime():
    b = CircuitBreaker()
    b.observe_error("ocr_failed:RuntimeError", success=False)
    assert b.tripped
    assert b.failure_class == OcrFailureClass.OCR_RUNTIME_ERROR.value


def test_circuit_breaker_ignores_timeout():
    b = CircuitBreaker()
    b.observe_error("timeout:30.0s", success=False)
    assert not b.tripped
    assert classify_ocr_failure("timeout:30.0s") == OcrFailureClass.OCR_TIMEOUT


def test_circuit_breaker_ignores_result_bad():
    b = CircuitBreaker()
    b.observe_error("formula_not_found_in_ocr", success=False)
    assert not b.tripped


def test_route_severe_to_deepseek():
    cand = FormulaCandidate(
        text=r"\quad " * 20,
        raw_text=r"\quad " * 20,
        lifecycle=FormulaLifecycle.CORRUPTED,
        quality=FormulaQuality(corruption_score=0.95, valid=False),
    )
    assert (
        route_corrupted_formula(cand, deepseek_available=True, prefer_deepseek_primary=True)
        == RecoveryRoute.DEEPSEEK_DIRECT
    )


def test_soft_budget_not_block_mandatory_count():
    cfg = SchedulerConfig(
        coverage_first=True,
        guarantee_one_attempt=True,
        max_total_recovery_seconds=10.0,
        hard_limit_seconds=300.0,
        max_formulas_per_document=2,
    )
    bud = DocumentRecoveryBudget(seconds_used=50.0, formulas_used=2)
    # soft + formula cap：mandatory 仍不因 soft/公式帽阻断
    exceed, reason = bud.would_exceed(
        cfg=cfg, extra_formulas=1, extra_seconds=8.0, stage="mandatory"
    )
    assert not exceed
    # hard 阻断
    bud.seconds_used = 301.0
    exceed, reason = bud.would_exceed(
        cfg=cfg, extra_formulas=1, extra_seconds=8.0, stage="mandatory"
    )
    assert exceed
    assert reason == "hard_limit_exceeded"
