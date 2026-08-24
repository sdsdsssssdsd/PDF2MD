# -*- coding: utf-8 -*-
"""Phase 4A：Cost-aware RecoveryScheduler 决策单测（无 GPU）。"""
from __future__ import annotations

from app.ocr.cost_model import CostModelSnapshot, RecoveryCostModel, RuntimeState
from app.ocr.scheduler import (
    DocumentRecoveryBudget,
    RecoveryMode,
    RecoveryScheduler,
    SchedulerConfig,
)


def _warm_model(
    formula: float = 3.0,
    page: float = 40.0,
    *,
    page_deficit: float = 0.0,
    page_quality_samples: int = 0,
) -> RecoveryCostModel:
    snap = CostModelSnapshot(
        formula_seconds_ema=formula,
        page_seconds_ema=page,
        model_load_seconds_ema=166.0,
        formula_samples=10,
        page_samples=5,
        page_usable_deficit_ema=page_deficit,
        page_quality_samples=page_quality_samples,
    )
    m = RecoveryCostModel(snapshot=snap, auto_load=False, auto_save=False)
    m.runtime = RuntimeState(model_loaded=True, device="RTX 4060")
    return m


def test_n1_always_formula():
    sch = RecoveryScheduler(cost_model=_warm_model(), config=SchedulerConfig())
    d = sch.decide_page(page=6, corrupted_formula_count=1)
    assert d.chosen_mode == RecoveryMode.FORMULA
    assert d.reason == "single_formula"


def test_n2_phase3c_must_formula_batch():
    """N=2, formula=3s, page=40s → FORMULA_BATCH（且低于 min_page=8）。"""
    sch = RecoveryScheduler(
        cost_model=_warm_model(3.0, 40.0),
        config=SchedulerConfig(min_page_formula_count=8, page_safety_factor=1.2),
    )
    d = sch.decide_page(page=7, corrupted_formula_count=2)
    assert d.chosen_mode == RecoveryMode.FORMULA_BATCH
    assert d.reason == "below_min_page_formula_count"
    assert d.trace["selected"] == "formula_batch"


def test_n20_page_when_cheaper():
    sch = RecoveryScheduler(
        cost_model=_warm_model(3.0, 40.0),
        config=SchedulerConfig(
            min_page_formula_count=8,
            page_safety_factor=1.2,
            max_formulas_per_document=50,
            max_total_recovery_seconds=500.0,
        ),
    )
    # 20*3=60; 40*1.2=48 → PAGE
    d = sch.decide_page(page=3, corrupted_formula_count=20)
    assert d.chosen_mode == RecoveryMode.PAGE
    assert d.reason == "page_cheaper_with_safety"


def test_n20_quality_blocks_page():
    sch = RecoveryScheduler(
        cost_model=_warm_model(3.0, 40.0, page_deficit=2.0, page_quality_samples=5),
        config=SchedulerConfig(
            min_page_formula_count=8,
            page_safety_factor=1.2,
            max_page_usable_deficit=1,
            max_formulas_per_document=50,
            max_total_recovery_seconds=500.0,
        ),
    )
    d = sch.decide_page(page=3, corrupted_formula_count=20)
    assert d.chosen_mode == RecoveryMode.FORMULA_BATCH
    assert d.reason == "page_quality_insufficient"


def test_budget_skip():
    bud = DocumentRecoveryBudget(seconds_used=85.0)
    sch = RecoveryScheduler(
        cost_model=_warm_model(3.0, 40.0),
        config=SchedulerConfig(
            max_total_recovery_seconds=90.0,
            coverage_first=False,
            guarantee_one_attempt=False,
        ),
        budget=bud,
    )
    # remaining 5s, formula cost 8s → SKIP
    d = sch.decide_page(page=1, corrupted_formula_count=1)
    # wait: n=1 formula cost = 3s with warm model, not 8s
    # use n such that cost > 5: n=2 → below min → formula_batch cost 6 > 5
    d = sch.decide_page(page=1, corrupted_formula_count=2)
    assert d.chosen_mode == RecoveryMode.SKIP
    assert "budget_exceeded" in d.reason


