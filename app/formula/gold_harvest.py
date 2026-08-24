# -*- coding: utf-8 -*-
"""从 Academic100 PDF 收 display 式候选。禁止自动 verified / 禁止当伪标签训练。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from app.formula.crop_cache import language_from_stem
from app.formula.gold_crop import (
    cluster_is_label_only,
    detect_text_column,
    grow_equation_cluster,
    iter_page_lines,
    line_eq_number,
    looks_like_formula_line,
    looks_like_math_fragment,
    looks_like_prose,
)
from app.formula.gold_schema import FormulaGoldRecord

_EQ_ONLY = re.compile(r"^[\(（]\s*\d{1,3}[a-z]?\s*[\)）]$")


def is_right_margin_eq_label(text: str, x0: float, page_w: float) -> str:
    """栏右侧 (n) / 公式行尾 (n)。不要把小节标题、求和上下标收进来。

    双栏论文左栏编号常在页宽 36%～52%（左栏右缘），不能只用整页右半。
    仍拒绝页左缘列表号 / 小节号。
    """
    t = (text or "").strip()
    eq = line_eq_number(t)
    if not eq:
        return ""
    if _EQ_ONLY.fullmatch(t):
        return eq if x0 >= page_w * 0.36 else ""
    if looks_like_prose(t):
        return ""
    if looks_like_formula_line(t) or "=" in t:
        return eq
    return ""


@dataclass
class HarvestHit:
    page: int
    equation_number: str
    bbox: list[float]
    preview: str


def harvest_page(page: Any, page_index: int) -> list[HarvestHit]:
    page_w = float(page.rect.width)
    lines = iter_page_lines(page)
    hits: list[HarvestHit] = []
    seen_eq: set[str] = set()
    for ln in lines:
        eq = is_right_margin_eq_label(ln.text, ln.x0, page_w)
        if not eq or eq in seen_eq:
            continue
        dummy_seed = [ln.x0 - 80.0, ln.y0 - 8.0, ln.x1 + 4.0, ln.y1 + 8.0]
        col = detect_text_column(page, dummy_seed)
        cluster = grow_equation_cluster(
            lines, ln, seed=dummy_seed, equation_number=eq, column=col
        )
        if cluster_is_label_only(cluster):
            continue
        cluster = [m for m in cluster if not looks_like_prose(m.text)]
        if cluster_is_label_only(cluster) or not cluster:
            continue
        if not any(looks_like_math_fragment(m.text) for m in cluster if m is not ln):
            if not any("=" in (m.text or "") for m in cluster):
                continue
        box = [
            min(m.x0 for m in cluster),
            min(m.y0 for m in cluster),
            max(m.x1 for m in cluster),
            max(m.y1 for m in cluster),
        ]
        if box[2] - box[0] < 48.0 or box[3] - box[1] < 7.0:
            continue
        preview = " ".join((m.text or "").strip() for m in cluster if not looks_like_prose(m.text))
        if looks_like_prose(preview) and "=" not in preview:
            continue
        seen_eq.add(eq)
        hits.append(
            HarvestHit(
                page=page_index,
                equation_number=eq,
                bbox=box,
                preview=preview[:180],
            )
        )
    return hits


def harvest_pdf(
    pdf_path: Path,
    *,
    pdf_id: str,
    language: str = "",
    skip_keys: Iterable[tuple[str, int, str]] | None = None,
    per_paper: int = 4,
    skip_cover: bool = True,
) -> list[dict[str, Any]]:
    import pymupdf

    skip = set(skip_keys or [])
    lang = language or language_from_stem(pdf_id)
    doc = pymupdf.open(str(pdf_path))
    rows: list[dict[str, Any]] = []
    try:
        n = len(doc)
        start = 1 if skip_cover and n > 3 else 0
        end = n
        for idx in range(start, end):
            if len(rows) >= per_paper:
                break
            for hit in harvest_page(doc[idx], idx):
                key = (pdf_id, hit.page, hit.equation_number)
                if key in skip:
                    continue
                skip.add(key)
                rec = FormulaGoldRecord(
                    id=f"{pdf_id}_p{hit.page}_eq{hit.equation_number}_h",
                    pdf_id=pdf_id,
                    language=lang,
                    page=hit.page,
                    bbox_pdf=hit.bbox,
                    equation_number=hit.equation_number,
                    tags=["needs_human_gt", "harvest_display"],
                    notes=f"harvest_display; do_not_train; preview={hit.preview[:80]}",
                    verified=False,
                    split="regression",
                )
                rows.append(rec.to_dict())
                if len(rows) >= per_paper:
                    break
    finally:
        doc.close()
    return rows
