"""QA → RecoveryRequest → capability resolve → 局部 patch → Re-QA。

不在这里做整篇 parser fallback，也不按具体 backend 名字分支。
没有 specialist executor 时跳过，把请求留给 R12 incubator。
"""
from __future__ import annotations

import re
from typing import Any, Callable
from uuid import uuid4

from app.core.domain.document import BLOCK_TABLE, BlockIR, DocumentIR, Provenance
from app.core.domain.quality import CheckStatus, QualityReport, QualityVerdict
from app.core.domain.recovery import (
    ProblemType,
    RecoveryOutcome,
    RecoveryPatch,
    RecoveryRequest,
    RecoveryScope,
    RecoveryStatus,
)
from app.core.providers.descriptor import Capability, ProviderHandle, ResolveConstraints
from app.core.providers.registry import get_registry
from app.core.qa.engine import run_unified_qa

RecoverFn = Callable[[RecoveryRequest, DocumentIR, str, ProviderHandle | None], RecoveryPatch | None]

_PAGE_ID_RE = re.compile(r"^page:(\d+)$", re.I)
_FORMULA_FAIL_RE = re.compile(
    r"formula-not-decoded|公式未能可靠提取|Formula extraction failed",
    re.I,
)

_CHECK_CAPABILITY = {
    "formula_unresolved": (Capability.FORMULA_RECOGNITION, ProblemType.FORMULA_UNRESOLVED),
    "formula_structural_validity": (Capability.FORMULA_RECOGNITION, ProblemType.FORMULA_STRUCTURAL),
    "page_coverage": (Capability.VISION_PAGE, ProblemType.PAGE_COVERAGE),
    "placeholder_or_fake_url": (Capability.VISION_REGION, ProblemType.PLACEHOLDER),
}

DEFAULT_BUDGET = 8


def plan_recovery(
    quality: QualityReport,
    document: DocumentIR | None = None,
    *,
    budget: int = DEFAULT_BUDGET,
) -> list[RecoveryRequest]:
    """只从 QA evidence 出局部请求。空文档 FAILED 不规划。"""
    if _fatal_empty(quality):
        return []
    requests: list[RecoveryRequest] = []
    seen: set[tuple[Any, ...]] = set()

    def _add(req: RecoveryRequest) -> None:
        key = (req.required_capability, req.page, req.block_ids, req.problem_type)
        if key in seen:
            return
        seen.add(key)
        requests.append(req)

    ranked = sorted(
        quality.checks,
        key=lambda c: (
            0 if (c.status == CheckStatus.FAIL.value and c.blocking) else
            1 if c.status == CheckStatus.FAIL.value else
            2 if c.status == CheckStatus.WARN.value else
            3
        ),
    )
    for check in ranked:
        if check.status not in {CheckStatus.FAIL.value, CheckStatus.WARN.value}:
            continue
        mapped = _CHECK_CAPABILITY.get(check.check_id)
        if mapped is None:
            continue
        capability, problem = mapped
        pages = _pages_from_check(check)
        block_ids = _block_ids_from_check(check, document)
        if check.check_id.startswith("formula") and document is not None:
            block_ids = block_ids or _formula_fail_blocks(document)
            if not pages:
                pages = _pages_of_blocks(document, block_ids)
        if check.check_id == "page_coverage" and not pages:
            missing = check.evidence.get("missing") or []
            pages = [int(p) for p in missing if str(p).isdigit() or isinstance(p, int)]
        if pages:
            for page in pages[:4]:
                page_blocks = tuple(
                    b.id
                    for b in (document.blocks if document is not None else [])
                    if b.page == page and (not block_ids or b.id in block_ids)
                )
                _add(
                    _make_request(
                        scope=RecoveryScope.PAGE,
                        page=int(page),
                        block_ids=page_blocks or block_ids,
                        capability=capability,
                        problem=problem,
                        evidence=dict(check.evidence),
                    )
                )
        elif block_ids:
            _add(
                _make_request(
                    scope=RecoveryScope.BLOCK,
                    page=None,
                    block_ids=block_ids,
                    capability=capability,
                    problem=problem,
                    evidence=dict(check.evidence),
                )
            )
        else:
            _add(
                _make_request(
                    scope=RecoveryScope.DOCUMENT,
                    page=None,
                    block_ids=(),
                    capability=capability,
                    problem=problem,
                    evidence=dict(check.evidence),
                    status=RecoveryStatus.REFUSED,
                    reason="unscoped_no_page_or_block",
                )
            )

    if document is not None:
        for block in _broken_tables(document):
            _add(
                _make_request(
                    scope=RecoveryScope.BLOCK if block.page is None else RecoveryScope.PAGE,
                    page=block.page,
                    block_ids=(block.id,),
                    capability=Capability.TABLE_STRUCTURE,
                    problem=ProblemType.TABLE_STRUCTURE,
                    evidence={"block_id": block.id, "reason": "inconsistent_table"},
                )
            )
    return requests[: max(0, int(budget))]


