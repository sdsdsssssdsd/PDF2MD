"""批级 DeepSeek 暖机编排：预检跳过 vs 阻塞就绪 + 显式等待分账。"""
from __future__ import annotations

import time
from typing import Any, Callable

ProgressCB = Callable[[str], None]


def zero_deepseek_document_timings(timings: dict[str, Any], *, needs_deepseek: bool) -> None:
    """本文 DeepSeek 成本归零（后台暖机可继续，不计入本篇 critical path）。"""
    timings["document_needs_deepseek_ocr"] = needs_deepseek
    timings["deepseek_skipped_preflight"] = not needs_deepseek
    timings["deepseek_load"] = 0.0
    timings["model_cold_start"] = 0.0
    timings["deepseek_blocking_load"] = 0.0
    timings["deepseek_load_overlap"] = 0.0
    timings["deepseek_batch_warmup_seconds"] = 0.0
    timings["deepseek_warmup_wait_seconds"] = 0.0
    timings["deepseek_existing_load_wait_seconds"] = 0.0
    timings["deepseek_load_rpc_wait_seconds"] = 0.0
    timings["deepseek_load_count_delta"] = 0


def ensure_deepseek_before_repair(
    *,
    client: Any,
    warmup_thread: Any,
    docling_span: tuple[float, float] | None,
    timings: dict[str, Any],
    progress: ProgressCB,
) -> None:
    """需要 OCR 的文档：批前阻塞直至模型就绪，并写入完整等待分账。

    使用**单次**总预算（默认 load_timeout），禁止 join+wait+load 叠成数分钟假死。
    Worker 已死则尽快走 load()/ensure_started，不空等。
    """
    timings["document_needs_deepseek_ocr"] = True
    timings["deepseek_skipped_preflight"] = False

    health0 = client.health()
    load_count_before = int(health0.get("load_count") or 0)
    timings["deepseek_load_count_before"] = load_count_before

    load_timeout = float(getattr(client, "load_timeout_seconds", 240) or 240)
    deadline = time.time() + load_timeout
    warmup_wait = 0.0
    existing_wait = 0.0
    rpc_wait = 0.0
    batch_warm_s = 0.0

    def _remaining() -> float:
        return max(0.5, deadline - time.time())

    def _model_ready(h: dict[str, Any] | None) -> bool:
        h = h or {}
        return bool(h.get("model_loaded")) and str(h.get("model_state") or "") in {
            "MODEL_READY",
            "",
        }

    if _model_ready(health0):
        rt = client.run_timings
        timings["model_cold_start"] = 0.0
        timings["deepseek_batch_warmup_seconds"] = 0.0
        timings["deepseek_load"] = 0.0
        timings["deepseek_blocking_load"] = 0.0
        timings["deepseek_load_overlap"] = 0.0
        timings["deepseek_current_run"] = rt.to_dict()
        timings["deepseek_worker_lifetime"] = client.worker_lifetime.to_dict()
        timings["deepseek_load_count_delta"] = 0
        timings["deepseek_warmup_wait_seconds"] = 0.0
        timings["deepseek_existing_load_wait_seconds"] = 0.0
        timings["deepseek_load_rpc_wait_seconds"] = 0.0
        progress("DeepSeek：模型已就绪（跳过批前等待）")
        return

    if warmup_thread is not None and warmup_thread.is_alive():
        progress("DeepSeek：等待并行预热完成…")
        t_join = time.time()
        warmup_thread.join(timeout=_remaining())
        warmup_wait += time.time() - t_join

    health = client.health()
    if not _model_ready(health):
        # Worker 挂了 / 未在加载：别空等，直接进入 load
        model_state = str((health or {}).get("model_state") or "")
        state = str((health or {}).get("state") or "")
        alive = bool((health or {}).get("ok")) and state not in {"STOPPED", ""}
        if alive and model_state == "MODEL_LOADING":
            progress("DeepSeek：模型加载中，等待就绪…")
            t_exist = time.time()
            client.wait_for_model_loaded(timeout=_remaining())
            existing_wait += time.time() - t_exist
            health = client.health()

    if not _model_ready(health):
        progress("DeepSeek：批前同步加载模型（移出 repair）…")
        t_rpc = time.time()
        # load() 自身有 RPC timeout；外层预算只用于日志分账
        client.load(parallel_span=docling_span)
        batch_warm_s = time.time() - t_rpc
        rt = client.run_timings
        load_s = float(rt.model_load_seconds or batch_warm_s or 0.0)
        rpc_wait = max(0.0, batch_warm_s - load_s)
        timings["deepseek_batch_warmup_seconds"] = round(batch_warm_s, 3)
        timings["model_cold_start"] = round(load_s, 3)
        timings["deepseek_load"] = round(load_s, 3)
        timings["deepseek_blocking_load"] = round(
            float(rt.blocking_load_seconds or load_s), 3
        )
        timings["deepseek_load_overlap"] = round(float(rt.load_overlap_seconds or 0.0), 3)
        timings["deepseek_current_run"] = rt.to_dict()
        timings["deepseek_worker_lifetime"] = client.worker_lifetime.to_dict()
        ready = _model_ready(client.health())
        progress(
            f"DeepSeek：批前加载{'完成' if ready else '未完成'} {load_s:.1f}s "
            f"(blocking={timings['deepseek_blocking_load']}s)"
        )
    else:
        rt = client.run_timings
        load_s = float(rt.model_load_seconds or 0.0)
        timings["model_cold_start"] = 0.0
        timings["deepseek_batch_warmup_seconds"] = 0.0
        timings["deepseek_load"] = round(load_s, 3) if load_s > 0.05 else 0.0
        timings["deepseek_blocking_load"] = round(
            float(rt.blocking_load_seconds or 0.0), 3
        )
        timings["deepseek_load_overlap"] = round(float(rt.load_overlap_seconds or 0.0), 3)
        if load_s > 0.05 or rt.to_dict().get("load_started_at"):
            timings["deepseek_current_run"] = rt.to_dict()
        timings["deepseek_worker_lifetime"] = client.worker_lifetime.to_dict()

    load_count_after = int((client.health() or {}).get("load_count") or 0)
    timings["deepseek_load_count_delta"] = max(0, load_count_after - load_count_before)
    timings["deepseek_warmup_wait_seconds"] = round(warmup_wait, 3)
    timings["deepseek_existing_load_wait_seconds"] = round(existing_wait, 3)
    timings["deepseek_load_rpc_wait_seconds"] = round(rpc_wait, 3)


