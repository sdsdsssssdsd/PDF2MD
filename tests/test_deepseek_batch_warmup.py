# -*- coding: utf-8 -*-
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.ocr.deepseek_batch_warmup import (
    deepseek_critical_path_seconds,
    ensure_deepseek_before_repair,
    finalize_deepseek_timings_after_repair,
    zero_deepseek_document_timings,
)


def test_zero_deepseek_document_timings():
    t: dict = {}
    zero_deepseek_document_timings(t, needs_deepseek=False)
    assert t["document_needs_deepseek_ocr"] is False
    assert t["deepseek_skipped_preflight"] is True
    assert t["deepseek_load"] == 0.0
    assert t["deepseek_warmup_wait_seconds"] == 0.0
    assert t["deepseek_load_count_delta"] == 0


def test_deepseek_critical_path_sums_waits():
    t = {
        "deepseek_skipped_preflight": False,
        "deepseek_warmup_wait_seconds": 10.0,
        "deepseek_existing_load_wait_seconds": 5.0,
        "deepseek_load_rpc_wait_seconds": 2.0,
        "deepseek_blocking_load": 3.0,
        "model_cold_start": 0.0,
    }
    assert deepseek_critical_path_seconds(t) == 20.0


def test_skipped_preflight_critical_path_counts_repair_cold_start():
    t = {
        "deepseek_skipped_preflight": True,
        "model_cold_start": 59.0,
        "recovery_cold_start_seconds": 12.5,
    }
    assert deepseek_critical_path_seconds(t) == 12.5


def test_deepseek_critical_path_dedupes_model_load():
    t = {
        "deepseek_skipped_preflight": False,
        "deepseek_warmup_wait_seconds": 10.0,
        "deepseek_blocking_load": 18.0,
        "model_cold_start": 18.0,
    }
    assert deepseek_critical_path_seconds(t) == 28.0


def test_finalize_skipped_does_not_join():
    thread = MagicMock()
    thread.is_alive.return_value = True
    client = MagicMock()
    client.health.return_value = {"model_loaded": False, "load_count": 0}
    timings: dict = {"deepseek_skipped_preflight": True}
    finalize_deepseek_timings_after_repair(
        timings=timings,
        warmup_thread=thread,
        docling_span=(1.0, 2.0),
        client=client,
    )
    thread.join.assert_not_called()
    assert "deepseek_worker_background" in timings


def test_ensure_deepseek_records_wait_fields():
    client = MagicMock()
    client.load_timeout_seconds = 60.0
    # 模拟：进程活着且正在 MODEL_LOADING → wait 后就绪，不调 load()
    client.health.side_effect = [
        {"ok": True, "load_count": 0, "model_loaded": False, "state": "STARTING", "model_state": "MODEL_LOADING"},
        {"ok": True, "load_count": 0, "model_loaded": False, "state": "STARTING", "model_state": "MODEL_LOADING"},
        {"ok": True, "load_count": 1, "model_loaded": True, "state": "READY", "model_state": "MODEL_READY"},
        {"ok": True, "load_count": 1, "model_loaded": True, "state": "READY", "model_state": "MODEL_READY"},
    ]
    client.wait_for_model_loaded.return_value = True
    rt = MagicMock()
    rt.model_load_seconds = 0.0
    rt.blocking_load_seconds = 0.0
    rt.load_overlap_seconds = 0.0
    rt.to_dict.return_value = {}
    client.run_timings = rt
    client.worker_lifetime.to_dict.return_value = {}
    thread = MagicMock()
    thread.is_alive.return_value = False
    timings: dict = {}
    msgs: list[str] = []

    ensure_deepseek_before_repair(
        client=client,
        warmup_thread=thread,
        docling_span=None,
        timings=timings,
        progress=msgs.append,
    )
    assert timings["document_needs_deepseek_ocr"] is True
    assert timings["deepseek_warmup_wait_seconds"] == 0.0
    assert timings["deepseek_load_count_delta"] == 1
    client.load.assert_not_called()
    client.wait_for_model_loaded.assert_called_once()


