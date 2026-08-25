# -*- coding: utf-8 -*-
"""Phase 5C：持久化 DeepSeek OCR Worker（dsocr2 venv）。

协议：TCP 行分隔 JSON（localhost）。
方法：ping / health / load / recognize / unload / quit
"""
from __future__ import annotations

import base64
import io
import json
import os
import socket
import sys
import threading
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ocr.deepseek_paths import ensure_deepseek_hf_env

ensure_deepseek_hf_env()
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18765
# Phase 5I：默认 60min idle 才 unload 模型；进程默认不因 idle 退出（随 Windows session）
IDLE_UNLOAD_SECONDS = 60 * 60
IDLE_SHUTDOWN_SECONDS = 0.0  # 0 = 永不因 idle 杀进程
LOAD_TIMEOUT_HINT = 240.0


@dataclass
class WorkerRuntime:
    state: str = "STARTING"  # STARTING|READY|BUSY|UNHEALTHY|DISABLED
    model_state: str = "MODEL_UNLOADED"  # MODEL_LOADING|MODEL_READY|MODEL_UNLOADED
    process_state: str = "PROCESS_READY"
    model_loaded: bool = False
    load_seconds: float = 0.0
    load_count: int = 0
    load_stages: dict | None = None
    model_loaded_at: float = 0.0
    process_started_at: float = 0.0
    last_used: float = 0.0
    last_error: str = ""
    restart_budget: int = 1
    recognizer: Any = None
    lock: threading.RLock = None  # type: ignore

    def __post_init__(self) -> None:
        self.lock = threading.RLock()
        self.last_used = time.time()
        self.process_started_at = time.time()


RT = WorkerRuntime()


def _log(msg: str) -> None:
    print(f"[ds-worker] {msg}", flush=True, file=sys.stderr)


def _ensure_recognizer(model_name: str | None = None, **profile_overrides: Any) -> Any:
    from app.ocr.deepseek_ocr2 import DeepSeekOCR2Recognizer
    from app.ocr.deepseek_paths import resolve_deepseek_model_name
    from app.ocr.deepseek_profiles import (
        DEEPSEEK_FORMULA_PROFILE,
        DEEPSEEK_PAGE_PROFILE,
        DeepSeekOCRProfile,
    )

    with RT.lock:
        # profile 覆盖变化时重建（benchmark）
        want_key = (
            model_name or resolve_deepseek_model_name(),
            int(profile_overrides.get("max_new_tokens") or 0),
            bool(profile_overrides.get("crop_mode", DEEPSEEK_FORMULA_PROFILE.crop_mode)),
            int(profile_overrides.get("image_size") or DEEPSEEK_FORMULA_PROFILE.image_size),
        )
        if RT.recognizer is not None and getattr(RT, "profile_key", None) == want_key:
            return RT.recognizer

        formula = DEEPSEEK_FORMULA_PROFILE
        if profile_overrides:
            formula = DeepSeekOCRProfile(
                name="formula_fast_override",
                base_size=int(profile_overrides.get("base_size") or formula.base_size),
                image_size=int(profile_overrides.get("image_size") or formula.image_size),
                crop_mode=bool(
                    profile_overrides["crop_mode"]
                    if "crop_mode" in profile_overrides
                    else formula.crop_mode
                ),
                max_new_tokens=int(
                    profile_overrides.get("max_new_tokens") or formula.max_new_tokens
                ),
                save_results=False,
                eval_mode=True,
            )
        RT.recognizer = DeepSeekOCR2Recognizer(
            model_name=model_name or resolve_deepseek_model_name(),
            device="cuda:0",
            dtype="bf16",
            base_size=formula.base_size,
            image_size=formula.image_size,
            crop_mode=formula.crop_mode,
            allow_cpu=False,
            formula_profile=formula,
            page_profile=DEEPSEEK_PAGE_PROFILE,
            max_new_tokens=int(profile_overrides.get("max_new_tokens") or formula.max_new_tokens)
            if profile_overrides.get("max_new_tokens")
            else None,
        )
        RT.profile_key = want_key  # type: ignore[attr-defined]
        return RT.recognizer


RT = WorkerRuntime()
_load_cv = threading.Condition(RT.lock)


def _load_ready_response(*, load_this_call: float = 0.0, waited: bool = False) -> dict[str, Any]:
    return {
        "ok": True,
        "state": RT.state,
        "model_loaded": True,
        "model_state": RT.model_state,
        "process_state": RT.process_state,
        "load_seconds": RT.load_seconds,
        "load_count": RT.load_count,
        "load_this_call": load_this_call,
        "load_stages": RT.load_stages or {"cache_hit": True, "total": 0.0},
        "waited_for_existing": waited,
    }


