# -*- coding: utf-8 -*-
"""Phase 5I：GUI-independent daemon / run timing 隔离。"""
from __future__ import annotations

from app.ocr.deepseek_worker_client import (
    DeepSeekWorkerClient,
    RunDeepSeekTiming,
    WorkerLifetimeInfo,
    reset_deepseek_worker_client,
)


def test_run_timing_defaults_zero_load():
    rt = RunDeepSeekTiming()
    d = rt.to_dict()
    assert d["model_load_seconds"] == 0.0
    assert d["reused_warm_worker"] is False


def test_shutdown_default_does_not_quit_when_survive(monkeypatch):
    client = DeepSeekWorkerClient(allow_spawn=False, survive_gui_exit=True)
    calls: list[str] = []

    def fake_rpc(method, params=None, timeout=60.0):
        calls.append(method)
        return {"ok": True}

    monkeypatch.setattr(client, "_rpc", fake_rpc)
    monkeypatch.setattr(client, "ping", lambda: True)
    client.shutdown(force_kill=False, quit_daemon=False)
    assert "quit" not in calls


def test_shutdown_quit_daemon_sends_quit(monkeypatch):
    client = DeepSeekWorkerClient(allow_spawn=False, survive_gui_exit=True)
    calls: list[str] = []

    def fake_rpc(method, params=None, timeout=60.0):
        calls.append(method)
        return {"ok": True, "quit": True}

    monkeypatch.setattr(client, "_rpc", fake_rpc)
    monkeypatch.setattr(client, "ping", lambda: True)
    monkeypatch.setattr(client, "_kill_worker_process", lambda: None)
    client.shutdown(force_kill=False, quit_daemon=True)
    assert "quit" in calls


def test_load_warm_reuse_zeros_run_cost(monkeypatch):
    client = DeepSeekWorkerClient(allow_spawn=False)
    client.begin_document_session()

    monkeypatch.setattr(client, "ensure_started", lambda **kw: True)
    monkeypatch.setattr(
        client,
        "health",
        lambda: {
            "ok": True,
            "model_loaded": True,
            "model_state": "MODEL_READY",
            "process_state": "PROCESS_READY",
            "load_seconds": 200.0,
            "load_count": 1,
            "model_age_seconds": 100.0,
        },
    )
    monkeypatch.setattr(
        client,
        "_rpc",
        lambda method, params=None, timeout=60.0: {
            "ok": True,
            "load_this_call": 0.0,
            "load_seconds": 200.0,
            "load_stages": {"cache_hit": True},
        },
    )
    r = client.load()
    assert r.get("ok") is True
    assert client.run_timings.model_load_seconds == 0.0
    assert client.run_timings.reused_warm_worker is True
    assert client.worker_lifetime.model_loaded is True
    # 旧字段仍可看 lifetime，但文档成本必须用 run_timings
    assert client.timings.load_seconds == 200.0


def test_reset_client_default_no_kill(monkeypatch):
    reset_deepseek_worker_client(kill_worker=False)
    from app.ocr import deepseek_worker_client as m

    c = m.get_deepseek_worker_client()
    killed = {"v": False}

    def boom(*a, **k):
        killed["v"] = True

    monkeypatch.setattr(c, "shutdown", boom)
    # get already created; reset without kill should call detach path
    # re-bind: replace instance method via module reset
    calls: list[tuple] = []

    class Fake:
        survive_gui_exit = True

        def shutdown(self, *, force_kill=False, quit_daemon=False):
            calls.append((force_kill, quit_daemon))

        def detach_client_only(self):
            calls.append(("detach",))

    with m._CLIENT_LOCK:
        m._CLIENT = Fake()  # type: ignore[assignment]
    reset_deepseek_worker_client(kill_worker=False)
    assert calls == [("detach",)] or calls == [(False, False)]


def test_spawn_flags_include_detached_on_windows():
    import os

    if os.name != "nt":
        return
    c = DeepSeekWorkerClient(allow_spawn=False)
    flags = c._spawn_creationflags()
    assert flags & 0x00000008  # DETACHED_PROCESS
    assert flags & 0x00000200  # CREATE_NEW_PROCESS_GROUP


def test_worker_lifetime_dict():
    info = WorkerLifetimeInfo(
        process_state="PROCESS_READY",
        model_state="MODEL_READY",
        model_loaded=True,
        model_age_seconds=12.3,
    )
    d = info.to_dict()
    assert d["model_state"] == "MODEL_READY"
    assert d["survive_gui_exit"] is True
