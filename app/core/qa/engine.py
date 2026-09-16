"""Unified QA：JobRunner 终态判定器。DocumentIR 只提供事实，分数不写回 IR。"""
from __future__ import annotations

from typing import Any

from app.core.domain.document import DocumentIR
from app.core.domain.quality import QualityReport, build_report
from app.core.qa.checks import (
    check_empty_document,
    check_equation_numbers,
    check_forbidden_markers,
    check_formula_structural,
    check_formula_unresolved,
    check_page_coverage,
    check_placeholders,
    check_retry_exhaustion,
    check_text_anchors,
)

UNIFIED_CHECK_IDS: tuple[str, ...] = (
    "empty_document",
    "page_coverage",
    "formula_unresolved",
    "formula_structural_validity",
    "equation_number_preservation",
    "text_anchor_preservation",
    "placeholder_or_fake_url",
    "retry_recovery_exhaustion",
    "forbidden_markers",
)


def run_unified_qa(
    markdown: str,
    *,
    document: DocumentIR | None = None,
    page_count: int | None = None,
    required_pages: list[int] | None = None,
    required_equation_ids: list[str] | None = None,
    anchors: list[str] | None = None,
    forbidden_markers: list[str] | None = None,
    max_unresolved_formulas: int = 0,
    context: dict[str, Any] | None = None,
    evaluator: str = "unified",
) -> QualityReport:
    checks = [
        check_empty_document(markdown),
        check_page_coverage(
            markdown, page_count=page_count, required_pages=required_pages
        ),
        check_formula_unresolved(markdown, max_unresolved=max_unresolved_formulas, document=document),
        check_formula_structural(markdown, document),
        check_equation_numbers(markdown, required_ids=required_equation_ids),
        check_text_anchors(markdown, anchors=anchors),
        check_placeholders(markdown),
        check_retry_exhaustion(context),
        check_forbidden_markers(markdown, forbidden_markers),
    ]
    extra = {
        "page_count": page_count,
        "chars": len(markdown or ""),
        "block_count": len(document.blocks) if document is not None else None,
    }
    return build_report(checks, evaluator=evaluator, extra_summary=extra)


def quality_from_markdown(
    markdown: str,
    *,
    page_count: int | None = None,
    extra: dict[str, Any] | None = None,
) -> QualityReport:
    """兼容入口：无 Gold 期望时跑默认统一门。"""
    ctx = dict(extra or {})
    recovery = ctx.get("recovery") if isinstance(ctx.get("recovery"), dict) else None
    return run_unified_qa(
        markdown,
        page_count=page_count,
        context={"recovery": recovery or {}, "retries": ctx.get("retries")},
        evaluator="unified",
    )