def handle_load(params: dict[str, Any]) -> dict[str, Any]:
    with _load_cv:
        if RT.state == "DISABLED":
            return {"ok": False, "error": "worker_disabled", "state": RT.state}
        if RT.model_loaded and RT.model_state == "MODEL_READY":
            return _load_ready_response(load_this_call=0.0, waited=False)
        while RT.model_state == "MODEL_LOADING":
            if not _load_cv.wait(timeout=LOAD_TIMEOUT_HINT):
                return {
                    "ok": False,
                    "error": "load_wait_timeout",
                    "state": RT.state,
                    "model_state": RT.model_state,
                }
            if RT.model_loaded and RT.model_state == "MODEL_READY":
                return _load_ready_response(load_this_call=0.0, waited=True)
        RT.state = "STARTING"
        RT.model_state = "MODEL_LOADING"
        RT.process_state = "PROCESS_READY"
    try:
        rec = _ensure_recognizer(params.get("model_name"))
        t0 = time.perf_counter()
        load_s = float(rec._ensure_loaded())
        stages = dict(getattr(type(rec), "_last_load_stages", {}) or {})
        with _load_cv:
            RT.model_loaded = True
            RT.model_state = "MODEL_READY"
            if load_s > 0.5:
                RT.load_seconds = load_s
                RT.load_count += 1
                RT.load_stages = stages
                RT.model_loaded_at = time.time()
            elif RT.load_count == 0:
                RT.load_count = 1
                RT.load_seconds = time.perf_counter() - t0
                RT.load_stages = stages
                RT.model_loaded_at = time.time()
            RT.state = "READY"
            RT.last_used = time.time()
            RT.last_error = ""
            _load_cv.notify_all()
        return {
            "ok": True,
            "state": RT.state,
            "model_loaded": True,
            "model_state": RT.model_state,
            "process_state": RT.process_state,
            "load_seconds": RT.load_seconds,
            "load_count": RT.load_count,
            "load_this_call": load_s,
            "load_stages": stages,
            "waited_for_existing": False,
        }
    except Exception as e:
        with _load_cv:
            RT.state = "UNHEALTHY"
            RT.model_state = "MODEL_UNLOADED"
            RT.model_loaded = False
            RT.last_error = f"{type(e).__name__}:{e}"
            _load_cv.notify_all()
        _log(f"load failed: {RT.last_error}")
        return {"ok": False, "error": RT.last_error, "state": RT.state, "model_state": RT.model_state}


