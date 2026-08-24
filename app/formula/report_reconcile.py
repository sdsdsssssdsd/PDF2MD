"""DeepSeek shadow / 写回完成后，对齐 FormulaQAReport 顶层计数与 formula_failures。"""
from __future__ import annotations

import re
from typing import Any

from app.formula.config import FormulaConfig
from app.formula.release_gate import check_release
from app.formula.types import FormulaQAReport


def _norm_raw(text: str, *, limit: int = 320) -> str:
    return re.sub(r"\s+", " ", (text or "")[:limit]).strip()


def _strip_ds_marker(text: str) -> str:
    return re.sub(r"%dsid:[^%]+%", "", text or "", flags=re.I).strip()


def _shadow_rows(shadow: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page in shadow.get("pages") or []:
        exec_block = page.get("execution") or {}
        rows.extend(exec_block.get("candidates") or [])
    summary = shadow.get("summary") or {}
    rows.extend(summary.get("would_replace") or [])
    return rows


def _build_outcome_index(
    shadow: dict[str, Any] | None,
    writeback: dict[str, Any] | None,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """candidate_id / normalized raw → shadow+写回结果。"""
    by_id: dict[str, dict[str, Any]] = {}
    by_raw: dict[str, dict[str, Any]] = {}

    def put(key_id: str, raw: str, payload: dict[str, Any]) -> None:
        if key_id:
            cur = by_id.setdefault(key_id, {})
            cur.update(payload)
        norm = _norm_raw(_strip_ds_marker(raw))
        if norm:
            cur = by_raw.setdefault(norm, {})
            cur.update(payload)

    for row in _shadow_rows(shadow or {}):
        cid = str(row.get("candidate_id") or "").strip()
        raw = str(row.get("original") or "")
        accepted = bool(row.get("gate_accepted")) and bool(row.get("would_replace"))
        put(
            cid,
            raw,
            {
                "candidate_id": cid,
                "shadow_accepted": accepted,
                "shadow_rejected": bool(row.get("gate_accepted") is False or row.get("error")),
                "gate_reason": str(row.get("gate_reason") or ""),
                "failure_class": str(row.get("failure_class") or ""),
            },
        )

    for entry in (writeback or {}).get("entries") or []:
        cid = str(entry.get("candidate_id") or "").strip()
        raw = str(entry.get("original") or "")
        put(
            cid,
            raw,
            {
                "candidate_id": cid,
                "writeback_accepted": bool(entry.get("accepted")),
                "writeback_applied": bool(entry.get("writeback_applied")),
                "writeback_skip_reason": str(entry.get("skip_reason") or ""),
            },
        )
        if entry.get("accepted"):
            put(
                cid,
                raw,
                {
                    "shadow_accepted": True,
                },
            )

    return by_id, by_raw


def _lookup_outcome(
    failure: dict[str, Any],
    by_id: dict[str, dict[str, Any]],
    by_raw: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    cid = str(failure.get("candidate_id") or "").strip()
    if cid and cid in by_id:
        return by_id[cid]
    raw = _norm_raw(_strip_ds_marker(str(failure.get("raw") or "")))
    if raw and raw in by_raw:
        return by_raw[raw]
    for key, outcome in by_raw.items():
        if len(key) >= 24 and (key in raw or raw in key):
            return outcome
    return None


def _sync_details(report: FormulaQAReport, resolved_raws: set[str]) -> None:
    for detail in report.details:
        if detail.get("status") != "recovery_failed":
            continue
        preview = _norm_raw(str(detail.get("preview") or ""))
        if not preview:
            continue
        for raw in resolved_raws:
            if preview in raw or raw[:80] in preview:
                detail["status"] = "recovery_success"
                detail["lifecycle"] = "recovery_success"
                detail["resolution"] = "shadow_accepted"
                break


def reconcile_report_after_deepseek(
    report: FormulaQAReport,
    markdown: str,
    cfg: FormulaConfig | None = None,
) -> None:
    """用 shadow / writeback 真值覆盖 pipeline 阶段的暂态 recovery_failed 计数。"""
    cfg = cfg or FormulaConfig()
    shadow = report.deepseek_shadow or {}
    writeback = report.writeback or {}
    summary = shadow.get("summary") or {}

    if not shadow and not writeback:
        return

    by_id, by_raw = _build_outcome_index(shadow, writeback)

    shadow_accepted = int(summary.get("accepted") or 0)
    shadow_rejected = int(summary.get("rejected") or 0)
    if shadow_accepted == 0 and by_id:
        shadow_accepted = sum(
            1 for o in by_id.values() if o.get("shadow_accepted")
        )
    if shadow_rejected == 0 and summary.get("attempted"):
        attempted = int(summary.get("attempted") or 0)
        if attempted and shadow_accepted:
            shadow_rejected = max(0, attempted - shadow_accepted)

    wb_applied = int(writeback.get("applied_count") or 0)
    wb_skipped = sum(
        1
        for e in (writeback.get("entries") or [])
        if e.get("accepted") and not e.get("writeback_applied") and e.get("skip_reason")
    )

    resolved_raws: set[str] = set()
    unresolved_failures: list[dict[str, Any]] = []

    for failure in report.formula_failures:
        outcome = _lookup_outcome(failure, by_id, by_raw)
        if outcome and outcome.get("shadow_accepted"):
            failure["lifecycle"] = "recovery_success"
            failure["status"] = "recovery_success"
            failure["resolution"] = "shadow_accepted"
            if outcome.get("gate_reason"):
                failure["gate_reason"] = outcome["gate_reason"]
            if outcome.get("writeback_applied"):
                failure["writeback_applied"] = True
            elif outcome.get("writeback_skip_reason"):
                failure["failure_stage"] = "writeback"
                failure["writeback_skip_reason"] = outcome["writeback_skip_reason"]
            raw = _norm_raw(_strip_ds_marker(str(failure.get("raw") or "")))
            if raw:
                resolved_raws.add(raw)
            continue
        if outcome and outcome.get("shadow_rejected"):
            failure["resolution"] = "shadow_rejected"
        unresolved_failures.append(failure)

    _sync_details(report, resolved_raws)

    corrupted = int(report.corrupted_formula_count or 0)
    if shadow_accepted > 0:
        report.recovery_success_count = shadow_accepted
        report.recovery_failed_count = max(0, corrupted - shadow_accepted)
        if corrupted:
            report.fallback = max(0, corrupted - shadow_accepted)
    elif wb_applied > 0:
        report.recovery_success_count = wb_applied
        report.recovery_failed_count = max(0, corrupted - wb_applied)
        report.fallback = max(0, corrupted - wb_applied)

    if report.telemetry is not None:
        report.telemetry.recovery_success = int(report.recovery_success_count or 0)
        report.telemetry.recovery_rejected = int(shadow_rejected or 0)

    report.document_quality = check_release(
        markdown,
        report,
        cfg,
        writeback_skipped=wb_skipped,
    )
