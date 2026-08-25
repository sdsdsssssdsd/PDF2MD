"""失败恢复规划（P2：recopy → page → sub-batch → full）。"""
from __future__ import annotations

from app.vision_transcribe.recovery import taxonomy as T
from app.vision_transcribe.recovery.failure_parse import (
    classify_validation_errors,
    contiguous_page_groups,
    failed_pages_from_errors,
)


def suggest_recovery(failure_class: str) -> str:
    """返回建议恢复动作：recopy | continue | page_retry | sub_batch | full_batch。"""
    fc = (failure_class or "").upper()
    if fc in (
        T.CLIPBOARD_STALE,
        T.CLIPBOARD_TRUNCATED,
        T.COPY_NOT_FIRED,
        T.EXTRACTION_UNSTABLE,
    ):
        return "recopy"
    if fc == T.GENERATION_INCOMPLETE:
        return "continue"
    if fc in (T.PAGE_CONTENT_SUSPECT, T.EXTRACTION_CONFLICT, T.PAGE_MARKER_MISSING):
        return "page_retry"
    if fc == T.DOM_CAPTURE_FAILED:
        return "recopy"
    if fc == T.FORMULA_INTEGRITY_FAILED:
        return "page_retry"
    if fc == T.MODEL_DEGENERATION:
        return "full_batch"
    return "full_batch"


def plan_batch_recovery(
    *,
    errors: list[str],
    error_text: str = "",
    recopy_tried: bool = False,
    page_retry_tried: bool = False,
    page_retry_pages: set[int] | None = None,
    sub_batch_tried: bool = False,
    retry_count: int = 0,
) -> tuple[str, list[int]]:
    """返回 (action, target_pages)。action ∈ recopy|page_retry|sub_batch|full_batch。"""
    all_errs = list(errors or [])
    if error_text and error_text not in all_errs:
        all_errs.append(error_text)

    fc = classify_validation_errors(all_errs)
    hint = suggest_recovery(fc)

    if fc == T.MODEL_DEGENERATION:
        return "full_batch", failed_pages_from_errors(all_errs)

    if hint == "recopy" and not recopy_tried:
        return "recopy", []

    pages = failed_pages_from_errors(all_errs)
    retried = set(page_retry_pages or ())
    if page_retry_tried and not retried and pages:
        retried = set(pages)
    pending_pages = [p for p in pages if p not in retried]

    # 软告警（SourceGuard/标记）不应触发单页重跑
    soft_only = all_errs and all(
        any(k in e for k in ("SourceGuard", "PAGE_END", "BATCH_END", "锚点疑似"))
        for e in all_errs
    ) and not any(
        any(k in e for k in ("过短", "缺页", "截断", "公式完整性"))
        for e in all_errs
    )
    if soft_only:
        return "accept_warnings", []

    if pending_pages and len(pending_pages) <= 3:
        return "page_retry", pending_pages

    sub_batch_targets = pending_pages or (
        pages if page_retry_tried and not sub_batch_tried else []
    )
    groups = contiguous_page_groups(sub_batch_targets)
    if (
        sub_batch_targets
        and not sub_batch_tried
        and len(sub_batch_targets) >= 2
        and len(sub_batch_targets) <= 5
        and len(groups) == 1
    ):
        return "sub_batch", sub_batch_targets

    if retry_count >= 2:
        return "full_batch", pages

    if pending_pages:
        return "page_retry", pending_pages[:3]

    return "full_batch", pages
