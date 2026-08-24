# -*- coding: utf-8 -*-
"""Phase 5G：Worker Watchdog / 单式 hard timeout / restart once（无 GPU）。"""
from __future__ import annotations

import json
import socket
import threading
import time
from pathlib import Path

from app.formula.config import formula_config_for_deepseek_limited_production
from app.ocr.deepseek_worker_client import (
    DeepSeekWorkerClient,
    WorkerLifecycleState,
    WorkerSessionStats,
)


def _serve_fake_worker(
    port_holder: dict,
    *,
    behavior: str = "ok",
    call_log: list | None = None,
) -> threading.Thread:
    """极简行 JSON Worker：支持 sleep / cuda_error / ok。"""

    call_log = call_log if call_log is not None else []

    def _handle(conn: socket.socket) -> None:
        with conn:
            try:
                f = conn.makefile("rwb")
                while True:
                    line = f.readline()
                    if not line:
                        break
                    req = json.loads(line.decode("utf-8"))
                    method = str(req.get("method") or "")
                    params = req.get("params") or {}
                    call_log.append(method)
                    if method == "ping":
                        result = {"ok": True, "state": "READY", "model_loaded": True}
                    elif method == "health":
                        result = {
                            "ok": True,
                            "state": "READY",
                            "model_loaded": True,
                            "load_count": 1,
                        }
                    elif method == "load":
                        result = {
                            "ok": True,
                            "state": "READY",
                            "model_loaded": True,
                            "load_this_call": 0.01,
                            "load_count": 1,
                        }
                    elif method == "quit":
                        result = {"ok": True, "quit": True}
                    elif method == "recognize":
                        inject = str(params.get("inject_fault") or "")
                        n_rec = sum(1 for m in call_log if m == "recognize")
                        if behavior == "sleep_on_third" and n_rec == 3:
                            time.sleep(5.0)
                            result = {
                                "ok": False,
                                "success": False,
                                "error": "should_have_timed_out",
                                "state": "READY",
                                "elapsed_seconds": 5.0,
                            }
                        elif inject in {"sleep_60", "sleep"} or behavior == "always_sleep":
                            time.sleep(5.0)
                            result = {
                                "ok": False,
                                "success": False,
                                "error": "sleep_done",
                                "elapsed_seconds": 5.0,
                            }
                        elif inject in {"cuda_error", "cuda"} or behavior == "cuda_error":
                            result = {
                                "ok": False,
                                "success": False,
                                "error": "RuntimeError:CUDA error: injected",
                                "state": "UNHEALTHY",
                                "elapsed_seconds": 0.01,
                            }
                        elif behavior == "cuda_then_ok":
                            if n_rec <= 1:
                                result = {
                                    "ok": False,
                                    "success": False,
                                    "error": "RuntimeError:CUDA error: injected",
                                    "state": "UNHEALTHY",
                                    "elapsed_seconds": 0.01,
                                }
                            else:
                                result = {
                                    "ok": True,
                                    "success": True,
                                    "text": "x=1",
                                    "raw_output": "x=1",
                                    "state": "READY",
                                    "elapsed_seconds": 0.05,
                                    "metadata": {},
                                }
                        else:
                            result = {
                                "ok": True,
                                "success": True,
                                "text": "a+b",
                                "raw_output": "a+b",
                                "state": "READY",
                                "elapsed_seconds": 0.05,
                                "metadata": {"worker_elapsed_seconds": 0.05},
                            }
                    else:
                        result = {"ok": False, "error": f"unknown:{method}"}
                    out = {"id": req.get("id"), **result}
                    f.write((json.dumps(out) + "\n").encode("utf-8"))
                    f.flush()
                    if result.get("quit"):
                        break
            except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, OSError):
                return
    def _main() -> None:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", 0))
        port_holder["port"] = srv.getsockname()[1]
        srv.listen(8)
        port_holder["ready"].set()
        try:
            while not port_holder.get("stop"):
                srv.settimeout(0.3)
                try:
                    conn, _ = srv.accept()
                except socket.timeout:
                    continue
                threading.Thread(target=_handle, args=(conn,), daemon=True).start()
        finally:
            srv.close()

    port_holder["ready"] = threading.Event()
    port_holder["stop"] = False
    t = threading.Thread(target=_main, daemon=True)
    t.start()
    port_holder["ready"].wait(timeout=5)
    return t


def test_limited_production_timeout_is_30():
    cfg = formula_config_for_deepseek_limited_production()
    assert cfg.deepseek_formula_timeout_seconds == 30.0
    assert cfg.deepseek_slow_call_threshold_seconds == 20.0
    assert cfg.deepseek_timeout_deferred_retry is True
    assert cfg.deepseek_coverage_first is True


def test_worker_session_stats_dict():
    s = WorkerSessionStats(worker_timeout_count=1, kill_count=1)
    d = s.to_dict()
    assert d["worker_timeout_count"] == 1
    assert d["tail_latency_protected"] is True


