# -*- coding: utf-8 -*-
"""写回对齐：仅页码一致性（Gate 已在 OCR 阶段做过上下文否决）。"""
from __future__ import annotations

import re


def candidate_id_page(candidate_id: str) -> int | None:
    m = re.search(r"page(\d+)", candidate_id or "", re.I)
    return int(m.group(1)) if m else None


def pages_consistent(candidate_id: str, explicit_page: int | None) -> bool:
    """candidate_id 内页码与 OCR 行页码须一致（防 O-024 跨页串写）。

    ``page0`` 表示 Lean 入队时几何尚未解析（占位），以 OCR 实测页为准。
    """
    if explicit_page is None:
        return True
    cid_page = candidate_id_page(candidate_id)
    if cid_page is None:
        return True
    if cid_page == 0:
        return True
    return cid_page == int(explicit_page)
