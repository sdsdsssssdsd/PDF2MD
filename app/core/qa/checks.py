"""R5 第一版确定性 QualityCheck。不引入 VLM judge。"""
from __future__ import annotations

import re
from typing import Any

from app.core.domain.document import BLOCK_FORMULA, DocumentIR
from app.core.domain.quality import CheckStatus, QualityCheckResult, make_check

_FIGURE_MARK_RE = re.compile(
    r"<!--\s*PDF2MD:IMAGE:|<!--\s*FIGURE\b|FIGURE_PLACEHOLDER|!\[\]\(\s*\)",
    re.I,
)
_FORMULA_FAIL_RE = re.compile(
    r"formula-not-decoded|公式未能可靠提取|Formula extraction failed",
    re.I,
)
_FAKE_URL_RE = re.compile(
    r"https?://(?:example\.invalid|localhost|example\.com)/[^\s)]*",
    re.I,
)
_PAGE_RE = re.compile(r"(?im)(?:^|\n)\s*(?:PAGE\s+(\d+)|<!--\s*PAGE\s+(\d+)\s*-->)")
_BEGIN_RE = re.compile(r"\\begin\{([A-Za-z*]+)\}")
_TAG_RE = re.compile(r"\\tag\{([^}]+)\}")
_EQ_PAREN_RE = re.compile(r"(?:Eq\.?\s*)?\((\d+[a-z]?)\)")


def check_empty_document(markdown: str) -> QualityCheckResult:
    ok = bool((markdown or "").strip())
    return make_check(
        "empty_document",
        status=CheckStatus.PASS.value if ok else CheckStatus.FAIL.value,
        blocking=not ok,
        fatal=not ok,
        score=1.0 if ok else 0.0,
        threshold=1.0,
        evidence={"chars": len(markdown or "")},
    )


def check_page_coverage(
    markdown: str,
    *,
    page_count: int | None = None,
    required_pages: list[int] | None = None,
) -> QualityCheckResult:
    text = markdown or ""
    found: set[int] = set()
    for m in _PAGE_RE.finditer(text):
        n = m.group(1) or m.group(2)
        if n:
            found.add(int(n))
    required = [int(x) for x in (required_pages or [])]
    if required:
        missing = [p for p in required if p not in found]
        if missing and not found and page_count:
            covered = page_count >= max(required)
            return make_check(
                "page_coverage",
                status=CheckStatus.PASS.value if covered else CheckStatus.FAIL.value,
                score=float(page_count) / float(max(required) or 1),
                threshold=1.0,
                evidence={"mode": "parser_pages", "page_count": page_count, "required": required},
                affected_ids=[] if covered else [f"page:{p}" for p in required],
            )
        status = CheckStatus.PASS.value if not missing else CheckStatus.FAIL.value
        return make_check(
            "page_coverage",
            status=status,
            score=1.0 - (len(missing) / max(1, len(required))),
            threshold=1.0,
            evidence={"found": sorted(found), "missing": missing, "required": required},
            affected_ids=[f"page:{p}" for p in missing],
        )
    if page_count and found:
        missing = [p for p in range(1, page_count + 1) if p not in found]
        status = CheckStatus.PASS.value if not missing else CheckStatus.WARN.value
        return make_check(
            "page_coverage",
            status=status,
            blocking=False,
            score=len(found) / max(1, page_count),
            threshold=1.0,
            evidence={"found": sorted(found), "missing": missing, "page_count": page_count},
            affected_ids=[f"page:{p}" for p in missing],
        )
    if page_count:
        return make_check(
            "page_coverage",
            status=CheckStatus.SKIP.value,
            blocking=False,
            evidence={"reason": "no_page_markers", "page_count": page_count},
        )
    return make_check(
        "page_coverage",
        status=CheckStatus.SKIP.value,
        blocking=False,
        evidence={"reason": "no_page_expectation"},
    )


def check_formula_unresolved(
    markdown: str,
    *,
    max_unresolved: int = 0,
    document: DocumentIR | None = None,
) -> QualityCheckResult:
    hits = _FORMULA_FAIL_RE.findall(markdown or "")
    n = len(hits)
    status = CheckStatus.PASS.value
    if n > max_unresolved:
        status = CheckStatus.FAIL.value if max_unresolved == 0 else CheckStatus.WARN.value
        if n > max(3, max_unresolved):
            status = CheckStatus.FAIL.value
    affected: list[str] = []
    if document is not None:
        for block in document.blocks:
            if _FORMULA_FAIL_RE.search(block.content or ""):
                affected.append(block.id)
    if not affected:
        affected = [str(h) for h in hits[:20]]
    return make_check(
        "formula_unresolved",
        status=status,
        score=0.0 if n else 1.0,
        threshold=float(max_unresolved),
        evidence={"count": n, "max_unresolved": max_unresolved},
        affected_ids=affected,
    )