def resolve_recovery(request: RecoveryRequest) -> ProviderHandle | None:
    """Router 只问 capability。"""
    if request.status == RecoveryStatus.REFUSED:
        return None
    cap = request.required_capability
    exclude: tuple[str, ...] = ()
    if cap == Capability.TABLE_STRUCTURE:
        exclude = ("parser.docling", "parser.mineru")
    allow_experimental = cap in {
        Capability.TABLE_STRUCTURE,
        Capability.LAYOUT_DETECTION,
        Capability.READING_ORDER,
        Capability.VISION_PAGE,
        Capability.VISION_REGION,
    }
    input_kind = "pdf"
    if cap in {
        Capability.FORMULA_RECOGNITION,
        Capability.VISION_PAGE,
        Capability.VISION_REGION,
    }:
        input_kind = None
    return get_registry().resolve(
        cap,
        ResolveConstraints(
            capability=cap,
            exclude_ids=exclude,
            allow_experimental=allow_experimental,
            input_kind=input_kind,
        ),
    )


def apply_patch(document: DocumentIR, markdown: str, patch: RecoveryPatch) -> tuple[DocumentIR, str]:
    by_id = {b.id: i for i, b in enumerate(document.blocks)}
    for block in patch.blocks:
        block.provenance = Provenance(
            provider=patch.provider_id,
            stage="recover",
            source=block.provenance.source if block.provenance else document.source,
        )
        block.provider = patch.provider_id
        if block.id in by_id:
            old = document.blocks[by_id[block.id]]
            if not block.reading_order:
                block.reading_order = old.reading_order
            if block.page is None:
                block.page = old.page
            document.blocks[by_id[block.id]] = block
        else:
            document.blocks.append(block)
    md = markdown or ""
    for old, new in patch.markdown_replacements.items():
        if old and old in md:
            md = md.replace(old, new, 1)
    if patch.rebuild_markdown:
        md = document.to_markdown()
    if patch.blocks or patch.markdown_replacements or patch.rebuild_markdown:
        from app.core.repair import apply_markdown_rules

        md = apply_markdown_rules(md)
    document.provenance.append(Provenance(provider=patch.provider_id, stage="recover"))
    return document, md


def execute_recovery(
    request: RecoveryRequest,
    *,
    document: DocumentIR,
    markdown: str,
    handle: ProviderHandle | None = None,
    executors: dict[str, RecoverFn] | None = None,
) -> RecoveryPatch | None:
    request.attempts += 1
    if request.status == RecoveryStatus.REFUSED:
        return None
    if request.scope == RecoveryScope.DOCUMENT and request.required_capability in {
        Capability.PARSE_STRUCTURE,
        Capability.PARSE_TEXT,
    }:
        request.status = RecoveryStatus.REFUSED
        request.reason = "refuse_document_parser_fallback"
        return None
    handle = handle if handle is not None else resolve_recovery(request)
    if handle is None:
        request.status = RecoveryStatus.SKIPPED
        request.reason = request.reason or "no_provider"
        return None
    request.provider_id = handle.id
    fn = (executors or {}).get(request.required_capability)
    if fn is None and handle.provider is not None:
        recover_fn = getattr(handle.provider, "recover_blocks", None)
        if callable(recover_fn):
            patch = recover_fn(request, document, markdown)
            if patch is None:
                request.status = RecoveryStatus.SKIPPED
                request.reason = request.reason or "executor_empty"
                return None
            request.status = RecoveryStatus.RESOLVED
            request.reason = "patched"
            return patch
    if fn is None:
        request.status = RecoveryStatus.SKIPPED
        request.reason = "no_executor"
        return None
    patch = fn(request, document, markdown, handle)
    if patch is None:
        request.status = RecoveryStatus.SKIPPED
        request.reason = request.reason or "executor_empty"
        return None
    request.status = RecoveryStatus.RESOLVED
    request.reason = "patched"
    return patch