def test_case_a_sleep_triggers_timeout_and_kill(tmp_path: Path):
    """Case A：sleep 超 formula_timeout → timeout → kill 计数 +1。"""
    port_holder: dict = {}
    _serve_fake_worker(port_holder, behavior="always_sleep")
    meta = tmp_path / "w.json"
    meta.write_text(
        json.dumps({"host": "127.0.0.1", "port": port_holder["port"], "pid": 0}),
        encoding="utf-8",
    )
    client = DeepSeekWorkerClient(
        host="127.0.0.1",
        port=int(port_holder["port"]),
        meta_path=meta,
        infer_timeout_seconds=1.0,
        load_timeout_seconds=5.0,
        allow_spawn=False,
    )
    assert client.ping()
    client.begin_document_session()
    t0 = time.perf_counter()
    r = client.recognize(image_b64="AAAA", mode="formula", inject_fault="sleep_60")
    wall = time.perf_counter() - t0
    assert r.get("ok") is False
    assert "timeout" in str(r.get("error") or "").lower()
    assert client.session_stats.worker_timeout_count >= 1
    assert client.session_stats.kill_count >= 1
    assert wall < 4.0
    port_holder["stop"] = True


def test_case_b_cuda_restart_once_then_disable(tmp_path: Path):
    """Case B：CUDA → restart once → 第二次失败 → session disable。"""
    port_holder: dict = {}
    call_log: list = []
    _serve_fake_worker(port_holder, behavior="cuda_error", call_log=call_log)
    meta = tmp_path / "w.json"
    meta.write_text(
        json.dumps({"host": "127.0.0.1", "port": port_holder["port"], "pid": 0}),
        encoding="utf-8",
    )
    client = DeepSeekWorkerClient(
        host="127.0.0.1",
        port=int(port_holder["port"]),
        meta_path=meta,
        infer_timeout_seconds=5.0,
        allow_spawn=False,
    )
    client.begin_document_session()
    assert client.ping()

    # 第一次：CUDA → kill + restart（fake 仍在 → restart 成功）
    r1 = client.recognize(image_b64="AA", inject_fault="cuda_error")
    assert r1.get("ok") is False
    assert "cuda" in str(r1.get("error") or "").lower()
    assert client._restart_used == 1
    assert client.session_stats.worker_unhealthy_count >= 1
    assert client.disabled is False

    # 第二次：再 CUDA → 预算耗尽 → DISABLED
    r2 = client.recognize(image_b64="AA", inject_fault="cuda_error")
    assert r2.get("ok") is False
    assert client.disabled is True
    assert client.lifecycle == WorkerLifecycleState.DISABLED

    # 后续直接拒绝
    r3 = client.recognize(image_b64="AA")
    assert "disabled" in str(r3.get("error") or "").lower()
    port_holder["stop"] = True
    del call_log


def test_slow_streak_triggers_restart_path(tmp_path: Path):
    port_holder: dict = {}
    _serve_fake_worker(port_holder, behavior="ok")
    meta = tmp_path / "w.json"
    meta.write_text(
        json.dumps({"host": "127.0.0.1", "port": port_holder["port"], "pid": 0}),
        encoding="utf-8",
    )
    client = DeepSeekWorkerClient(
        host="127.0.0.1",
        port=int(port_holder["port"]),
        meta_path=meta,
        slow_call_threshold_seconds=0.01,
        slow_call_restart_count=2,
        infer_timeout_seconds=10.0,
        allow_spawn=False,
    )
    client.begin_document_session()
    client.recognize(image_b64="AA")
    client.recognize(image_b64="AA")
    assert client.session_stats.worker_slow_call_count >= 2
    assert client._restart_used >= 1 or client.disabled
    port_holder["stop"] = True


def test_handle_formula_timeout_does_not_reuse_without_kill(tmp_path: Path):
    client = DeepSeekWorkerClient(
        host="127.0.0.1",
        port=1,  # 不可达，避免误 ping 到本机常驻 daemon
        meta_path=tmp_path / "m.json",
        infer_timeout_seconds=30.0,
        allow_spawn=False,
    )
    client.begin_document_session()
    r = client.handle_formula_timeout(detail="unit")
    assert "timeout" in str(r.get("error") or "")
    assert client.session_stats.worker_timeout_count == 1
    assert client.session_stats.kill_count >= 1
    assert client.disabled is True
    assert client.lifecycle == WorkerLifecycleState.DISABLED

def test_timeout_handler_idempotent_does_not_double_burn_restart(tmp_path: Path):
    """socket + ThreadPool 双触发不得二次耗尽 restart → 整篇 disabled。"""
    port_holder: dict = {}
    _serve_fake_worker(port_holder, behavior="ok")
    meta = tmp_path / "w.json"
    meta.write_text(
        json.dumps({"host": "127.0.0.1", "port": port_holder["port"], "pid": 0}),
        encoding="utf-8",
    )
    client = DeepSeekWorkerClient(
        host="127.0.0.1",
        port=int(port_holder["port"]),
        meta_path=meta,
        infer_timeout_seconds=5.0,
        allow_spawn=False,
    )
    client.begin_document_session()
    assert client.ping()

    client._handling_timeout = True
    client.lifecycle = WorkerLifecycleState.RESTARTING
    r2 = client.handle_formula_timeout(detail="executor_thread_timeout")
    assert (r2.get("metadata") or {}).get("watchdog") == "formula_hard_timeout_dedup"
    assert client._restart_used == 0
    assert client.session_stats.kill_count == 0
    assert client.disabled is False

    client._handling_timeout = False
    client.lifecycle = WorkerLifecycleState.READY
    r1 = client.handle_formula_timeout(detail="socket_timeout")
    assert "timeout" in str(r1.get("error") or "")
    assert client.session_stats.worker_timeout_count == 1
    port_holder["stop"] = True