def test_ensure_dead_worker_calls_load_not_idle_wait():
    client = MagicMock()
    client.load_timeout_seconds = 60.0
    client.health.side_effect = [
        {"ok": False, "error": "refused", "state": "STOPPED", "load_count": 0, "model_loaded": False},
        {"ok": False, "error": "refused", "state": "STOPPED", "load_count": 0, "model_loaded": False},
        {"ok": True, "load_count": 1, "model_loaded": True, "model_state": "MODEL_READY"},
        {"ok": True, "load_count": 1, "model_loaded": True, "model_state": "MODEL_READY"},
    ]
    rt = MagicMock()
    rt.model_load_seconds = 12.0
    rt.blocking_load_seconds = 12.0
    rt.load_overlap_seconds = 0.0
    rt.to_dict.return_value = {}
    client.run_timings = rt
    client.worker_lifetime.to_dict.return_value = {}
    thread = MagicMock()
    thread.is_alive.return_value = False
    timings: dict = {}

    ensure_deepseek_before_repair(
        client=client,
        warmup_thread=thread,
        docling_span=None,
        timings=timings,
        progress=lambda *_: None,
    )
    client.wait_for_model_loaded.assert_not_called()
    client.load.assert_called_once()
    assert timings["model_cold_start"] == 12.0


def test_document_needs_deepseek_no_placeholder():
    from app.formula.deepseek_preflight import document_needs_deepseek_ocr

    assert document_needs_deepseek_ocr("plain text only", None) is False


def test_document_needs_deepseek_placeholder_without_pdf():
    from app.formula.deepseek_preflight import document_needs_deepseek_ocr

    md = "before <!-- formula-not-decoded --> after"
    assert document_needs_deepseek_ocr(md, None) is True


def test_document_needs_deepseek_corrupt_display_without_not_decoded():
    from app.formula.deepseek_preflight import (
        document_needs_deepseek_ocr,
        markdown_has_corrupt_display_math,
    )

    md = "text\n$$F 1 & = garbage \\quad \\quad$$\nmore"
    assert markdown_has_corrupt_display_math(md) is True
    # 预检不据此阻塞；由 pipeline 在 repair 内按需 OCR
    assert document_needs_deepseek_ocr(md, None) is False


def test_document_needs_deepseek_spaced_docling_latex_not_blocking():
    from app.formula.deepseek_preflight import document_needs_deepseek_ocr

    md = r"$$T P R = \frac { T P } { T P + F N }$$"
    assert document_needs_deepseek_ocr(md, None) is False


def test_document_needs_deepseek_clean_display_only():
    from app.formula.deepseek_preflight import document_needs_deepseek_ocr

    md = r"$$E = mc^2$$"
    assert document_needs_deepseek_ocr(md, None) is False


def test_should_ensure_when_warmup_in_flight():
    from app.formula.deepseek_preflight import should_ensure_deepseek_before_repair

    assert (
        should_ensure_deepseek_before_repair("plain", None, warmup_in_flight=True) is True
    )


def test_should_ensure_corrupt_display_when_model_cold():
    from app.formula.deepseek_preflight import should_ensure_deepseek_before_repair

    md = "text\n$$F 1 & = garbage \\quad \\quad$$\nmore"
    assert should_ensure_deepseek_before_repair(md, None, model_loaded=False) is True
    assert should_ensure_deepseek_before_repair(md, None, model_loaded=True) is True


def test_clean_display_does_not_require_ensure():
    from app.formula.deepseek_preflight import should_ensure_deepseek_before_repair

    md = r"$$E = mc^2$$"
    assert should_ensure_deepseek_before_repair(md, None) is False
    md2 = r"$$T P R = \frac { T P } { T P + F N }$$"
    assert should_ensure_deepseek_before_repair(md2, None) is False