def run_recovery(
    *,
    quality: QualityReport,
    document: DocumentIR,
    markdown: str,
    budget: int = DEFAULT_BUDGET,
    page_count: int | None = None,
    executors: dict[str, RecoverFn] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> RecoveryOutcome:
    requests = plan_recovery(quality, document, budget=budget)
    changed = False
    current_doc = document
    current_md = markdown
    current_qa = quality
    for req in requests:
        if cancelled and cancelled():
            req.status = RecoveryStatus.SKIPPED
            req.reason = "cancelled"
            continue
        handle = resolve_recovery(req)
        patch = execute_recovery(
            req,
            document=current_doc,
            markdown=current_md,
            handle=handle,
            executors=executors,
        )
        if patch is None:
            continue
        current_doc, current_md = apply_patch(current_doc, current_md, patch)
        changed = True
    if changed:
        current_qa = run_unified_qa(
            current_md,
            document=current_doc,
            page_count=page_count if page_count is not None else (len(current_doc.pages) or None),
        )
    return RecoveryOutcome(
        requests=requests,
        document=current_doc,
        markdown=current_md,
        quality=current_qa,
        changed=changed,
    )


def _make_request(
    *,
    scope: str,
    page: int | None,
    block_ids: tuple[str, ...],
    capability: str,
    problem: str,
    evidence: dict[str, Any],
    status: str = RecoveryStatus.PENDING,
    reason: str = "",
) -> RecoveryRequest:
    return RecoveryRequest(
        id=uuid4().hex[:10],
        scope=scope,
        page=page,
        block_ids=tuple(block_ids),
        problem_type=problem,
        required_capability=capability,
        evidence=evidence,
        status=status,
        reason=reason,
    )


def _fatal_empty(quality: QualityReport) -> bool:
    if quality.status != QualityVerdict.FAILED.value:
        return False
    return any(
        c.check_id == "empty_document" and c.status == CheckStatus.FAIL.value for c in quality.checks
    )


def _pages_from_check(check) -> list[int]:
    pages: list[int] = []
    for item in check.affected_ids or []:
        m = _PAGE_ID_RE.match(str(item))
        if m:
            pages.append(int(m.group(1)))
    return pages


def _block_ids_from_check(check, document: DocumentIR | None) -> tuple[str, ...]:
    ids = [str(x) for x in (check.affected_ids or []) if str(x).startswith("b-")]
    if ids:
        return tuple(ids)
    if document is None:
        return ()
    known = {b.id for b in document.blocks}
    return tuple(str(x) for x in (check.affected_ids or []) if str(x) in known)


def _formula_fail_blocks(document: DocumentIR) -> tuple[str, ...]:
    out: list[str] = []
    for block in document.blocks:
        if _FORMULA_FAIL_RE.search(block.content or ""):
            out.append(block.id)
    return tuple(out)


def _pages_of_blocks(document: DocumentIR, block_ids: tuple[str, ...]) -> list[int]:
    wanted = set(block_ids)
    pages = []
    for block in document.blocks:
        if block.id in wanted and block.page is not None:
            pages.append(int(block.page))
    return sorted(set(pages))


def _broken_tables(document: DocumentIR) -> list[BlockIR]:
    broken: list[BlockIR] = []
    for block in document.blocks:
        if block.type != BLOCK_TABLE:
            continue
        rows = [ln for ln in (block.content or "").splitlines() if ln.strip().startswith("|")]
        if len(rows) < 2:
            broken.append(block)
            continue
        widths = [ln.count("|") for ln in rows]
        if widths and (max(widths) - min(widths)) >= 2:
            broken.append(block)
    return broken
