# -*- coding: utf-8 -*-
"""Phase 5C：Worker client 协议 / 超时字段（无 GPU）。"""
from __future__ import annotations

from app.formula.config import formula_config_for_deepseek_limited_production
from app.ocr.deepseek_worker_client import DeepSeekWorkerClient, WorkerTimings


def test_limited_production_has_load_and_parallel_flags():
    cfg = formula_config_for_deepseek_limited_production()
    assert cfg.deepseek_load_timeout_seconds >= 180
    assert cfg.deepseek_formula_timeout_seconds == 30.0
    assert cfg.deepseek_parallel_warmup is True
    assert cfg.deepseek_coverage_first is True
    assert cfg.deepseek_timeout_deferred_retry is True


def test_worker_timings_overlap_math():
    t = WorkerTimings()
    t.load_seconds = 100.0
    # simulate: docling 0..90, load 10..110 → overlap 80, blocking 20
    t.load_started_at = 10.0
    t.load_finished_at = 110.0
    ds, de = 0.0, 90.0
    lo = max(t.load_started_at, ds)
    hi = min(t.load_finished_at, de)
    t.load_overlap_seconds = max(0.0, hi - lo)
    t.blocking_load_seconds = max(0.0, t.load_seconds - t.load_overlap_seconds)
    assert abs(t.load_overlap_seconds - 80.0) < 1e-6
    assert abs(t.blocking_load_seconds - 20.0) < 1e-6
    d = t.to_dict()
    assert "blocking_load_seconds" in d


def test_client_disabled_flag():
    c = DeepSeekWorkerClient()
    c.disabled = True
    r = c.recognize(image_b64="AAAA", mode="formula")
    assert r.get("ok") is False
    assert "disabled" in str(r.get("error") or "")