def handle_recognize(params: dict[str, Any]) -> dict[str, Any]:
    from app.ocr import OCRMode

    with RT.lock:
        if RT.state == "DISABLED":
            return {"ok": False, "error": "worker_disabled", "state": RT.state}
        if RT.state == "UNHEALTHY":
            return {"ok": False, "error": f"worker_unhealthy:{RT.last_error}", "state": RT.state}
        RT.state = "BUSY"

    # Phase 5G 故障注入（仅测试 / 显式 params；生产客户端不传）
    inject = str(params.get("inject_fault") or os.environ.get("DEEPSEEK_WORKER_INJECT") or "").strip()
    if inject in {"sleep_60", "sleep60", "sleep"}:
        _log("inject_fault=sleep_60")
        time.sleep(60.0)
        with RT.lock:
            RT.state = "READY"
        return {
            "ok": False,
            "success": False,
            "error": "timeout:injected_sleep_finished",
            "state": RT.state,
            "elapsed_seconds": 60.0,
            "metadata": {"inject_fault": "sleep_60"},
        }
    if inject in {"cuda_error", "cuda", "runtime_error"}:
        with RT.lock:
            RT.state = "UNHEALTHY"
            RT.last_error = "RuntimeError:CUDA error: injected"
        _log("inject_fault=cuda_error")
        return {
            "ok": False,
            "success": False,
            "error": RT.last_error,
            "state": RT.state,
            "elapsed_seconds": 0.05,
            "metadata": {"inject_fault": "cuda_error"},
        }

    # 未 load 则自动 load（必须把 load_this_call 透传到 recognize metadata，
    # 否则冷启动会被算进 repair/actual，telemetry 显示 model_load=0）
    auto_load_s = 0.0
    if not RT.model_loaded:
        lr = handle_load({"model_name": params.get("model_name")})
        if not lr.get("ok"):
            return lr
        auto_load_s = float(lr.get("load_this_call") or 0.0)

    try:
        from PIL import Image

        b64 = params.get("image_b64") or ""
        raw = base64.b64decode(b64)
        image = Image.open(io.BytesIO(raw)).convert("RGB")
        mode_s = str(params.get("mode") or "formula")
        mode = OCRMode.FORMULA if mode_s == "formula" else (
            OCRMode.PAGE if mode_s == "page" else OCRMode.REGION
        )
        prompt = params.get("prompt")
        ov = {
            k: v
            for k, v in {
                "max_new_tokens": params.get("max_new_tokens"),
                "crop_mode": params.get("crop_mode"),
                "image_size": params.get("image_size"),
                "base_size": params.get("base_size"),
            }.items()
            if v is not None
        }
        rec = _ensure_recognizer(params.get("model_name"), **ov)
        t0 = time.perf_counter()
        doc_res = rec.recognize(image, mode=mode, prompt=prompt)
        elapsed = time.perf_counter() - t0
        with RT.lock:
            RT.last_used = time.time()
            RT.state = "READY"
        meta = dict(doc_res.metadata or {})
        meta["worker_elapsed_seconds"] = round(elapsed, 3)
        meta["worker_model_loaded"] = True
        meta["worker_load_count"] = RT.load_count
        if auto_load_s > 0.05:
            # recognizer 侧此时通常已 loaded，model_load_seconds 会是 0；显式补上
            meta["model_load_seconds"] = round(
                max(float(meta.get("model_load_seconds") or 0.0), auto_load_s), 3
            )
            meta["cold_start_seconds"] = round(auto_load_s, 3)
            meta["auto_load_before_recognize"] = True
        try:
            import torch

            if torch.cuda.is_available():
                free_b, total_b = torch.cuda.mem_get_info(0)
                meta["gpu_allocated_mb"] = round(
                    torch.cuda.memory_allocated(0) / (1024**2), 1
                )
                meta["gpu_reserved_mb"] = round(
                    torch.cuda.memory_reserved(0) / (1024**2), 1
                )
                meta["gpu_free_mb"] = round(free_b / (1024**2), 1)
                meta["gpu_total_mb"] = round(total_b / (1024**2), 1)
        except Exception:
            pass
        if not doc_res.success and doc_res.error:
            err_l = (doc_res.error or "").lower()
            if any(x in err_l for x in ("cuda", "oom", "runtimeerror", "cublas")):
                with RT.lock:
                    RT.state = "UNHEALTHY"
                    RT.last_error = doc_res.error or "recognize_failed"
        return {
            "ok": bool(doc_res.success),
            "state": RT.state,
            "text": doc_res.text or "",
            "raw_output": doc_res.raw_output or "",
            "markdown": doc_res.markdown,
            "success": bool(doc_res.success),
            "error": doc_res.error,
            "elapsed_seconds": doc_res.elapsed_seconds,
            "metadata": meta,
            "mode": doc_res.mode,
            "recognizer": doc_res.recognizer,
        }
    except Exception as e:
        err = f"{type(e).__name__}:{e}"
        with RT.lock:
            RT.state = "UNHEALTHY"
            RT.last_error = err
        _log(f"recognize failed: {err}\n{traceback.format_exc()}")
        return {"ok": False, "error": err, "state": RT.state}


def handle_health(_: dict[str, Any]) -> dict[str, Any]:
    idle = time.time() - RT.last_used
    model_age = (
        (time.time() - RT.model_loaded_at) if RT.model_loaded and RT.model_loaded_at else 0.0
    )
    return {
        "ok": RT.state in {"READY", "STARTING", "BUSY"},
        "state": RT.state,
        "process_state": RT.process_state or "PROCESS_READY",
        "model_state": RT.model_state
        or ("MODEL_READY" if RT.model_loaded else "MODEL_UNLOADED"),
        "model_loaded": RT.model_loaded,
        "load_seconds": RT.load_seconds,
        "load_count": RT.load_count,
        "load_stages": RT.load_stages or {},
        "idle_seconds": round(idle, 1),
        "model_age_seconds": round(model_age, 1),
        "process_uptime_seconds": round(time.time() - (RT.process_started_at or time.time()), 1),
        "last_error": RT.last_error,
        "restart_budget": RT.restart_budget,
        "survive_gui_exit": True,
    }


