# -*- coding: utf-8 -*-
"""Shadow OCR 行 → pending %dsid:% 槽位匹配（禁止任意 fallback）。"""
from __future__ import annotations

import re
from typing import Any

from app.formula.types import FormulaCandidate
from app.ocr.executor import eq_number_from_candidate

_DSID_RE = re.compile(r"%dsid:([A-Za-z0-9_.:-]+)%")


def match_shadow_row_to_pending(
    row: dict[str, Any],
    pending_by_id: dict[str, FormulaCandidate],
    pending_by_page_eq: dict[tuple[int | None, str], str],
    *,
    used: set[str],
) -> str | None:
    """将 shadow 行映射到唯一 pending candidate_id；无法确定则返回 None。"""

    def _take(cid: str) -> str | None:
        if cid and cid in pending_by_id and cid not in used:
            return cid
        return None

    cid = str(row.get("candidate_id") or "").strip()
    hit = _take(cid)
    if hit:
        return hit

    # 兼容旧 executor 临时 id：p7_eq3_12345 → page7_eq3
    m_legacy = re.match(r"^p(\d+)_eq([^_]+)_\d+$", cid, re.I)
    if m_legacy:
        hit = _take(f"page{m_legacy.group(1)}_eq{m_legacy.group(2)}")
        if hit:
            return hit

    orig = str(row.get("original") or "")
    m = _DSID_RE.search(orig)
    if m:
        hit = _take(m.group(1))
        if hit:
            return hit

    page = row.get("page")
    if page is not None:
        try:
            page = int(page)
        except (TypeError, ValueError):
            page = None
    eq = str(row.get("eq_number") or "").strip()
    if page is not None and eq:
        hit = _take(pending_by_page_eq.get((page, eq), ""))
        if hit:
            return hit

    return None


def build_pending_indexes(
    pending: list[tuple[str, FormulaCandidate]],
) -> tuple[dict[str, FormulaCandidate], dict[tuple[int | None, str], str]]:
    by_id = {cid: cand for cid, cand in pending}
    by_page_eq: dict[tuple[int | None, str], str] = {}
    for cid, cand in pending:
        eq = eq_number_from_candidate(cand)
        if not eq:
            continue
        key = (cand.page, eq)
        if key not in by_page_eq:
            by_page_eq[key] = cid
    return by_id, by_page_eq