def test_budget_skip_explicit_estimate():
    """budget remaining=5s, estimated formula=8s → SKIP。"""
    m = _warm_model(8.0, 40.0)
    bud = DocumentRecoveryBudget(seconds_used=0.0)
    sch = RecoveryScheduler(
        cost_model=m,
        config=SchedulerConfig(
            max_total_recovery_seconds=5.0,
            coverage_first=False,
            guarantee_one_attempt=False,
        ),
        budget=bud,
    )
    d = sch.decide_page(page=1, corrupted_formula_count=1)
    assert d.chosen_mode == RecoveryMode.SKIP
    assert d.reason == "budget_exceeded"


def test_coverage_first_soft_budget_still_runs_mandatory():
    """soft 已超，coverage_first 下 mandatory 仍给 FORMULA，不 SKIP。"""
    m = _warm_model(8.0, 40.0)
    bud = DocumentRecoveryBudget(seconds_used=100.0)
    sch = RecoveryScheduler(
        cost_model=m,
        config=SchedulerConfig(
            max_total_recovery_seconds=90.0,
            hard_limit_seconds=300.0,
            coverage_first=True,
            guarantee_one_attempt=True,
        ),
        budget=bud,
    )
    d = sch.decide_page(page=7, corrupted_formula_count=1)
    assert d.chosen_mode == RecoveryMode.FORMULA
    assert d.reason == "single_formula"


def test_coverage_first_hard_limit_skips():
    m = _warm_model(8.0, 40.0)
    bud = DocumentRecoveryBudget(seconds_used=301.0)
    sch = RecoveryScheduler(
        cost_model=m,
        config=SchedulerConfig(
            max_total_recovery_seconds=90.0,
            hard_limit_seconds=300.0,
            coverage_first=True,
            guarantee_one_attempt=True,
        ),
        budget=bud,
    )
    d = sch.decide_page(page=7, corrupted_formula_count=1)
    assert d.chosen_mode == RecoveryMode.SKIP
    assert d.reason == "hard_limit_exceeded"


def test_page_cache_reuse_zero_cost():
    sch = RecoveryScheduler(cost_model=_warm_model(), config=SchedulerConfig())
    d = sch.decide_page(page=7, corrupted_formula_count=1, page_cached=True)
    assert d.chosen_mode == RecoveryMode.PAGE_REUSE
    assert d.reason == "page_cache_hit"
    assert d.estimated_page_seconds == 0.0


def test_cold_start_model_load_once_not_times_n():
    snap = CostModelSnapshot(
        formula_seconds_ema=3.0,
        page_seconds_ema=40.0,
        model_load_seconds_ema=166.0,
    )
    m = RecoveryCostModel(snapshot=snap, auto_load=False, auto_save=False)
    m.runtime.model_loaded = False
    # cold batch N=3: 166 + 9 = 175, 不是 3*(166+3)
    assert abs(m.estimate_formula_batch(3) - 175.0) < 1e-6
    m.runtime.model_loaded = True
    assert abs(m.estimate_formula_batch(3) - 9.0) < 1e-6


def test_no_region_mode_in_enum_path():
    sch = RecoveryScheduler(cost_model=_warm_model(), config=SchedulerConfig(allow_region=True))
    d = sch.decide_page(page=7, corrupted_formula_count=2)
    assert d.chosen_mode != "region"
    assert d.chosen_mode in {
        RecoveryMode.FORMULA,
        RecoveryMode.FORMULA_BATCH,
        RecoveryMode.PAGE,
        RecoveryMode.PAGE_REUSE,
        RecoveryMode.SKIP,
    }


def test_ema_observe_updates(tmp_path):
    path = tmp_path / "formula_runtime_profile.json"
    m = RecoveryCostModel(
        snapshot=CostModelSnapshot(formula_seconds_ema=3.0),
        profile_path=path,
        auto_load=False,
        auto_save=True,
        alpha=0.5,
    )
    m.runtime.model_loaded = True
    m.observe_formula(5.0)
    assert abs(m.snap.formula_seconds_ema - 4.0) < 1e-6
    assert path.exists()
    m2 = RecoveryCostModel(profile_path=path, auto_load=True, auto_save=False)
    assert abs(m2.snap.formula_seconds_ema - 4.0) < 1e-6


def test_decision_trace_has_reason():
    sch = RecoveryScheduler(cost_model=_warm_model(3.0, 40.0), config=SchedulerConfig())
    d = sch.decide_page(page=7, corrupted_formula_count=2)
    assert d.trace.get("reason")
    assert d.trace.get("selected")
    assert "formula_cost_estimate" in d.trace
