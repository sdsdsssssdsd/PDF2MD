# -*- coding: utf-8 -*-
"""Phase 4B：Shadow Executor — OCR 次数 / SKIP / cache / EMA 隔离。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

from app.formula.config import FormulaConfig
from app.formula.types import FormulaCandidate, FormulaLifecycle
from app.ocr import DocumentOCRResult, OCRMode
from app.ocr.cache import PageOCRCache
from app.ocr.cost_model import CostModelSnapshot, RecoveryCostModel
from app.ocr.deepseek_ocr2 import FakeDeepSeekOCR2Recognizer
from app.ocr.executor import ExecutorContext, RecoveryExecutor
from app.ocr.scheduler import (
    DocumentRecoveryBudget,
    RecoveryCostEstimate,
    RecoveryMode,
    RecoveryScheduler,
    SchedulerConfig,
)
from app.ocr.shadow import ShadowRecoveryRunner, group_candidates_by_page


def _cand(page: int, eq: str, *, bbox=(10.0, 10.0, 100.0, 40.0)) -> FormulaCandidate:
    return FormulaCandidate(
        text=r"\quad\quad garbage",
        page=page,
        bbox=bbox,
        context_before=f"calculated using Eq. ({eq}):",
        lifecycle=FormulaLifecycle.CORRUPTED,
        status="corrupted",
    )


def _decision(mode: RecoveryMode, *, page: int = 7, n: int = 2, reason: str = "test") -> RecoveryCostEstimate:
    return RecoveryCostEstimate(
        formula_count=n,
        estimated_formula_seconds=n * 3.0,
        estimated_page_seconds=40.0,
        safety_factor=1.2,
        chosen_mode=mode,
        reason=reason,
        page=page,
        page_cost_with_safety=48.0,
        trace={"selected": mode.value, "reason": reason},
    )


def _session_with_page() -> Any:
    page = MagicMock()
    page.rect = MagicMock(width=612.0, height=792.0)
    pix = MagicMock()
    page.get_pixmap.return_value = pix
    doc = MagicMock()
    doc.__getitem__.return_value = page
    sess = MagicMock()
    sess.pdf_doc = doc
    sess.pdf_path = ""
    return sess


@dataclass
class _FakePIL:
    """render_clip 可能返回 pix；recognize 忽略 image。"""


def test_formula_one_ocr_per_candidate(monkeypatch):
    monkeypatch.setattr("app.ocr.executor.render_clip", lambda *a, **k: _FakePIL())
    fake = FakeDeepSeekOCR2Recognizer(
        {"formula": r"\[ TPR=\frac{TP}{TP+FN} \quad (6) \]"},
        inference_seconds=2.5,
    )
    cost = RecoveryCostModel(
        snapshot=CostModelSnapshot(formula_seconds_ema=3.0),
        auto_load=False,
        auto_save=False,
    )
    cost.runtime.model_loaded = True
    ex = RecoveryExecutor(recognizer=fake, cost_model=cost)
    cands = [_cand(7, "6"), _cand(7, "7")]
    # second needs different gold-ish output — same fake ok for call count
    res = ex.execute_page(
        cands,
        _decision(RecoveryMode.FORMULA_BATCH, n=2),
        ExecutorContext(session=_session_with_page(), pdf_hash="h"),
    )
    assert res.ocr_calls == 2
    assert len(fake.calls) == 2
    assert all(c["mode"] == "formula" for c in fake.calls)
    assert cost.snap.formula_samples == 2


def test_page_one_ocr_only(monkeypatch):
    monkeypatch.setattr("app.ocr.executor.render_clip", lambda *a, **k: _FakePIL())
    fake = FakeDeepSeekOCR2Recognizer(
        {
            "page": (
                r"\[ TPR=\frac{TP}{TP+FN} \quad (6) \]"
                r"\[ FPR=\frac{FP}{FP+TN} \quad (7) \]"
            )
        },
        inference_seconds=40.0,
    )
    cost = RecoveryCostModel(
        snapshot=CostModelSnapshot(page_seconds_ema=40.0),
        auto_load=False,
        auto_save=False,
    )
    cost.runtime.model_loaded = True
    cache = PageOCRCache()
    ex = RecoveryExecutor(recognizer=fake, cost_model=cost, page_cache=cache)
    res = ex.execute_page(
        [_cand(7, "6"), _cand(7, "7")],
        _decision(RecoveryMode.PAGE, n=2),
        ExecutorContext(session=_session_with_page(), pdf_hash="h"),
    )
    assert res.ocr_calls == 1
    assert len(fake.calls) == 1
    assert fake.calls[0]["mode"] == "page"
    assert cost.snap.page_samples == 1


def test_page_reuse_zero_ocr(monkeypatch):
    monkeypatch.setattr("app.ocr.executor.render_clip", lambda *a, **k: _FakePIL())
    fake = FakeDeepSeekOCR2Recognizer({"page": r"\[ TPR=\frac{TP}{TP+FN} \quad (6) \]"})
    cost = RecoveryCostModel(auto_load=False, auto_save=False)
    cost.runtime.model_loaded = True
    cache = PageOCRCache()
    ex = RecoveryExecutor(recognizer=fake, cost_model=cost, page_cache=cache)
    ctx = ExecutorContext(session=_session_with_page(), pdf_hash="h")
    # seed cache via PAGE once
    ex.execute_page([_cand(7, "6")], _decision(RecoveryMode.PAGE, n=1), ctx)
    n_calls = len(fake.calls)
    page_samples = cost.snap.page_samples
    res = ex.execute_page(
        [_cand(7, "6")],
        _decision(RecoveryMode.PAGE_REUSE, n=1, reason="page_cache_hit"),
        ctx,
    )
    assert res.ocr_calls == 0
    assert res.cache_hit is True
    assert res.marginal_ocr_seconds == 0.0
    assert len(fake.calls) == n_calls
    assert cost.snap.page_samples == page_samples  # cache 不进 EMA


def test_skip_zero_ocr_no_fallback(monkeypatch):
    monkeypatch.setattr("app.ocr.executor.render_clip", lambda *a, **k: _FakePIL())
    fake = FakeDeepSeekOCR2Recognizer({"formula": "x"})
    cost = RecoveryCostModel(auto_load=False, auto_save=False)
    ex = RecoveryExecutor(recognizer=fake, cost_model=cost)
    res = ex.execute_page(
        [_cand(1, "1")],
        _decision(RecoveryMode.SKIP, n=1, reason="budget_exceeded"),
        ExecutorContext(session=_session_with_page(), pdf_hash="h"),
    )
    assert res.ocr_calls == 0
    assert len(fake.calls) == 0
    assert res.mode == RecoveryMode.SKIP


def test_executor_does_not_change_mode(monkeypatch):
    monkeypatch.setattr("app.ocr.executor.render_clip", lambda *a, **k: _FakePIL())
    fake = FakeDeepSeekOCR2Recognizer({"formula": r"\[ a=b \]"})
    cost = RecoveryCostModel(auto_load=False, auto_save=False)
    cost.runtime.model_loaded = True
    ex = RecoveryExecutor(recognizer=fake, cost_model=cost)
    decision = _decision(RecoveryMode.FORMULA, n=1)
    res = ex.execute_page(
        [_cand(6, "1")],
        decision,
        ExecutorContext(session=_session_with_page(), pdf_hash="h"),
    )
    assert res.mode == RecoveryMode.FORMULA
    assert decision.chosen_mode == RecoveryMode.FORMULA


def test_outlier_clip_protects_ema():
    cost = RecoveryCostModel(
        snapshot=CostModelSnapshot(page_seconds_ema=40.0),
        auto_load=False,
        auto_save=False,
        max_outlier_multiplier=3.0,
        alpha=1.0,  # 直接看 clipped 值
    )
    cost.runtime.model_loaded = True
    info = cost.observe_page(736.0)
    assert info is not None
    assert info["raw_seconds"] == 736.0
    assert info["ema_observation"] == 120.0  # 40*3
    assert abs(cost.snap.page_seconds_ema - 120.0) < 1e-6


def test_cache_hit_not_in_page_ema(monkeypatch):
    monkeypatch.setattr("app.ocr.executor.render_clip", lambda *a, **k: _FakePIL())
    fake = FakeDeepSeekOCR2Recognizer({"page": "x"}, inference_seconds=40.0)
    cost = RecoveryCostModel(
        snapshot=CostModelSnapshot(page_seconds_ema=40.0),
        auto_load=False,
        auto_save=False,
    )
    cost.runtime.model_loaded = True
    cache = PageOCRCache()
    ex = RecoveryExecutor(recognizer=fake, cost_model=cost, page_cache=cache)
    ctx = ExecutorContext(session=_session_with_page(), pdf_hash="h")
    ex.execute_page([_cand(7, "6")], _decision(RecoveryMode.PAGE, n=1), ctx)
    assert cost.snap.page_samples == 1
    # second PAGE when cached → 0 OCR, no new sample
    ex.execute_page([_cand(7, "6")], _decision(RecoveryMode.PAGE, n=1), ctx)
    assert cost.snap.page_samples == 1
    assert len(fake.calls) == 1


def test_profile_key_isolation(tmp_path):
    path = tmp_path / "formula_runtime_profile.json"
    m = RecoveryCostModel(profile_path=path, auto_load=False, auto_save=True, alpha=1.0)
    m.set_runtime(device="RTX 4060", recognizer="deepseek-ocr-2", model="DeepSeek-OCR-2", dtype="bf16")
    m.runtime.model_loaded = True
    m.observe_formula(2.65)
    m.set_runtime(device="RTX 4090", recognizer="deepseek-ocr-2", model="DeepSeek-OCR-2", dtype="bf16")
    assert m.snap.formula_samples == 0  # 新 profile
    m.observe_formula(1.0)
    raw = path.read_text(encoding="utf-8")
    assert "RTX_4060" in raw or "NVIDIA" in raw or "RTX" in raw
    assert "profiles" in raw


def test_shadow_disabled_by_default():
    cfg = FormulaConfig()
    assert cfg.deepseek_shadow_enabled is False
    assert cfg.deepseek_scheduler_enabled is False


def test_group_by_page():
    g = group_candidates_by_page([_cand(7, "6"), _cand(7, "7"), _cand(6, "1")])
    assert set(g.keys()) == {6, 7}
    assert len(g[7]) == 2


def test_estimated_vs_actual_in_result(monkeypatch):
    monkeypatch.setattr("app.ocr.executor.render_clip", lambda *a, **k: _FakePIL())
    fake = FakeDeepSeekOCR2Recognizer({"formula": r"\[ a=1 \]"}, inference_seconds=3.0)
    cost = RecoveryCostModel(auto_load=False, auto_save=False)
    cost.runtime.model_loaded = True
    ex = RecoveryExecutor(recognizer=fake, cost_model=cost)
    res = ex.execute_page(
        [_cand(6, "1")],
        _decision(RecoveryMode.FORMULA, n=1),
        ExecutorContext(session=_session_with_page(), pdf_hash="h"),
    )
    assert res.estimated_seconds == 3.0
    assert res.cost_error_ratio is not None
    d = res.to_dict()
    assert "estimated_seconds" in d and "actual_seconds" in d