def check_formula_structural(markdown: str, document: DocumentIR | None = None) -> QualityCheckResult:
    text = markdown or ""
    dollars = text.count("$$")
    odd_display = dollars % 2 != 0
    begins = _BEGIN_RE.findall(text)
    missing_end: list[str] = []
    for env in begins:
        if text.count(f"\\begin{{{env}}}") > text.count(f"\\end{{{env}}}") and env not in missing_end:
            missing_end.append(env)
    formula_blocks = 0
    formula_ids: list[str] = []
    if document is not None:
        formula_ids = [b.id for b in document.blocks if b.type == BLOCK_FORMULA]
        formula_blocks = len(formula_ids)
    bad = odd_display or bool(missing_end)
    return make_check(
        "formula_structural_validity",
        status=CheckStatus.FAIL.value if bad else CheckStatus.PASS.value,
        score=0.0 if bad else 1.0,
        threshold=1.0,
        evidence={
            "display_fence_count": dollars,
            "odd_display": odd_display,
            "unclosed_envs": missing_end,
            "formula_blocks": formula_blocks,
        },
        affected_ids=[f"env:{e}" for e in missing_end],
    )


def _normalize_eq_id(raw: str) -> str:
    t = (raw or "").strip()
    t = t.strip("()")
    t = t.replace("\\tag{", "").replace("}", "")
    return t


def found_equation_ids(markdown: str) -> set[str]:
    text = markdown or ""
    out: set[str] = set()
    for m in _TAG_RE.finditer(text):
        out.add(_normalize_eq_id(m.group(1)))
    for m in _EQ_PAREN_RE.finditer(text):
        out.add(_normalize_eq_id(m.group(1)))
    return {x for x in out if x}


def check_equation_numbers(
    markdown: str,
    *,
    required_ids: list[str] | None = None,
) -> QualityCheckResult:
    required = [_normalize_eq_id(x) for x in (required_ids or []) if str(x).strip()]
    found = found_equation_ids(markdown)
    if not required:
        return make_check(
            "equation_number_preservation",
            status=CheckStatus.SKIP.value if not found else CheckStatus.PASS.value,
            blocking=False,
            evidence={"found": sorted(found)},
            affected_ids=[f"eq:{i}" for i in sorted(found)],
        )
    missing = [i for i in required if i not in found]
    return make_check(
        "equation_number_preservation",
        status=CheckStatus.PASS.value if not missing else CheckStatus.FAIL.value,
        score=1.0 - (len(missing) / max(1, len(required))),
        threshold=1.0,
        evidence={"required": required, "found": sorted(found), "missing": missing},
        affected_ids=[f"eq:{i}" for i in missing],
    )


def check_text_anchors(
    markdown: str,
    *,
    anchors: list[str] | None = None,
) -> QualityCheckResult:
    needles = [a for a in (anchors or []) if str(a).strip()]
    if not needles:
        return make_check(
            "text_anchor_preservation",
            status=CheckStatus.SKIP.value,
            blocking=False,
            evidence={"reason": "no_anchors"},
        )
    text = markdown or ""
    missing = [a for a in needles if a not in text]
    return make_check(
        "text_anchor_preservation",
        status=CheckStatus.PASS.value if not missing else CheckStatus.FAIL.value,
        score=1.0 - (len(missing) / len(needles)),
        threshold=1.0,
        evidence={"missing": missing, "total": len(needles)},
        affected_ids=[f"anchor:{a}" for a in missing],
    )


def check_placeholders(markdown: str) -> QualityCheckResult:
    text = markdown or ""
    figs = _FIGURE_MARK_RE.findall(text)
    fakes = list(_FAKE_URL_RE.findall(text))
    n = len(figs) + len(fakes)
    if n == 0:
        status = CheckStatus.PASS.value
    elif n < 3:
        status = CheckStatus.WARN.value
    else:
        status = CheckStatus.FAIL.value
    return make_check(
        "placeholder_or_fake_url",
        status=status,
        blocking=status == CheckStatus.FAIL.value,
        score=0.0 if n else 1.0,
        evidence={"figure_markers": len(figs), "fake_urls": fakes[:8], "count": n},
        affected_ids=[str(u) for u in fakes[:8]],
    )


def check_retry_exhaustion(context: dict[str, Any] | None = None) -> QualityCheckResult:
    ctx = dict(context or {})
    recovery = dict(ctx.get("recovery") or {})
    attempted = int(recovery.get("attempted") or ctx.get("retries") or 0)
    accepted = int(recovery.get("accepted") or 0)
    exhausted = bool(ctx.get("recovery_exhausted"))
    if attempted <= 0 and not exhausted:
        return make_check(
            "retry_recovery_exhaustion",
            status=CheckStatus.SKIP.value,
            blocking=False,
            evidence={"reason": "no_recovery"},
        )
    failed = exhausted or (attempted >= 8 and accepted == 0)
    warn = attempted >= 4 and accepted == 0
    if failed:
        status = CheckStatus.FAIL.value
    elif warn:
        status = CheckStatus.WARN.value
    else:
        status = CheckStatus.PASS.value
    return make_check(
        "retry_recovery_exhaustion",
        status=status,
        evidence={"attempted": attempted, "accepted": accepted, "exhausted": exhausted},
    )


def check_forbidden_markers(markdown: str, markers: list[str] | None = None) -> QualityCheckResult:
    needles = [m for m in (markers or []) if m]
    if not needles:
        return make_check(
            "forbidden_markers",
            status=CheckStatus.SKIP.value,
            blocking=False,
            evidence={"reason": "none"},
        )
    text = markdown or ""
    hit = [m for m in needles if m in text]
    return make_check(
        "forbidden_markers",
        status=CheckStatus.FAIL.value if hit else CheckStatus.PASS.value,
        evidence={"hit": hit},
        affected_ids=list(hit),
    )