def handle_unload(_: dict[str, Any]) -> dict[str, Any]:
    with RT.lock:
        try:
            from app.ocr.deepseek_ocr2 import DeepSeekOCR2Recognizer

            DeepSeekOCR2Recognizer.reset_class_model()
        except Exception:
            pass
        RT.recognizer = None
        RT.model_loaded = False
        RT.model_state = "MODEL_UNLOADED"
        RT.state = "READY"
        RT.last_error = ""
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass
    return {"ok": True, "state": RT.state, "model_loaded": False}


def handle_ping(_: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "state": RT.state, "model_loaded": RT.model_loaded}


def dispatch(method: str, params: dict[str, Any]) -> dict[str, Any]:
    if method == "ping":
        return handle_ping(params)
    if method == "health":
        return handle_health(params)
    if method == "load":
        return handle_load(params)
    if method == "recognize":
        return handle_recognize(params)
    if method == "unload":
        return handle_unload(params)
    if method == "quit":
        return {"ok": True, "quit": True}
    return {"ok": False, "error": f"unknown_method:{method}"}


def _idle_watchdog(idle_unload_seconds: float, idle_shutdown_seconds: float) -> None:
    """idle_unload：卸模型保进程；idle_shutdown=0 则永不因 idle 退出进程。"""
    while True:
        time.sleep(30)
        with RT.lock:
            idle = time.time() - RT.last_used
            if RT.model_loaded and idle_unload_seconds > 0 and idle >= idle_unload_seconds:
                _log(f"idle {idle:.0f}s → unload model (process stays)")
                handle_unload({})
            if (
                idle_shutdown_seconds > 0
                and idle >= idle_shutdown_seconds
                and not RT.model_loaded
            ):
                _log(f"idle {idle:.0f}s → shutdown process")
                os._exit(0)


def _handle_client(conn: socket.socket) -> None:
    with conn:
        f = conn.makefile("rwb")
        while True:
            line = f.readline()
            if not line:
                break
            try:
                req = json.loads(line.decode("utf-8"))
            except Exception as e:
                resp = {"id": None, "ok": False, "error": f"bad_json:{e}"}
                f.write((json.dumps(resp, ensure_ascii=False) + "\n").encode("utf-8"))
                f.flush()
                continue
            req_id = req.get("id")
            method = str(req.get("method") or "")
            params = req.get("params") or {}
            if not isinstance(params, dict):
                params = {}
            result = dispatch(method, params)
            out = {"id": req_id, **result}
            f.write((json.dumps(out, ensure_ascii=False) + "\n").encode("utf-8"))
            f.flush()
            if result.get("quit"):
                _log("quit requested")
                os._exit(0)


def main() -> int:
    host = os.environ.get("DEEPSEEK_WORKER_HOST", DEFAULT_HOST)
    port = int(os.environ.get("DEEPSEEK_WORKER_PORT", str(DEFAULT_PORT)))
    idle_unload = float(
        os.environ.get("DEEPSEEK_WORKER_IDLE_SECONDS")
        or os.environ.get("DEEPSEEK_WORKER_IDLE_UNLOAD_SECONDS")
        or str(IDLE_UNLOAD_SECONDS)
    )
    idle_shutdown = float(
        os.environ.get("DEEPSEEK_WORKER_IDLE_SHUTDOWN_SECONDS", str(IDLE_SHUTDOWN_SECONDS))
    )

    meta_path = Path(os.environ.get("DEEPSEEK_WORKER_META", str(ROOT / ".cache" / "deepseek_worker.json")))
    meta_path.parent.mkdir(parents=True, exist_ok=True)

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(8)
    bound_port = srv.getsockname()[1]
    meta = {
        "host": host,
        "port": bound_port,
        "pid": os.getpid(),
        "started_at": time.time(),
        "idle_unload_seconds": idle_unload,
        "idle_shutdown_seconds": idle_shutdown,
        "survive_gui_exit": True,
        "phase": "5I",
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    _log(f"listening {host}:{bound_port} meta={meta_path} idle_unload={idle_unload}s")
    RT.state = "READY"
    RT.process_state = "PROCESS_READY"
    RT.model_state = "MODEL_UNLOADED"

    threading.Thread(
        target=_idle_watchdog, args=(idle_unload, idle_shutdown), daemon=True
    ).start()

    try:
        while True:
            conn, _addr = srv.accept()
            threading.Thread(target=_handle_client, args=(conn,), daemon=True).start()
    finally:
        try:
            meta_path.unlink(missing_ok=True)  # type: ignore[call-arg]
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