def finalize_deepseek_timings_after_repair(
    *,
    timings: dict[str, Any],
    warmup_thread: Any,
    docling_span: tuple[float, float] | None,
    client: Any,
) -> None:
    """Repair 后补算 overlap；预检跳过篇目不 join、不污染本篇 metrics。"""
    if timings.get("deepseek_skipped_preflight"):
        try:
            alive = bool(warmup_thread is not None and warmup_thread.is_alive())
            h = client.health()
            timings["deepseek_worker_background"] = {
                "warmup_thread_alive": alive,
                "model_loaded": bool(h.get("model_loaded")),
                "load_count": int(h.get("load_count") or 0),
            }
        except Exception:
            pass
        return

    if warmup_thread is None or not docling_span:
        return

    if warmup_thread.is_alive():
        warmup_thread.join(timeout=1.0)

    ds, de = docling_span
    rt = client.run_timings
    if "deepseek_current_run" not in timings:
        ls, lf = rt.load_started_at, rt.load_finished_at
        if ls and lf and rt.model_load_seconds > 0.05:
            lo = max(ls, ds)
            hi = min(lf, de)
            overlap = max(0.0, hi - lo)
            load_s = float(rt.model_load_seconds or 0)
            timings["deepseek_load"] = round(load_s, 3)
            timings["deepseek_load_overlap"] = round(overlap, 3)
            timings["deepseek_blocking_load"] = round(max(0.0, load_s - overlap), 3)
        else:
            timings["deepseek_load"] = round(float(rt.model_load_seconds or 0), 3)
            timings["deepseek_load_overlap"] = 0.0
            timings["deepseek_blocking_load"] = round(
                float(rt.blocking_load_seconds or 0), 3
            )
        timings["deepseek_current_run"] = rt.to_dict()
        timings["deepseek_worker_lifetime"] = client.worker_lifetime.to_dict()
    timings["deepseek_worker"] = client.timings.to_dict()


def deepseek_critical_path_seconds(timings: dict[str, Any]) -> float:
    """本篇 DeepSeek 阻塞在 critical path 上的总秒数（含未归因等待）。"""
    if timings.get("deepseek_skipped_preflight"):
        return float(timings.get("recovery_cold_start_seconds") or 0.0)
    waits = sum(
        float(timings.get(k) or 0.0)
        for k in (
            "deepseek_warmup_wait_seconds",
            "deepseek_existing_load_wait_seconds",
            "deepseek_load_rpc_wait_seconds",
        )
    )
    load = max(
        float(timings.get("deepseek_blocking_load") or 0.0),
        float(timings.get("model_cold_start") or 0.0),
    )
    return waits + load
