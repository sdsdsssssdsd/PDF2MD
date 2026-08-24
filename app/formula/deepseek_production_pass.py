"""DeepSeek Limited Production：UniMERNet 失败后的高置信第二遍写回。

仅当 FormulaConfig.deepseek_limited_production_enabled 时启用。
GUI 主进程若无兼容 transformers，则走 dsocr2 子进程 OCR，写回仍在本进程。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable

from app.formula.config import FormulaConfig, formula_config_for_deepseek_limited_production
from app.formula.equation_numbers import bind_equation_number_from_latex
from app.formula.fallback import fallback_markup
from app.formula.session import FormulaRecoverySession
from app.formula.types import FormulaCandidate, FormulaLifecycle
from app.formula.writeback import (
    FormulaBlockRegistry,
    FormulaWritebackManager,
    RecoveryWritebackItem,
)
from app.formula.writeback_match import build_pending_indexes, match_shadow_row_to_pending
from app.ocr.deepseek_paths import (
    ensure_deepseek_hf_env,
    resolve_deepseek_model_name,
    resolve_dsocr2_python,
)
from app.ocr.executor import eq_number_from_candidate
from app.utils.paths import APP_ROOT, SCRIPTS_DIR

ProgressCB = Callable[[str], None]

_DS_MARKER = re.compile(
    r"\$\$\s*%dsid:([A-Za-z0-9_.:-]+)%\s*(.*?)\s*\$\$",
    re.DOTALL,
)


def make_pending_display_block(candidate_id: str, raw_inner: str) -> str:
    body = (raw_inner or r"\quad\quad\quad garbage").strip()
    return f"$$\n%dsid:{candidate_id}%\n{body}\n$$"


def stable_candidate_id(cand: FormulaCandidate, *, seq: int) -> str:
    """仅使用结构阶段已绑定的 equation_number；未绑定 → eqiN。

    禁止回退到 context 里「最后一个 Eq.(n)」——那会把 Eq.6/Eq.7 两槽都标成 7。
    """
    from app.formula.equation_identity import safe_eq_id_token

    page = cand.page if cand.page is not None else 0
    eq = (getattr(cand, "equation_number", None) or "").strip()
    if eq:
        eq = safe_eq_id_token(eq)
    else:
        eq = f"i{seq}"
    return f"page{page}_eq{eq}"


def _cand_payload(cand: FormulaCandidate, candidate_id: str) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "text": cand.text or "",
        "raw_text": cand.raw_text or cand.text or "",
        "page": cand.page,
        "bbox": list(cand.bbox) if cand.bbox else None,
        "context_before": cand.context_before or "",
        "context_after": cand.context_after or "",
        "display_mode": cand.display_mode or "display",
    }


def _cand_from_payload(row: dict[str, Any]) -> FormulaCandidate:
    bbox = row.get("bbox")
    return FormulaCandidate(
        text=str(row.get("text") or r"\quad\quad\quad garbage"),
        raw_text=str(row.get("raw_text") or row.get("text") or ""),
        page=int(row["page"]) if row.get("page") is not None else None,
        bbox=tuple(float(x) for x in bbox) if bbox and len(bbox) == 4 else None,
        context_before=str(row.get("context_before") or ""),
        context_after=str(row.get("context_after") or ""),
        source_type="parser_math",
        display_mode="display",
        lifecycle=FormulaLifecycle.CORRUPTED,
        status="corrupted",
        issues=["deepseek_limited_pending"],
        candidate_id=str(row.get("candidate_id") or ""),
    )


def run_shadow_inprocess(
    pdf: Path,
    candidates: list[tuple[str, FormulaCandidate]],
    cfg: FormulaConfig,
    *,
    model_name: str | None = None,
    prefer_persistent_worker: bool = True,
) -> dict[str, Any]:
    from app.formula.config import adaptive_hard_limit_seconds

    ensure_deepseek_hf_env()
    from app.ocr.cost_model import RecoveryCostModel, default_profile_path
    from app.ocr.shadow import ShadowRecoveryRunner

    recognizer: Any
    via = "inprocess"
    if prefer_persistent_worker and resolve_dsocr2_python() is not None:
        from app.ocr.deepseek_worker_client import (
            get_deepseek_worker_client,
            prepare_document_worker_session,
        )
        from app.ocr.deepseek_worker_recognizer import WorkerBackedDeepSeekRecognizer

        client = get_deepseek_worker_client()
        client.survive_gui_exit = bool(getattr(cfg, "deepseek_survive_gui_exit", True))
        unload_m = float(getattr(cfg, "deepseek_idle_unload_minutes", 60.0) or 0.0)
        shut_m = float(getattr(cfg, "deepseek_idle_shutdown_minutes", 0.0) or 0.0)
        os.environ["DEEPSEEK_WORKER_IDLE_UNLOAD_SECONDS"] = str(max(0.0, unload_m * 60.0))
        os.environ["DEEPSEEK_WORKER_IDLE_SHUTDOWN_SECONDS"] = str(max(0.0, shut_m * 60.0))
        client.load_timeout_seconds = float(
            getattr(cfg, "deepseek_load_timeout_seconds", 240.0) or 240.0
        )
        client.infer_timeout_seconds = float(
            getattr(cfg, "deepseek_formula_timeout_seconds", 30.0) or 30.0
        )
        client.slow_call_threshold_seconds = float(
            getattr(cfg, "deepseek_slow_call_threshold_seconds", 20.0) or 20.0
        )
        client.slow_call_restart_count = int(
            getattr(cfg, "deepseek_slow_call_restart_count", 2) or 2
        )
        prepare_document_worker_session(client)
        if client.ensure_started():
            # 批前 ensure 已负责长等待；此处仅短等 MODEL_LOADING，避免再叠 240s
            h = client.health() or {}
            ready = bool(h.get("model_loaded")) and str(h.get("model_state") or "") in {
                "MODEL_READY",
                "",
            }
            if not ready and str(h.get("model_state") or "") == "MODEL_LOADING":
                client.wait_for_model_loaded(timeout=min(30.0, client.load_timeout_seconds))
                h = client.health() or {}
                ready = bool(h.get("model_loaded"))
            if not ready:
                client.load()
            recognizer = WorkerBackedDeepSeekRecognizer(client)
            via = "persistent_worker"
        else:
            prefer_persistent_worker = False

    if via != "persistent_worker":
        from app.ocr.deepseek_ocr2 import DeepSeekOCR2Recognizer

        recognizer = DeepSeekOCR2Recognizer(
            model_name=model_name or resolve_deepseek_model_name(),
            device="cuda:0",
            dtype="bf16",
            base_size=1024,
            image_size=640,
            crop_mode=True,
            allow_cpu=False,
        )
        via = "inprocess"

    cost = RecoveryCostModel(
        profile_path=default_profile_path(),
        auto_load=True,
        auto_save=True,
        max_outlier_multiplier=float(cfg.deepseek_outlier_multiplier or 3.0),
    )
    runner = ShadowRecoveryRunner(config=cfg, recognizer=recognizer, cost_model=cost)
    cands: list[FormulaCandidate] = []
    for cid, c in candidates:
        c.candidate_id = cid
        bind_equation_number_from_latex(c)
        cands.append(c)
    hl = adaptive_hard_limit_seconds(
        len(cands), base=float(getattr(cfg, "deepseek_hard_limit_seconds", 300.0) or 300.0)
    )
    prev_hl = float(getattr(cfg, "deepseek_hard_limit_seconds", 300.0) or 300.0)
    cfg.deepseek_hard_limit_seconds = hl
    try:
        with FormulaRecoverySession(pdf, cfg) as session:
            shadow = runner.run(cands, session=session, pdf_path=pdf)
    finally:
        cfg.deepseek_hard_limit_seconds = prev_hl
    out = shadow.to_dict()
    summary = out.setdefault("summary", {})
    summary["recognizer_via"] = via
    try:
        from app.ocr.deepseek_worker_client import get_deepseek_worker_client

        wc = get_deepseek_worker_client()
        summary["worker_timings"] = wc.timings.to_dict()
        summary["current_run"] = wc.run_timings.to_dict()
        summary["worker"] = wc.worker_lifetime.to_dict()
        summary["worker_session"] = wc.session_stats.to_dict()
        summary["tail_latency_protected"] = bool(wc.session_stats.tail_latency_protected)
        summary.setdefault("acceptance", {})["tail_latency_protected"] = summary[
            "tail_latency_protected"
        ]
        summary.setdefault("acceptance", {})["warm_reuse"] = bool(
            wc.run_timings.reused_warm_worker
        )
    except Exception:
        pass
    return out

def run_shadow_subprocess(
    pdf: Path,
    candidates: list[tuple[str, FormulaCandidate]],
    cfg: FormulaConfig,
    *,
    emit: ProgressCB | None = None,
) -> dict[str, Any]:
    py = resolve_dsocr2_python()
    if py is None:
        raise RuntimeError("dsocr2_python_missing")
    worker = SCRIPTS_DIR / "deepseek_limited_pass_worker.py"
    if not worker.is_file():
        raise RuntimeError(f"worker_missing:{worker}")

    payload = {
        "pdf": str(pdf),
        "model_name": resolve_deepseek_model_name(),
        "candidates": [_cand_payload(c, cid) for cid, c in candidates],
        "config": {
            "deepseek_max_formulas_per_document": cfg.deepseek_max_formulas_per_document,
            "deepseek_max_pages_per_document": cfg.deepseek_max_pages_per_document,
            "deepseek_max_total_recovery_seconds": cfg.deepseek_max_total_recovery_seconds,
            "deepseek_hard_limit_seconds": getattr(cfg, "deepseek_hard_limit_seconds", 300.0),
            "deepseek_coverage_first": getattr(cfg, "deepseek_coverage_first", True),
            "deepseek_formula_timeout_seconds": getattr(
                cfg, "deepseek_formula_timeout_seconds", 30.0
            ),
            "deepseek_page_safety_factor": cfg.deepseek_page_safety_factor,
            "deepseek_min_page_formula_count": cfg.deepseek_min_page_formula_count,
            "deepseek_outlier_multiplier": cfg.deepseek_outlier_multiplier,
            "crop_render_scale": cfg.crop_render_scale,
        },
    }
    with tempfile.TemporaryDirectory(prefix="ds_lp_") as td:
        inp = Path(td) / "in.json"
        outp = Path(td) / "out.json"
        inp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        if emit:
            emit("DeepSeek：调用 dsocr2 子进程 OCR…")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(APP_ROOT) + (
            os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
        )
        ensure_deepseek_hf_env()
        for k in ("HF_HOME", "HUGGINGFACE_HUB_CACHE", "TRANSFORMERS_CACHE", "TRANSFORMERS_NO_TF", "USE_TF"):
            if k in os.environ:
                env[k] = os.environ[k]
        proc = subprocess.run(
            [str(py), "-u", str(worker), str(inp), str(outp)],
            cwd=str(APP_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            check=False,
        )
        if proc.returncode != 0 or not outp.is_file():
            tail = (proc.stderr or proc.stdout or "")[-1200:]
            raise RuntimeError(f"dsocr2_worker_failed:{proc.returncode}:{tail}")
        return json.loads(outp.read_text(encoding="utf-8"))


def _transformers_version() -> str:
    try:
        import transformers

        return str(getattr(transformers, "__version__", "") or "")
    except Exception:
        return ""


def _deepseek_inprocess_compatible() -> bool:
    """GUI 主环境常为 transformers 4.57+，与 DeepSeek-OCR-2 不兼容。"""
    try:
        import torch

        if not torch.cuda.is_available():
            return False
    except Exception:
        return False
    ver = _transformers_version()
    if not ver:
        return False
    # 冻结验证环境：4.46.x
    parts = ver.split(".")
    try:
        major, minor = int(parts[0]), int(parts[1])
    except (TypeError, ValueError, IndexError):
        return False
    return major == 4 and minor == 46


def shadow_would_replace_rows(shadow: dict[str, Any]) -> list[dict[str, Any]]:
    summary = shadow.get("summary") or {}
    rows = list(summary.get("would_replace") or [])
    if rows:
        return rows
    return list(shadow.get("would_replace") or [])


def register_marked_blocks(markdown: str) -> FormulaBlockRegistry:
    reg = FormulaBlockRegistry()
    spans: list[tuple[str, int, int, str]] = []
    for m in _DS_MARKER.finditer(markdown):
        spans.append((m.group(1), m.start(), m.end(), "display"))
    reg.register_from_markdown_spans(markdown, spans)
    return reg


def strip_remaining_markers(markdown: str, cfg: FormulaConfig, *, reason: str = "deepseek_not_applied") -> str:
    """未写回成功的 pending 块 → clean 占位。"""

    def _repl(m: re.Match[str]) -> str:
        cand = FormulaCandidate(
            text=m.group(2) or "",
            raw_text=m.group(2) or "",
            display_mode="display",
            lifecycle=FormulaLifecycle.RECOVERY_FAILED,
            status="recovery_failed",
            issues=[reason[:80] if reason else "deepseek_not_applied"],
        )
        return fallback_markup(cand, cfg)

    return _DS_MARKER.sub(_repl, markdown)


def _run_shadow_with_fallback(
    pdf: Path,
    pending: list[tuple[str, FormulaCandidate]],
    cfg: FormulaConfig,
    *,
    emit: ProgressCB | None = None,
) -> tuple[dict[str, Any], str]:
    """优先持久 Worker；其次整篇 dsocr2 子进程；最后兼容本机 inprocess。"""
    errors: list[str] = []

    # P0：持久 Worker（主进程 shadow + GPU OCR RPC）
    if resolve_dsocr2_python() is not None:
        try:
            if emit:
                emit("DeepSeek：持久 Worker OCR…")
            shadow = run_shadow_inprocess(pdf, pending, cfg, prefer_persistent_worker=True)
            via = (shadow.get("summary") or {}).get("recognizer_via") or "persistent_worker"
            return shadow, str(via)
        except Exception as e:
            errors.append(f"persistent_worker:{e}")
            if emit:
                emit(f"DeepSeek Worker 失败，回退一次性子进程：{e}")

    if resolve_dsocr2_python() is not None:
        try:
            if emit:
                emit("DeepSeek：dsocr2 一次性子进程 OCR…")
            return run_shadow_subprocess(pdf, pending, cfg, emit=emit), "dsocr2_subprocess"
        except Exception as e:
            errors.append(f"subprocess:{e}")

    if _deepseek_inprocess_compatible():
        try:
            if emit:
                emit("DeepSeek：本进程 GPU Shadow…")
            return run_shadow_inprocess(
                pdf, pending, cfg, prefer_persistent_worker=False
            ), "inprocess"
        except Exception as e:
            errors.append(f"inprocess:{e}")

    raise RuntimeError("; ".join(errors) or "deepseek_shadow_unavailable")


def apply_deepseek_limited_production_pass(
    markdown: str,
    pdf_path: str | Path,
    pending: list[tuple[str, FormulaCandidate]],
    *,
    config: FormulaConfig | None = None,
    emit: ProgressCB | None = None,
) -> tuple[str, dict[str, Any]]:
    """对带 %dsid:% 标记的 display 块跑 Shadow → 受控写回。"""
    cfg = config or formula_config_for_deepseek_limited_production()
    pdf = Path(pdf_path)
    meta: dict[str, Any] = {
        "enabled": True,
        "pending": len(pending),
        "via": "none",
        "error": "",
        "transformers_host": _transformers_version(),
    }
    if not pending or not pdf.is_file():
        meta["error"] = "no_pending_or_pdf"
        return strip_remaining_markers(markdown, cfg, reason=meta["error"]), meta

    # 预算截断：0 / 负数 = 不截断（全量 pending）
    max_n = int(cfg.deepseek_max_writebacks_per_document or 0)
    if max_n > 0:
        pending = pending[:max_n]

    try:
        shadow, via = _run_shadow_with_fallback(pdf, pending, cfg, emit=emit)
        meta["via"] = via
    except Exception as e:
        meta["error"] = str(e)[:500]
        if emit:
            emit(f"DeepSeek 恢复失败（保留占位）：{e}")
        return strip_remaining_markers(markdown, cfg, reason="deepseek_ocr_failed"), meta

    rows = shadow_would_replace_rows(shadow)
    pending_by_id, pending_by_key = build_pending_indexes(pending)
    used: set[str] = set()
    items: list[RecoveryWritebackItem] = []
    for row in rows:
        cid = match_shadow_row_to_pending(
            row, pending_by_id, pending_by_key, used=used
        )
        if not cid:
            continue
        used.add(cid)
        cand = pending_by_id[cid]
        page = int(row["page"]) if row.get("page") is not None else cand.page
        items.append(
            RecoveryWritebackItem(
                candidate_id=cid,
                recovered_latex=str(row.get("recovered") or row.get("selected_latex") or ""),
                gate_accepted=bool(row.get("gate_accepted")),
                would_replace=bool(row.get("would_replace")),
                gate_reason=str(row.get("gate_reason") or ""),
                original=str(row.get("original") or ""),
                scheduler_mode=str(row.get("scheduler_mode") or ""),
                page=page,
                eq_number=str(row.get("eq_number") or eq_number_from_candidate(cand)),
                context_before=cand.context_before or "",
                context_after=cand.context_after or "",
                bbox=cand.bbox,
            )
        )

    reg = register_marked_blocks(markdown)
    wb = FormulaWritebackManager(cfg)
    report = wb.apply(
        markdown,
        items,
        reg,
        unresolved_formula_count=max(0, len(pending) - sum(1 for it in items if it.would_replace)),
    )
    out = report.markdown_after
    out = strip_remaining_markers(out, cfg, reason="deepseek_writeback_skipped")

    meta["shadow"] = shadow
    meta["writeback"] = report.to_dict()
    meta["applied"] = int(report.applied_count)
    meta["would_replace_rows"] = len(rows)
    if emit:
        emit(
            f"DeepSeek 写回：applied={report.applied_count}/{len(pending)}，"
            f"rows={len(rows)}，via={meta['via']}"
        )
    return out, meta
