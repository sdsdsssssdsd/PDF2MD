"""Phase 5C/5G：主进程侧 DeepSeek 持久 Worker 客户端 + Watchdog。"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from app.ocr.deepseek_paths import DSOCR2_PYTHON, resolve_deepseek_model_name
from app.utils.paths import APP_ROOT, SCRIPTS_DIR

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18765
META_PATH = APP_ROOT / ".cache" / "deepseek_worker.json"
LOAD_TIMEOUT_SECONDS = 240.0
# Phase 5G：热路径单式 hard timeout（不再用 90s）
INFER_TIMEOUT_SECONDS = 30.0
START_TIMEOUT_SECONDS = 30.0
SLOW_CALL_THRESHOLD_SECONDS = 20.0
SLOW_CALL_RESTART_COUNT = 2


class WorkerLifecycleState(str, Enum):
    READY = "READY"
    BUSY = "BUSY"
    SUSPECT = "SUSPECT"
    UNHEALTHY = "UNHEALTHY"
    RESTARTING = "RESTARTING"
    DISABLED = "DISABLED"


@dataclass
class WorkerTimings:
    """兼容旧字段：进程侧历史 load（勿直接当作本 run 成本）。"""

    warmup_requested_at: float | None = None
    load_started_at: float | None = None
    load_finished_at: float | None = None
    load_seconds: float = 0.0
    load_overlap_seconds: float = 0.0
    blocking_load_seconds: float = 0.0
    via: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "warmup_requested_at": self.warmup_requested_at,
            "load_started_at": self.load_started_at,
            "load_finished_at": self.load_finished_at,
            "load_seconds": round(self.load_seconds, 3),
            "load_overlap_seconds": round(self.load_overlap_seconds, 3),
            "blocking_load_seconds": round(self.blocking_load_seconds, 3),
            "via": self.via,
        }


@dataclass
class RunDeepSeekTiming:
    """单次文档转换的 DeepSeek 成本（与 Worker 历史隔离）。"""

    model_load_seconds: float = 0.0
    blocking_load_seconds: float = 0.0
    load_overlap_seconds: float = 0.0
    load_started_at: float | None = None
    load_finished_at: float | None = None
    load_stages: dict[str, Any] = field(default_factory=dict)
    reused_warm_worker: bool = False
    model_was_ready: bool = False
    existing_load_wait_seconds: float = 0.0
    waited_for_existing_load: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_load_seconds": round(self.model_load_seconds, 3),
            "blocking_load_seconds": round(self.blocking_load_seconds, 3),
            "load_overlap_seconds": round(self.load_overlap_seconds, 3),
            "load_started_at": self.load_started_at,
            "load_finished_at": self.load_finished_at,
            "load_stages": self.load_stages,
            "reused_warm_worker": self.reused_warm_worker,
            "model_was_ready": self.model_was_ready,
            "existing_load_wait_seconds": round(self.existing_load_wait_seconds, 3),
            "waited_for_existing_load": self.waited_for_existing_load,
        }


@dataclass
class WorkerLifetimeInfo:
    """Worker 守护进程 lifetime（跨 GUI / 跨文档）。"""

    process_state: str = "STOPPED"
    model_state: str = "MODEL_UNLOADED"
    model_loaded: bool = False
    model_age_seconds: float = 0.0
    process_uptime_seconds: float = 0.0
    lifetime_load_seconds: float = 0.0
    load_count: int = 0
    survive_gui_exit: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "process_state": self.process_state,
            "model_state": self.model_state,
            "model_loaded": self.model_loaded,
            "model_age_seconds": round(self.model_age_seconds, 1),
            "process_uptime_seconds": round(self.process_uptime_seconds, 1),
            "lifetime_load_seconds": round(self.lifetime_load_seconds, 3),
            "load_count": self.load_count,
            "survive_gui_exit": self.survive_gui_exit,
        }


@dataclass
class WorkerSessionStats:
    """单文档会话内 Worker 看门狗遥测（Phase 5G）。"""

    worker_restart_count: int = 0
    worker_timeout_count: int = 0
    worker_slow_call_count: int = 0
    worker_unhealthy_count: int = 0
    max_formula_inference_seconds: float = 0.0
    deferred_retry_count: int = 0
    kill_count: int = 0
    tail_latency_protected: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "worker_restart_count": self.worker_restart_count,
            "worker_timeout_count": self.worker_timeout_count,
            "worker_slow_call_count": self.worker_slow_call_count,
            "worker_unhealthy_count": self.worker_unhealthy_count,
            "max_formula_inference_seconds": round(self.max_formula_inference_seconds, 3),
            "deferred_retry_count": self.deferred_retry_count,
            "kill_count": self.kill_count,
            "tail_latency_protected": self.tail_latency_protected,
        }


@dataclass
class DeepSeekWorkerClient:
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    meta_path: Path = META_PATH
    load_timeout_seconds: float = LOAD_TIMEOUT_SECONDS
    infer_timeout_seconds: float = INFER_TIMEOUT_SECONDS
    slow_call_threshold_seconds: float = SLOW_CALL_THRESHOLD_SECONDS
    slow_call_restart_count: int = SLOW_CALL_RESTART_COUNT
    max_document_restarts: int = 1
    # 单测可关：禁止 ensure_started 拉起真实 dsocr2 进程
    allow_spawn: bool = True
    # Phase 5I：GUI 退出不杀 Worker；仅显式 quit_daemon / force_kill
    survive_gui_exit: bool = True
    _proc: subprocess.Popen | None = field(default=None, repr=False)
    _lock: threading.RLock = field(default_factory=threading.RLock)
    _req_id: int = 0
    _restart_used: int = 0
    _slow_streak: int = 0
    lifecycle: WorkerLifecycleState = WorkerLifecycleState.READY
    timings: WorkerTimings = field(default_factory=WorkerTimings)
    run_timings: RunDeepSeekTiming = field(default_factory=RunDeepSeekTiming)
    worker_lifetime: WorkerLifetimeInfo = field(default_factory=WorkerLifetimeInfo)
    session_stats: WorkerSessionStats = field(default_factory=WorkerSessionStats)
    disabled: bool = False
    last_error: str = ""
    _handling_timeout: bool = False

    def reset_session_stats(self) -> None:
        """新文档开始时清零会话计数；不重置 restart 预算（同进程可跨文档）。"""
        self.session_stats = WorkerSessionStats(
            tail_latency_protected=self.infer_timeout_seconds > 0
        )
        self._slow_streak = 0

    def begin_document_session(self) -> None:
        """文档级会话：清零 restart 预算、慢调用 streak、本 run 遥测。"""
        with self._lock:
            self._restart_used = 0
            self._slow_streak = 0
            self._handling_timeout = False
            self.disabled = False
            if self.lifecycle == WorkerLifecycleState.DISABLED:
                self.lifecycle = WorkerLifecycleState.READY
            self.session_stats = WorkerSessionStats(
                tail_latency_protected=self.infer_timeout_seconds > 0
            )
            self.run_timings = RunDeepSeekTiming()
            self.last_error = ""
        # 探测已有 daemon 是否暖机（写入 run_timings.model_was_ready）
        try:
            h = self.health()
            self._refresh_lifetime_from_health(h)
            if h.get("ok") and h.get("model_loaded"):
                self.run_timings.model_was_ready = True
                self.run_timings.reused_warm_worker = True
        except Exception:
            pass

    def _next_id(self) -> int:
        self._req_id += 1
        return self._req_id

    def _read_meta(self) -> dict[str, Any] | None:
        if not self.meta_path.is_file():
            return None
        try:
            return json.loads(self.meta_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _rpc(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float = 60.0,
    ) -> dict[str, Any]:
        if self.disabled:
            return {"ok": False, "error": "worker_session_disabled"}
        host, port = self.host, self.port
        meta = self._read_meta()
        if meta:
            host = str(meta.get("host") or host)
            port = int(meta.get("port") or port)
        req = {"id": self._next_id(), "method": method, "params": params or {}}
        raw = (json.dumps(req, ensure_ascii=False) + "\n").encode("utf-8")
        with socket.create_connection((host, port), timeout=min(10.0, timeout)) as sock:
            sock.settimeout(timeout)
            sock.sendall(raw)
            buf = b""
            while b"\n" not in buf:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                buf += chunk
        if not buf:
            return {"ok": False, "error": "empty_response"}
        line = buf.split(b"\n", 1)[0]
        return json.loads(line.decode("utf-8"))

    def ping(self) -> bool:
        try:
            r = self._rpc("ping", timeout=3.0)
            return bool(r.get("ok"))
        except Exception:
            return False

    def health(self) -> dict[str, Any]:
        try:
            return self._rpc("health", timeout=5.0)
        except Exception as e:
            return {"ok": False, "error": str(e), "state": "STOPPED"}

    def _refresh_lifetime_from_health(self, h: dict[str, Any] | None) -> None:
        if not h:
            return
        self.worker_lifetime = WorkerLifetimeInfo(
            process_state=str(h.get("process_state") or ("PROCESS_READY" if h.get("ok") else "STOPPED")),
            model_state=str(
                h.get("model_state")
                or ("MODEL_READY" if h.get("model_loaded") else "MODEL_UNLOADED")
            ),
            model_loaded=bool(h.get("model_loaded")),
            model_age_seconds=float(h.get("model_age_seconds") or 0),
            process_uptime_seconds=float(h.get("process_uptime_seconds") or 0),
            lifetime_load_seconds=float(h.get("load_seconds") or 0),
            load_count=int(h.get("load_count") or 0),
            survive_gui_exit=bool(h.get("survive_gui_exit", True)),
        )

    def _spawn_creationflags(self) -> int:
        """Windows：脱离 GUI Job，GUI 退出后 Worker 仍存活。"""
        if os.name != "nt":
            return 0
        # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS
        flags = 0x08000000 | 0x00000200 | 0x00000008
        return flags

    def _spawn(self) -> None:
        py = DSOCR2_PYTHON
        server = SCRIPTS_DIR / "deepseek_ocr_worker_server.py"
        if not py.is_file() or not server.is_file():
            raise RuntimeError("dsocr2_worker_assets_missing")
        self.meta_path.parent.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["PYTHONPATH"] = str(APP_ROOT) + (
            os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
        )
        env["DEEPSEEK_WORKER_HOST"] = self.host
        env["DEEPSEEK_WORKER_PORT"] = str(self.port)
        env["DEEPSEEK_WORKER_META"] = str(self.meta_path)
        # Phase 5I：默认 60min unload；进程不因 idle 退出
        env.setdefault("DEEPSEEK_WORKER_IDLE_UNLOAD_SECONDS", str(60 * 60))
        env.setdefault("DEEPSEEK_WORKER_IDLE_SHUTDOWN_SECONDS", "0")
        flags = self._spawn_creationflags()
        kwargs: dict[str, Any] = {
            "cwd": str(APP_ROOT),
            "env": env,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "stdin": subprocess.DEVNULL,
        }
        if os.name == "nt":
            kwargs["creationflags"] = flags
            # 再试带 BREAKAWAY（部分环境需要才能脱离 Job）
            try:
                self._proc = subprocess.Popen(
                    [str(py), "-u", str(server)],
                    creationflags=flags | 0x01000000,  # CREATE_BREAKAWAY_FROM_JOB
                    **{k: v for k, v in kwargs.items() if k != "creationflags"},
                )
            except OSError:
                self._proc = subprocess.Popen(
                    [str(py), "-u", str(server)], **kwargs
                )
        else:
            kwargs["start_new_session"] = True
            self._proc = subprocess.Popen([str(py), "-u", str(server)], **kwargs)

    def ensure_started(self, *, timeout: float = START_TIMEOUT_SECONDS) -> bool:
        with self._lock:
            if self.disabled:
                return False
            if self.ping():
                if self.lifecycle not in (
                    WorkerLifecycleState.BUSY,
                    WorkerLifecycleState.RESTARTING,
                ):
                    self.lifecycle = WorkerLifecycleState.READY
                return True
            if not self.allow_spawn:
                self.last_error = "spawn_disabled"
                return False
            try:
                self._spawn()
            except Exception as e:
                self.last_error = str(e)
                return False
            t0 = time.time()
            while time.time() - t0 < timeout:
                if self.ping():
                    self.lifecycle = WorkerLifecycleState.READY
                    return True
                time.sleep(0.2)
            self.last_error = "worker_start_timeout"
            return False

    def wait_for_model_loaded(
        self, *, timeout: float | None = None, poll: float = 0.5
    ) -> bool:
        """等待 Worker 侧 load 完成（避免客户端 RPC 超时后重复 load）。"""
        t0 = time.time()
        deadline = t0 + float(timeout or self.load_timeout_seconds)
        while time.time() < deadline:
            h = self.health()
            if bool(h.get("model_loaded")):
                self._refresh_lifetime_from_health(h)
                self.run_timings.existing_load_wait_seconds += time.time() - t0
                return True
            state = str(h.get("state") or "")
            model_state = str(h.get("model_state") or "")
            if model_state == "MODEL_LOADING" or state in {"BUSY", "STARTING"}:
                time.sleep(poll)
                continue
            if not self.ping():
                self.run_timings.existing_load_wait_seconds += time.time() - t0
                return False
            time.sleep(poll)
        ok = bool(self.health().get("model_loaded"))
        self.run_timings.existing_load_wait_seconds += time.time() - t0
        return ok

    def load(
        self, *, model_name: str | None = None, parallel_span: tuple[float, float] | None = None
    ) -> dict[str, Any]:
        """加载模型。parallel_span=(docling_start, docling_end) 用于算 overlap。

        Phase 5I：本 run 成本写入 run_timings；lifetime 写入 worker_lifetime。
        暖机复用时 model_load_seconds=0，禁止把历史 load 冒充本 run。
        """
        if not self.ensure_started():
            return {"ok": False, "error": self.last_error or "worker_not_started"}
        pre = self.health()
        self._refresh_lifetime_from_health(pre)
        already = bool(pre.get("model_loaded"))
        if not already:
            model_state = str(pre.get("model_state") or "")
            state = str(pre.get("state") or "")
            if model_state == "MODEL_LOADING" or state in {"BUSY", "STARTING"}:
                if self.wait_for_model_loaded(timeout=self.load_timeout_seconds):
                    pre = self.health()
                    self._refresh_lifetime_from_health(pre)
                    already = bool(pre.get("model_loaded"))
                    if already:
                        self.run_timings.reused_warm_worker = True
                        self.run_timings.model_was_ready = True
                        self.run_timings.waited_for_existing_load = True
                        self.run_timings.model_load_seconds = 0.0
                        self.run_timings.blocking_load_seconds = 0.0
                        self.run_timings.load_overlap_seconds = 0.0
                        self.timings.via = "persistent_worker"
                        return {
                            "ok": True,
                            "model_loaded": True,
                            "load_this_call": 0.0,
                            "load_seconds": float(pre.get("load_seconds") or 0.0),
                            "load_stages": pre.get("load_stages") or {"cache_hit": True},
                            "waited_for_existing": True,
                        }
        self.run_timings.waited_for_existing_load = False
        self.run_timings.load_started_at = time.time()
        self.timings.load_started_at = self.run_timings.load_started_at
        try:
            r = self._rpc(
                "load",
                {"model_name": model_name or resolve_deepseek_model_name()},
                timeout=self.load_timeout_seconds,
            )
        except Exception as e:
            self.last_error = str(e)
            r = {"ok": False, "error": str(e)}
        self.run_timings.load_finished_at = time.time()
        self.timings.load_finished_at = self.run_timings.load_finished_at
        this_call = float(r.get("load_this_call") or 0.0)
        stages = r.get("load_stages") if isinstance(r.get("load_stages"), dict) else {}
        self.run_timings.load_stages = dict(stages or {})
        # 本 run：仅计本次实际加载
        self.run_timings.model_load_seconds = this_call if this_call > 0.05 else 0.0
        self.run_timings.reused_warm_worker = already or this_call <= 0.05
        self.run_timings.model_was_ready = already
        # 兼容旧 timings：lifetime 累计值仍可查，但文档面板应读 run_timings
        lifetime_load = float(r.get("load_seconds") or this_call or 0.0)
        self.timings.load_seconds = lifetime_load
        self.timings.via = "persistent_worker"
        overlap = 0.0
        if (
            parallel_span
            and self.run_timings.load_started_at
            and self.run_timings.load_finished_at
            and this_call > 0.05
        ):
            ds, de = parallel_span
            lo = max(self.run_timings.load_started_at, ds)
            hi = min(self.run_timings.load_finished_at, de)
            overlap = max(0.0, hi - lo)
        self.run_timings.load_overlap_seconds = overlap if this_call > 0.05 else 0.0
        self.run_timings.blocking_load_seconds = max(
            0.0, self.run_timings.model_load_seconds - self.run_timings.load_overlap_seconds
        )
        self.timings.load_overlap_seconds = self.run_timings.load_overlap_seconds
        self.timings.blocking_load_seconds = self.run_timings.blocking_load_seconds
        self._refresh_lifetime_from_health(self.health() if r.get("ok") else pre)
        if not r.get("ok"):
            self.last_error = str(r.get("error") or "load_failed")
            self._recover_unhealthy(r)
        return r

    def recognize(
        self,
        *,
        image_b64: str,
        mode: str = "formula",
        prompt: str | None = None,
        inject_fault: str | None = None,
    ) -> dict[str, Any]:
        if self.disabled or self.lifecycle == WorkerLifecycleState.DISABLED:
            return {
                "ok": False,
                "error": "worker_session_disabled",
                "success": False,
                "state": WorkerLifecycleState.DISABLED.value,
            }
        if not self.ensure_started():
            return {
                "ok": False,
                "error": self.last_error or "worker_not_started",
                "success": False,
            }

        health = self.health()
        model_loaded = bool(health.get("model_loaded"))
        rpc_timeout = float(self.infer_timeout_seconds)
        if not model_loaded:
            # 冷加载：允许 load + infer；仍用 hard ceiling 防止无限挂死
            rpc_timeout = float(self.load_timeout_seconds) + float(self.infer_timeout_seconds)

        params: dict[str, Any] = {
            "image_b64": image_b64,
            "mode": mode,
            "prompt": prompt,
            "model_name": resolve_deepseek_model_name(),
        }
        if inject_fault:
            params["inject_fault"] = inject_fault

        with self._lock:
            self.lifecycle = WorkerLifecycleState.BUSY
        t0 = time.perf_counter()
        try:
            r = self._rpc("recognize", params, timeout=rpc_timeout)
        except (socket.timeout, TimeoutError) as e:
            return self.handle_formula_timeout(detail=str(e) or "socket_timeout")
        except OSError as e:
            # 连接被对端掐断 / 进程已死
            self.last_error = str(e)
            return self.handle_formula_timeout(detail=f"os_error:{e}")
        except Exception as e:
            self.last_error = str(e)
            with self._lock:
                if self.lifecycle == WorkerLifecycleState.BUSY:
                    self.lifecycle = WorkerLifecycleState.READY
            r = {"ok": False, "error": str(e), "success": False}

        wall = time.perf_counter() - t0
        elapsed = float(r.get("elapsed_seconds") or wall)
        # Phase 7.1A：冷启动分账兜底——若 Worker 未回传 load，用墙钟残差估计
        if isinstance(r, dict) and not model_loaded:
            meta = dict(r.get("metadata") or {})
            reported_load = float(
                meta.get("cold_start_seconds") or meta.get("model_load_seconds") or 0.0
            )
            reported_infer = float(
                meta.get("ocr_inference_seconds")
                or meta.get("worker_elapsed_seconds")
                or 0.0
            )
            if reported_load < 0.5 and wall > reported_infer + 5.0:
                residual = max(0.0, wall - max(reported_infer, 0.0))
                meta["model_load_seconds"] = round(residual, 3)
                meta["cold_start_seconds"] = round(residual, 3)
                meta["cold_start_inferred"] = True
                r = dict(r)
                r["metadata"] = meta
                # 同步到本 run timings，避免 repair 吞掉冷启动
                if residual > 0.5:
                    self.run_timings.model_load_seconds = max(
                        float(self.run_timings.model_load_seconds or 0.0), residual
                    )
                    self.run_timings.blocking_load_seconds = max(
                        float(self.run_timings.blocking_load_seconds or 0.0), residual
                    )
                    self.run_timings.model_was_ready = False
                    self.run_timings.reused_warm_worker = False
            elif reported_load > 0.5:
                r = dict(r)
                r.setdefault("metadata", meta)
                self.run_timings.model_load_seconds = max(
                    float(self.run_timings.model_load_seconds or 0.0), reported_load
                )
                self.run_timings.model_was_ready = False
                self.run_timings.reused_warm_worker = False

        self.session_stats.max_formula_inference_seconds = max(
            self.session_stats.max_formula_inference_seconds, elapsed
        )
        err = str(r.get("error") or "")
        err_l = err.lower()
        state = str(r.get("state") or "")

        if "timeout" in err_l:
            return self.handle_formula_timeout(detail=err)

        if (not r.get("ok")) and (
            state == "UNHEALTHY"
            or any(x in err_l for x in ("cuda", "cublas", "runtimeerror", "oom"))
        ):
            self.session_stats.worker_unhealthy_count += 1
            recovered = self._recover_unhealthy(r)
            r = dict(r)
            r["worker_restarted"] = recovered
            r["lifecycle"] = self.lifecycle.value
            return r

        # 正常返回路径：慢调用 streak
        if model_loaded and elapsed > float(self.slow_call_threshold_seconds):
            self._slow_streak += 1
            self.session_stats.worker_slow_call_count += 1
            if self._slow_streak >= int(self.slow_call_restart_count):
                self._recover_unhealthy(
                    {"ok": False, "error": f"slow_call_streak:{self._slow_streak}", "state": "SUSPECT"}
                )
                self._slow_streak = 0
        else:
            self._slow_streak = 0

        with self._lock:
            if self.lifecycle == WorkerLifecycleState.BUSY:
                self.lifecycle = WorkerLifecycleState.READY
        r = dict(r)
        r["lifecycle"] = self.lifecycle.value
        return r

    def handle_formula_timeout(self, *, detail: str = "") -> dict[str, Any]:
        """单式 hard timeout：旧 Worker 必须销毁；restart once。

        幂等：socket timeout 与 Executor ThreadPool 兜底可能同时触发；
        第二次不得再耗 restart 预算，否则整篇 `worker_session_disabled`。
        """
        with self._lock:
            if (
                self._handling_timeout
                or self.lifecycle
                in (
                    WorkerLifecycleState.RESTARTING,
                    WorkerLifecycleState.DISABLED,
                )
            ):
                return {
                    "ok": False,
                    "success": False,
                    "error": f"timeout:{self.infer_timeout_seconds}s",
                    "state": self.lifecycle.value,
                    "worker_restarted": False,
                    "lifecycle": self.lifecycle.value,
                    "elapsed_seconds": float(self.infer_timeout_seconds),
                    "metadata": {
                        "ocr_inference_seconds": float(self.infer_timeout_seconds),
                        "watchdog": "formula_hard_timeout_dedup",
                        "detail": detail or "",
                    },
                }
            self._handling_timeout = True
            self.session_stats.worker_timeout_count += 1
            self.lifecycle = WorkerLifecycleState.SUSPECT
            self.last_error = detail or f"timeout:{self.infer_timeout_seconds}s"

        try:
            restarted = self._kill_and_restart(reason=f"timeout:{detail}")
            return {
                "ok": False,
                "success": False,
                "error": f"timeout:{self.infer_timeout_seconds}s",
                "state": self.lifecycle.value,
                "worker_restarted": restarted,
                "lifecycle": self.lifecycle.value,
                "elapsed_seconds": float(self.infer_timeout_seconds),
                "metadata": {
                    "ocr_inference_seconds": float(self.infer_timeout_seconds),
                    "watchdog": "formula_hard_timeout",
                    "worker_restarted": restarted,
                },
            }
        finally:
            with self._lock:
                self._handling_timeout = False

    def on_inference_timeout(self) -> None:
        """Executor ThreadPool 兜底超时回调（与 socket timeout 同路径，可幂等）。"""
        self.handle_formula_timeout(detail="executor_thread_timeout")

    def _kill_worker_process(self) -> None:
        """销毁当前 Worker（含 meta pid），不可复用卡死进程。"""
        self.session_stats.kill_count += 1
        # 先杀我们 spawn 的句柄
        if self._proc is not None:
            try:
                self._proc.kill()
            except Exception:
                pass
            try:
                self._proc.wait(timeout=3)
            except Exception:
                pass
            self._proc = None
        # 再按 meta pid 兜底（外部已存在的 worker）
        meta = self._read_meta()
        pid = int(meta.get("pid") or 0) if meta else 0
        if pid > 0:
            try:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/F", "/PID", str(pid), "/T"],
                        capture_output=True,
                        timeout=5,
                        check=False,
                    )
                else:
                    os.kill(pid, 9)
            except Exception:
                pass
        try:
            if self.meta_path.is_file():
                self.meta_path.unlink()
        except Exception:
            pass

    def _kill_and_restart(self, *, reason: str) -> bool:
        with self._lock:
            self.lifecycle = WorkerLifecycleState.RESTARTING
            can_restart = (
                self._restart_used < int(self.max_document_restarts)
                and not self.disabled
            )
            if can_restart:
                self._restart_used += 1

        # 无论是否还有 restart 预算，不可信进程必须先销毁
        self._kill_worker_process()
        time.sleep(0.4)

        if not can_restart:
            self.disabled = True
            self.lifecycle = WorkerLifecycleState.DISABLED
            self.last_error = f"restart_budget_exhausted:{reason}"
            return False

        self.session_stats.worker_restart_count += 1

        if not self.ensure_started():
            self.disabled = True
            self.lifecycle = WorkerLifecycleState.DISABLED
            self.last_error = f"restart_failed:{reason}"
            return False

        # 重启后预热 load（失败则 disable）
        lr = self.load()
        if not lr.get("ok"):
            self.disabled = True
            self.lifecycle = WorkerLifecycleState.DISABLED
            self.last_error = f"restart_load_failed:{lr.get('error')}"
            return False

        hr = self.health()
        if not hr.get("ok") and not hr.get("model_loaded"):
            self.disabled = True
            self.lifecycle = WorkerLifecycleState.DISABLED
            self.last_error = f"restart_unhealthy:{hr.get('error') or hr.get('state')}"
            return False

        with self._lock:
            self.lifecycle = WorkerLifecycleState.READY
            self._slow_streak = 0
        return True

    def _recover_unhealthy(self, last: dict[str, Any]) -> bool:
        """UNHEALTHY / CUDA / 慢调用 streak → kill + restart once。"""
        with self._lock:
            self.lifecycle = WorkerLifecycleState.UNHEALTHY
        return self._kill_and_restart(reason=str(last.get("error") or "unhealthy"))

    def _maybe_restart(self, last: dict[str, Any]) -> None:
        """兼容旧调用点。"""
        self._recover_unhealthy(last)

    def warmup_async(self, *, model_name: str | None = None) -> threading.Thread:
        global _WARMUP_THREAD
        self.timings.warmup_requested_at = time.time()
        with _WARMUP_LOCK:
            if _WARMUP_THREAD is not None and _WARMUP_THREAD.is_alive():
                return _WARMUP_THREAD
            try:
                h = self.health()
                if bool(h.get("model_loaded")) and str(h.get("model_state") or "") == "MODEL_READY":
                    t = threading.Thread(target=lambda: None, daemon=True, name="deepseek-warmup-noop")
                    t.start()
                    _WARMUP_THREAD = t
                    return t
            except Exception:
                pass

            def _run() -> None:
                self.load(model_name=model_name)

            t = threading.Thread(target=_run, daemon=True, name="deepseek-warmup")
            t.start()
            _WARMUP_THREAD = t
            return t

    def shutdown(self, *, force_kill: bool = False, quit_daemon: bool = False) -> None:
        """断开本进程客户端。

        默认 survive_gui_exit：不发 quit、不杀进程（Phase 5I）。
        quit_daemon=True 或 force_kill=True 才真正停掉 Worker。
        """
        should_stop = bool(force_kill or quit_daemon or not self.survive_gui_exit)
        if should_stop:
            try:
                if self.ping():
                    self._rpc("quit", timeout=3.0)
            except Exception:
                pass
            if force_kill or self._proc is not None:
                if force_kill:
                    self._kill_worker_process()
                elif self._proc is not None:
                    try:
                        self._proc.terminate()
                        self._proc.wait(timeout=5)
                    except Exception:
                        try:
                            self._proc.kill()
                        except Exception:
                            pass
                    self._proc = None
        else:
            # 仅丢弃本地句柄，daemon 继续跑
            self._proc = None

    def detach_client_only(self) -> None:
        """GUI 退出：只丢客户端，不碰 Worker。"""
        self.shutdown(force_kill=False, quit_daemon=False)


def prepare_document_worker_session(
    client: DeepSeekWorkerClient,
    *,
    max_restarts: int = 2,
    slow_call_threshold_floor: float = 28.0,
    slow_call_restart_floor: int = 4,
) -> None:
    """文档级 Worker 会话：清零 disable/restart 预算，放宽慢调用误杀。"""
    client.begin_document_session()
    client.max_document_restarts = max(int(client.max_document_restarts), int(max_restarts))
    client.slow_call_threshold_seconds = max(
        float(client.slow_call_threshold_seconds), float(slow_call_threshold_floor)
    )
    client.slow_call_restart_count = max(
        int(client.slow_call_restart_count), int(slow_call_restart_floor)
    )


def cooldown_between_batch_documents(
    client: DeepSeekWorkerClient | None = None,
    *,
    pause_seconds: float = 2.0,
) -> None:
    """批跑篇间冷却：重置文档会话预算，避免连跑雪崩。"""
    import time

    c = client or get_deepseek_worker_client()
    prepare_document_worker_session(c)
    if pause_seconds > 0:
        time.sleep(float(pause_seconds))


_CLIENT: DeepSeekWorkerClient | None = None
_CLIENT_LOCK = threading.Lock()
_WARMUP_THREAD: threading.Thread | None = None
_WARMUP_LOCK = threading.Lock()


def get_deepseek_worker_client() -> DeepSeekWorkerClient:
    global _CLIENT
    with _CLIENT_LOCK:
        if _CLIENT is None:
            _CLIENT = DeepSeekWorkerClient()
        return _CLIENT


def reset_deepseek_worker_client(*, kill_worker: bool = False) -> None:
    """默认只丢本地单例（Worker 常驻）。测试/显式停服传 kill_worker=True。"""
    global _CLIENT
    with _CLIENT_LOCK:
        if _CLIENT is not None:
            try:
                if kill_worker:
                    _CLIENT.shutdown(force_kill=True, quit_daemon=True)
                else:
                    _CLIENT.detach_client_only()
            except Exception:
                pass
        _CLIENT = None


def ensure_deepseek_daemon(*, warmup: bool = False) -> dict[str, Any]:
    """GUI/登录预热入口：ping 复用，没有才 spawn。"""
    client = get_deepseek_worker_client()
    ok = client.ensure_started()
    info = {"ok": ok, "ping": client.ping(), "error": client.last_error}
    if ok:
        h = client.health()
        client._refresh_lifetime_from_health(h)
        info["health"] = h
        info["worker"] = client.worker_lifetime.to_dict()
        if warmup and not h.get("model_loaded"):
            client.warmup_async()
            info["warmup_started"] = True
    return info
