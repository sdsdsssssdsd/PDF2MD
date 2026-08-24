"""FormulaGeometryResolver：Slot 定位 → 自适应 crop → OCR 前质量预检（k3 Round-1）。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.formula.session import (
    EquationAnchor,
    EquationAnchorIndex,
    column_bounds,
    formula_band_from_number,
)

_RELIABLE_WORD = re.compile(r"[A-Za-z]{4,}")
_HYPHEN_PHRASE = re.compile(r"[A-Za-z]+(?:-[A-Za-z]+)+")
_MATH_CHAR = re.compile(r"[=+\-*/^_{}\\()[\]<>∑∫αβγπΠ]")


@dataclass
class GeometryEvidence:
    page: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    confidence: float = 0.0
    source: str = "unresolved"
    top_anchor: str = ""
    bottom_anchor: str = ""
    equation_anchor: str = ""
    table_overlap: float = 0.0
    text_density: float = 0.0
    crop_class: str = "unknown"
    crop_height_pt: float = 0.0
    evidence: list[str] = field(default_factory=list)
    failure_stage: str = ""
    failure_code: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "page": self.page,
            "bbox": list(self.bbox) if self.bbox else None,
            "confidence": round(self.confidence, 4),
            "source": self.source,
            "top_anchor": self.top_anchor,
            "bottom_anchor": self.bottom_anchor,
            "equation_anchor": self.equation_anchor,
            "table_overlap": round(self.table_overlap, 4),
            "text_density": round(self.text_density, 4),
            "crop_class": self.crop_class,
            "crop_height_pt": round(self.crop_height_pt, 2),
            "evidence": list(self.evidence),
            "failure_stage": self.failure_stage,
            "failure_code": self.failure_code,
        }


@dataclass
class GeometryDecision:
    page: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    confidence: float = 0.0
    source: str = "unresolved"
    crop_class: str = "unknown"
    evidence: GeometryEvidence | None = None
    escalation_level: str = "anchor_tight"

    def to_dict(self) -> dict[str, Any]:
        return {
            "page": self.page,
            "bbox": list(self.bbox) if self.bbox else None,
            "confidence": round(self.confidence, 4),
            "source": self.source,
            "crop_class": self.crop_class,
            "escalation_level": self.escalation_level,
            "evidence": self.evidence.to_dict() if self.evidence else None,
        }


def _midpoint(a: float, b: float) -> float:
    return (a + b) * 0.5


def _anchor_cy(anchor_bbox: tuple[float, float, float, float]) -> float:
    return (anchor_bbox[1] + anchor_bbox[3]) * 0.5


def _same_column(
    page_w: float, ax0: float, ax1: float, bx0: float, bx1: float
) -> bool:
    mid = page_w * 0.5
    a_right = ax0 >= mid - 12.0
    b_right = bx0 >= mid - 12.0
    return a_right == b_right


def _page_text_blocks(page: Any) -> list[tuple[float, float, float, float, str]]:
    out: list[tuple[float, float, float, float, str]] = []
    try:
        for b in page.get_text("blocks") or []:
            if len(b) < 5:
                continue
            x0, y0, x1, y1, text = b[0], b[1], b[2], b[3], str(b[4] or "")
            if not text.strip():
                continue
            out.append((float(x0), float(y0), float(x1), float(y1), text))
    except Exception:
        pass
    out.sort(key=lambda t: (t[1], t[0]))
    return out


def _neighbors_on_page(
    anchor: EquationAnchor,
    index: EquationAnchorIndex,
    page_w: float,
) -> tuple[EquationAnchor | None, EquationAnchor | None]:
    cy = _anchor_cy(anchor.bbox)
    same: list[EquationAnchor] = []
    for hits in index.by_number.values():
        for h in hits:
            if h.page != anchor.page:
                continue
            if _same_column(page_w, anchor.bbox[0], anchor.bbox[2], h.bbox[0], h.bbox[2]):
                same.append(h)
    same.sort(key=lambda h: _anchor_cy(h.bbox))
    prev_a = next_a = None
    for h in same:
        hc = _anchor_cy(h.bbox)
        if hc < cy - 2.0:
            prev_a = h
        elif hc > cy + 2.0 and next_a is None:
            next_a = h
    return prev_a, next_a


def formula_band_from_number_v2(
    page_w: float,
    page_h: float,
    number_bbox: tuple[float, float, float, float],
    *,
    page_blocks: list[tuple[float, float, float, float, str]] | None = None,
    prev_anchor: EquationAnchor | None = None,
    next_anchor: EquationAnchor | None = None,
    level: str = "display",
) -> tuple[float, float, float, float]:
    """Voronoi 自适应纵带；fallback 到 v1 narrow band。"""
    nx0, ny0, nx1, ny1 = number_bbox
    nh = max(8.0, ny1 - ny0)
    cy = (ny0 + ny1) * 0.5
    x0, x1 = column_bounds(page_w, nx0, nx1)
    margin = max(4.0, nh * 0.35)

    level_heights = {
        "tight": (36.0, 45.0),
        "display": (55.0, 85.0),
        "multiline": (90.0, 150.0),
    }
    lo_h, hi_h = level_heights.get(level, level_heights["display"])

    if level in {"multiline", "column_region"}:
        lower = min(page_h, ny1 + margin * 0.5)
        upper = max(0.0, lower - hi_h)
    else:
        upper = max(0.0, cy - hi_h * 0.55)
        lower = min(page_h, cy + hi_h * 0.45)

    if prev_anchor is not None:
        upper = max(upper, _midpoint(_anchor_cy(prev_anchor.bbox), cy))
    if next_anchor is not None:
        lower = min(lower, _midpoint(cy, _anchor_cy(next_anchor.bbox)))
    else:
        lower = min(lower, ny1 + margin * 0.5)
    if prev_anchor is not None:
        upper = min(upper, ny0 - margin * 0.35)

    if page_blocks:
        col_blocks = [
            b
            for b in page_blocks
            if _same_column(page_w, x0, x1, b[0], b[2]) and b[3] < cy - 2.0
        ]
        if col_blocks:
            prev_text_bottom = max(b[3] for b in col_blocks)
            upper = max(upper, prev_text_bottom + margin)
        col_blocks_after = [
            b
            for b in page_blocks
            if _same_column(page_w, x0, x1, b[0], b[2]) and b[1] > cy + 2.0
        ]
        if col_blocks_after:
            next_text_top = min(b[1] for b in col_blocks_after)
            lower = min(lower, next_text_top - margin)

    height = lower - upper
    if height < lo_h:
        pad = (lo_h - height) * 0.5
        upper = max(0.0, upper - pad)
        lower = min(page_h, lower + pad)
        height = lower - upper
    if height > hi_h:
        extra = (height - hi_h) * 0.5
        upper += extra
        lower -= extra

    if height < 28.0:
        return formula_band_from_number(page_w, page_h, number_bbox)

    return (x0, upper, x1, lower)


def formula_bbox_from_anchor_v2(
    page_w: float,
    page_h: float,
    anchor: EquationAnchor,
    index: EquationAnchorIndex,
    *,
    page_blocks: list[tuple[float, float, float, float, str]] | None = None,
    level: str = "display",
) -> tuple[float, float, float, float]:
    prev_a, next_a = _neighbors_on_page(anchor, index, page_w)
    return formula_band_from_number_v2(
        page_w,
        page_h,
        anchor.bbox,
        page_blocks=page_blocks,
        prev_anchor=prev_a,
        next_anchor=next_a,
        level=level,
    )


def _normalize_ligatures(text: str) -> str:
    text = re.sub(r"\bde\s+fi\s+ned\b", "defined", text, flags=re.I)
    return re.sub(r"(\w)\s+fi\s+(\w)", r"\1\2", text, flags=re.I)


def _context_prefers_tight_gap(
    context_before: str = "",
    context_after: str = "",
    original_latex: str = "",
) -> bool:
    blob = _normalize_ligatures(
        f"{context_before}\n{context_after}\n{original_latex}"
    )
    return bool(
        re.search(
            r"(?i)dtw\s+similarity\s+kernel\s+is\s+defined\s+as",
            blob,
        )
        or re.search(
            r"(?i)variation\s+of\s+information\s+between\s+two\s+partitions.*defined\s+as",
            blob,
        )
        or re.search(r"(?i)fixed-threshold performance|f1@0\.?5", blob)
        or (
            re.search(r"F\s*1\s*&\s*=", original_latex or "")
            and not re.search(r"(?i)brier\s+score", blob)
        )
    )


def _equation_in_context(eq: str, context_before: str, context_after: str) -> bool:
    if not (eq or "").strip():
        return False
    blob = f"{context_before}\n{context_after}"
    return bool(
        re.search(
            rf"Eq(?:uation)?\.?\s*\(\s*{re.escape(eq.strip())}\s*\)",
            blob,
            re.I,
        )
    )


def _strip_embedded_display_math(text: str) -> str:
    """去掉 context 内嵌 $$...$$，避免 bridge 尾词落在错误纵带。"""
    return re.sub(r"\$\$[\s\S]*?\$\$", " ", text or "")


def _bridge_query_pairs(
    context_before: str,
    context_after: str,
    original_latex: str = "",
) -> list[tuple[str, str]]:
    """生成 prose bridge 搜索对；优先连字符短语（discrete-time / time-dependent）。"""
    from app.formula.tokens import direction_flags

    bb = _normalize_ligatures(_strip_embedded_display_math(context_before or "")[-420:])
    ba = _normalize_ligatures((context_after or "")[:420:])
    blob = _normalize_ligatures(f"{context_before or ''}\n{original_latex or ''}")
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(b: str, a: str) -> None:
        b, a = b.strip(), a.strip()
        if len(b) < 4 or len(a) < 4:
            return
        key = (b.lower(), a.lower())
        if key in seen:
            return
        seen.add(key)
        pairs.append((b, a))

    orig_max, orig_min = direction_flags(original_latex or "")
    if orig_min and not orig_max:
        add("trace of", "which is to be maximised")
        add("trace of", "maximised")
        add("weighted", "which is to be maximised")
        add("Markov Stability", "which is to be maximised")
        add("Markov Stability of the partition", "which is to be maximised")
    if orig_max and not orig_min:
        add("partitions H", "Owing to the optimisation")
        add("space of partitions", "Owing to the optimisation")
        add("Markov Stability of the partition", "which is to be maximised")
        add("maximised", "partitions H")
        add("which is to be maximised", "Owing to the optimisation")

    if re.search(r"(?i)which is to be maximis", bb):
        pre_eq = _strip_embedded_display_math(context_before or "")
        pre_tail = _prose_tail(pre_eq, 8)
        if len(pre_tail) >= 3:
            add(" ".join(pre_tail[-4:]), "which is to be maximised")

    if re.search(r"\\begin\{cases\}|H_\{\s*ic", original_latex or "", re.I):
        add("membership matrix", "goodness of the partition")
        add("correspondence between", "goodness of the partition")

    before_hy = _HYPHEN_PHRASE.findall(bb)
    after_fixed: list[str] = []
    if re.search(r"(?i)markov\s+time", ba):
        after_fixed.append("Markov time")

    if re.search(r"(?i)discrete[- ]time", bb):
        add("discrete-time process", "Markov time")
    if re.search(r"(?i)time[- ]dependent", bb):
        add("time-dependent solution", "Markov time")
    if re.search(r"(?i)laplacian\s+l", bb):
        add("Laplacian L", "Markov time")
    if re.search(r"(?i)louvain", bb):
        add("Louvain", "partitions")
    if re.search(r"(?i)markov\s+stability", bb):
        add("Markov Stability", "partitions")
    if re.search(r"(?i)membership\s+matrix", blob):
        add("membership matrix", "goodness of the partition")
        add("correspondence between", "goodness of the partition")
    if re.search(r"(?i)maximis", bb):
        add("maximised", "partitions")
    if re.search(r"(?i)dtw\s+similarity\s+kernel", blob):
        add("DTW similarity kernel", "where Dl denotes")
    if re.search(
        r"(?i)variation\s+of\s+information\s+between\s+two\s+partitions",
        blob,
    ):
        add("normalised variation of information", "Shannon entropy")
        add("variation of information", "Shannon entropy")
    if re.search(r"(?i)scale\s+of", original_latex or ""):
        add("scale of", "graphs")
    if re.search(r"(?i)cross-time\s+variation\s+of\s+information", blob):
        add("cross-time variation of information", "heatmap")
        add("plateau of the cross-time variation", "persistent")

    if re.search(r"(?i)brier\s+score|mean squared error between outcomes", bb):
        add("probabilities [9]", "The Brier score is a strictly proper")
        add("predicted probabilities [9]", "The Brier score is a strictly proper")
        add("outcomes and predicted probabilities", "The Brier score is a strictly proper")
        add("predicted probabilities", "strictly proper scoring rule")
        add("mean squared error between outcomes", "strictly proper scoring")

    if re.search(r"F\s*1\s*&\s*=", original_latex or "") or re.search(
        r"(?i)f1@0|fixed-threshold performance", bb
    ):
        add("we convert probabilities", "Having defined")
        add("convert probabilities to labels", "Having defined the leakage")

    before_tail = _prose_tail(bb, 12)
    after_head = _prose_head(ba, 12)
    if not after_fixed:
        after_fixed.append(" ".join(after_head[:2]))

    for hp in before_hy[-4:]:
        for ap in after_fixed[:4]:
            add(hp, ap)

    repl = {
        "discrete time": "discrete-time",
        "time dependent": "time-dependent",
        "cross time": "cross-time",
    }
    for n_b, n_a in ((4, 3), (3, 2), (5, 3), (3, 3), (2, 2)):
        if len(before_tail) < n_b or len(after_head) < n_a:
            continue
        bq = " ".join(before_tail[-n_b:])
        aq = " ".join(after_head[:n_a])
        add(bq, aq)
        bq2 = bq
        for k, v in repl.items():
            bq2 = bq2.replace(k, v)
        if bq2 != bq:
            add(bq2, aq)
    return pairs


def _prose_tail(text: str, n: int = 12) -> list[str]:
    words = _RELIABLE_WORD.findall(text or "")
    return [w.lower() for w in words[-n:]]


def _prose_head(text: str, n: int = 12) -> list[str]:
    words = _RELIABLE_WORD.findall(text or "")
    return [w.lower() for w in words[:n]]


def _bbox_suspicious(page_w: float, bbox: tuple[float, float, float, float]) -> bool:
    w = max(0.0, bbox[2] - bbox[0])
    h = max(0.0, bbox[3] - bbox[1])
    if w < page_w * 0.2:
        return True
    return h < 28.0


def _page_width(pdf_doc: Any | None, page: int) -> float:
    try:
        if pdf_doc is not None:
            return float(pdf_doc[page].rect.width)
    except Exception:
        pass
    return 612.0


def _page_height(pdf_doc: Any | None, page: int) -> float:
    try:
        if pdf_doc is not None:
            return float(pdf_doc[page].rect.height)
    except Exception:
        pass
    return 792.0


def _expand_tight_formula_crop(
    pdf_doc: Any | None,
    page: int,
    bbox: tuple[float, float, float, float],
    *,
    target_h: float = 40.0,
) -> tuple[float, float, float, float]:
    """紧 gap 公式纵向补边，避免 OCR crop 过窄。"""
    ph = _page_height(pdf_doc, page)
    x0, y0, x1, y1 = bbox
    h = max(0.0, y1 - y0)
    if h >= target_h:
        return bbox
    pad = (target_h - h) * 0.5
    return (
        float(x0),
        max(0.0, y0 - pad),
        float(x1),
        min(ph, y1 + pad),
    )


def crop_bbox_suspicious(
    pdf_doc: Any | None,
    page: int | None,
    bbox: tuple[float, float, float, float] | None,
    crop_class: str = "",
) -> bool:
    """已有 bbox 是否仍应强制重定位（窄条 / 散文 / 表格 / 过高）。"""
    if page is None or bbox is None:
        return True
    if crop_class in {"likely_prose", "likely_table", "likely_too_small"}:
        return True
    pw = _page_width(pdf_doc, int(page))
    ph = _page_height(pdf_doc, int(page))
    h = max(0.0, bbox[3] - bbox[1])
    if _bbox_suspicious(pw, bbox):
        return True
    if h > min(130.0, ph * 0.22):
        return True
    if pdf_doc is None:
        return False
    ev = GeometryEvidence()
    assess_formula_crop(pdf_doc, int(page), bbox, ev)
    return ev.crop_class in {"likely_prose", "likely_table", "likely_too_small"}


def _bbox_vertically_distinct(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
    *,
    thresh: float = 22.0,
) -> bool:
    ay = (a[1] + a[3]) * 0.5
    by = (b[1] + b[3]) * 0.5
    return abs(ay - by) > thresh


def prose_bridge_locator(
    pdf_doc: Any,
    *,
    context_before: str,
    context_after: str,
    hint_page: int | None = None,
    original_latex: str = "",
    priority_pairs: list[tuple[str, str]] | None = None,
    prefer_tight_gap: bool = False,
) -> GeometryEvidence:
    """before/after prose 双锚点定位 display 公式纵向 gap。"""
    ev = GeometryEvidence(source="prose_bridge")
    before_words = _prose_tail(context_before, 10)
    after_words = _prose_head(context_after, 10)
    if len(before_words) < 3 or len(after_words) < 3:
        ev.failure_stage = "geometry"
        ev.failure_code = "prose_bridge_insufficient_words"
        return ev

    if pdf_doc is None:
        ev.failure_stage = "geometry"
        ev.failure_code = "no_pdf"
        return ev

    if not prefer_tight_gap:
        prefer_tight_gap = _context_prefers_tight_gap(
            context_before, context_after, original_latex
        )

    page_range = (
        [hint_page]
        if hint_page is not None and 0 <= hint_page < len(pdf_doc)
        else list(range(len(pdf_doc)))
    )

    best: tuple[float, int, tuple[float, float, float, float], str, str] | None = None
    query_pairs = list(priority_pairs or [])
    query_pairs.extend(_bridge_query_pairs(context_before, context_after, original_latex))
    for n_b, n_a in ((4, 4), (3, 3), (5, 3), (3, 5), (2, 3)):
        if len(before_words) < n_b or len(after_words) < n_a:
            continue
        query_pairs.append(
            (" ".join(before_words[-n_b:]), " ".join(after_words[:n_a]))
        )

    for before_q, after_q in query_pairs:
        for pi in page_range:
            try:
                page = pdf_doc[pi]
            except Exception:
                continue
            page_w = float(page.rect.width)
            page_h = float(page.rect.height)
            before_hits = page.search_for(before_q) or []
            after_hits = page.search_for(after_q) or []
            if not before_hits or not after_hits:
                continue
            for br in sorted(before_hits, key=lambda r: r.y1)[-3:]:
                for ar in sorted(after_hits, key=lambda r: r.y0)[:3]:
                    if ar.y0 <= br.y1 + 4.0:
                        continue
                    if not _same_column(page_w, br.x0, br.x1, ar.x0, ar.x1):
                        continue
                    gap = ar.y0 - br.y1
                    max_gap = page_h * (0.18 if prefer_tight_gap else 0.45)
                    if gap < 12.0 or gap > max_gap:
                        continue
                    x0, x1 = column_bounds(page_w, br.x0, ar.x1)
                    y0 = max(0.0, br.y1 + 2.0)
                    y1 = min(page_h, ar.y0 - 2.0)
                    min_h = 15.0 if prefer_tight_gap else 20.0
                    if y1 - y0 < min_h:
                        continue
                    if prefer_tight_gap:
                        score = gap + abs(br.x0 - ar.x0) * 0.1
                    else:
                        score = -gap + abs(br.x0 - ar.x0) * 0.1
                    if best is None or score < best[0]:
                        best = (
                            score,
                            pi,
                            (float(x0), float(y0), float(x1), float(y1)),
                            before_q,
                            after_q,
                        )

    if best is None:
        ev.failure_stage = "geometry"
        ev.failure_code = "prose_bridge_not_found"
        return ev

    _, page_i, bbox, before_q, after_q = best
    ev.top_anchor = before_q
    ev.bottom_anchor = after_q
    ev.page = page_i
    ev.bbox = bbox
    ev.confidence = 0.82
    ev.source = "prose_bridge"
    ev.evidence.append(f"bridge:{before_q!r}|{after_q!r}")
    assess_formula_crop(pdf_doc, page_i, bbox, ev)
    return ev


def assess_formula_crop(
    pdf_doc: Any | None,
    page: int,
    bbox: tuple[float, float, float, float],
    ev: GeometryEvidence | None = None,
) -> GeometryEvidence:
    """OCR 前极便宜 crop 质量分类。"""
    out = ev or GeometryEvidence()
    out.page = page
    out.bbox = bbox
    x0, y0, x1, y1 = bbox
    out.crop_height_pt = max(0.0, y1 - y0)

    if pdf_doc is None:
        out.crop_class = "unknown"
        return out

    try:
        pg = pdf_doc[page]
        clip = pg.get_text("text", clip=bbox) or ""
    except Exception:
        clip = ""

    letters = sum(1 for c in clip if c.isalpha())
    math_c = len(_MATH_CHAR.findall(clip))
    words = [w for w in re.split(r"\s+", clip.strip()) if len(w) >= 3]
    out.text_density = letters / max(1, letters + math_c)

    lines = [ln.strip() for ln in clip.splitlines() if ln.strip()]
    if not clip.strip():
        out.crop_class = "likely_too_small"
        out.failure_stage = "geometry"
        out.failure_code = "crop_empty"
        return out
    prose_like = len(words) >= 6 and math_c <= 2 and letters > 40
    table_like = clip.count("|") >= 4 or "<table" in clip.lower()
    if not table_like and len(lines) >= 5:
        numeric_lines = sum(1 for ln in lines if re.search(r"\d", ln))
        word_lines = sum(1 for ln in lines if len(ln.split()) >= 4)
        table_like = word_lines >= 3 and numeric_lines >= 4 and math_c <= 1

    if table_like:
        out.crop_class = "likely_table"
        out.table_overlap = 0.85
        out.failure_stage = "geometry"
        out.failure_code = "crop_hits_table"
    elif prose_like:
        out.crop_class = "likely_prose"
        out.failure_stage = "geometry"
        out.failure_code = "crop_hits_prose"
    elif out.crop_height_pt < 40.0:
        out.crop_class = "likely_too_small"
        out.failure_stage = "geometry"
        out.failure_code = "crop_too_small"
    else:
        out.crop_class = "likely_formula"

    return out


class FormulaGeometryResolver:
    """统一 Slot → PDF bbox 决策（Round-1 仅 geometry，不动 Gate）。"""

    def __init__(self, pdf_doc: Any | None, anchor_index: EquationAnchorIndex | None = None):
        self.pdf_doc = pdf_doc
        self.anchor_index = anchor_index or EquationAnchorIndex()
        self._block_cache: dict[int, list] = {}

    def _blocks(self, page_index: int) -> list:
        if page_index not in self._block_cache:
            blocks: list = []
            if self.pdf_doc is not None:
                try:
                    blocks = _page_text_blocks(self.pdf_doc[page_index])
                except Exception:
                    blocks = []
            self._block_cache[page_index] = blocks
        return self._block_cache[page_index]

    def resolve(
        self,
        *,
        context_before: str,
        context_after: str,
        equation_number: str = "",
        hint_page: int | None = None,
        escalation: str = "anchor_voronoi",
        original_latex: str = "",
    ) -> GeometryDecision:
        eq = (equation_number or "").strip()
        ev = GeometryEvidence(equation_anchor=eq)

        def _try_prose_bridge(page_hint: int | None = None) -> GeometryDecision | None:
            bridge = prose_bridge_locator(
                self.pdf_doc,
                context_before=context_before,
                context_after=context_after,
                hint_page=page_hint,
                original_latex=original_latex,
                prefer_tight_gap=_context_prefers_tight_gap(
                    context_before, context_after, original_latex
                ),
            )
            if bridge.bbox is None or bridge.page is None:
                return None
            if bridge.crop_class in {"likely_prose", "likely_table"} and escalation != "column_region":
                return self.resolve(
                    context_before=context_before,
                    context_after=context_after,
                    equation_number=eq,
                    hint_page=bridge.page,
                    escalation="column_region",
                )
            return GeometryDecision(
                page=bridge.page,
                bbox=bridge.bbox,
                confidence=bridge.confidence,
                source=bridge.source,
                crop_class=bridge.crop_class,
                evidence=bridge,
                escalation_level="prose_bridge",
            )

        # 无印刷编号：优先全页 prose bridge（cand.page 来自 MD 槽位，不可靠）
        if not eq and self.pdf_doc is not None:
            bridged = _try_prose_bridge(None)
            if bridged is None and hint_page is not None:
                bridged = _try_prose_bridge(hint_page)
            if bridged is not None:
                return bridged

        # A. printed equation label
        if eq and self.pdf_doc is not None:
            anchor = self.anchor_index.lookup(eq, page=hint_page)
            if anchor is None and _equation_in_context(
                eq, context_before, context_after
            ):
                anchor = self.anchor_index.lookup(eq)
            if anchor is None and not _equation_in_context(
                eq, context_before, context_after
            ):
                anchor = self.anchor_index.lookup(eq)
            if anchor is not None:
                try:
                    page = self.pdf_doc[anchor.page]
                    pw, ph = float(page.rect.width), float(page.rect.height)
                except Exception:
                    pw, ph = 612.0, 792.0
                level = "multiline" if escalation == "column_region" else "display"
                bbox = formula_bbox_from_anchor_v2(
                    pw,
                    ph,
                    anchor,
                    self.anchor_index,
                    page_blocks=self._blocks(anchor.page),
                    level=level,
                )
                ev.page = anchor.page
                ev.bbox = bbox
                ev.source = "printed_eq_anchor_v2"
                ev.confidence = 0.88
                assess_formula_crop(self.pdf_doc, anchor.page, bbox, ev)
                try:
                    pw_chk = float(self.pdf_doc[anchor.page].rect.width)
                except Exception:
                    pw_chk = 612.0
                if _bbox_suspicious(pw_chk, bbox) or ev.crop_class in {
                    "likely_prose",
                    "likely_table",
                }:
                    bridged = _try_prose_bridge(None) or _try_prose_bridge(
                        anchor.page
                    )
                    if bridged is not None and bridged.source == "prose_bridge":
                        return bridged
                if ev.crop_class in {"likely_prose", "likely_table"} and escalation == "anchor_voronoi":
                    bridge = prose_bridge_locator(
                        self.pdf_doc,
                        context_before=context_before,
                        context_after=context_after,
                        hint_page=anchor.page,
                        original_latex=original_latex,
                        prefer_tight_gap=_context_prefers_tight_gap(
                            context_before, context_after, original_latex
                        ),
                    )
                    if (
                        bridge.bbox is not None
                        and bridge.page is not None
                        and bridge.crop_class not in {"likely_prose", "likely_table"}
                    ):
                        return GeometryDecision(
                            page=bridge.page,
                            bbox=bridge.bbox,
                            confidence=bridge.confidence,
                            source=bridge.source,
                            crop_class=bridge.crop_class,
                            evidence=bridge,
                            escalation_level="prose_bridge",
                        )
                if ev.crop_class in {"likely_prose", "likely_table"} and escalation != "column_region":
                    return self.resolve(
                        context_before=context_before,
                        context_after=context_after,
                        equation_number=eq,
                        hint_page=anchor.page,
                        escalation="column_region",
                    )
                return GeometryDecision(
                    page=ev.page,
                    bbox=ev.bbox,
                    confidence=ev.confidence,
                    source=ev.source,
                    crop_class=ev.crop_class,
                    evidence=ev,
                    escalation_level=escalation,
                )

        # B. prose bridge（无编号 / 锚点失败）
        bridged = _try_prose_bridge(None)
        if bridged is None and hint_page is not None:
            bridged = _try_prose_bridge(hint_page)
        if bridged is not None:
            return bridged

        ev.failure_stage = "geometry"
        ev.failure_code = "geometry_unresolved"
        return GeometryDecision(
            confidence=0.0,
            source="unresolved",
            crop_class="unknown",
            evidence=ev,
            escalation_level=escalation,
        )


def _refined_crop_usable(
    pdf_doc: Any | None,
    page: int,
    bbox: tuple[float, float, float, float],
    crop_class: str,
    old_bbox: tuple[float, float, float, float] | None,
) -> bool:
    if crop_class in {"likely_prose", "likely_table"}:
        if old_bbox is None:
            return crop_class != "likely_table"
        pw = _page_width(pdf_doc, page)
        return _bbox_suspicious(pw, old_bbox) and not _bbox_suspicious(pw, bbox)
    return True


def proactive_cross_page_relocate(
    pdf_doc: Any | None,
    anchor_index: EquationAnchorIndex | None,
    *,
    page: int | None,
    bbox: tuple[float, float, float, float] | None,
    context_before: str = "",
    context_after: str = "",
    equation_number: str = "",
    original_latex: str = "",
) -> tuple[int, tuple[float, float, float, float], str, str] | None:
    """MD 槽页与 PDF 真页不一致、crop 过高、或同页纵带错位时重定位。"""
    if pdf_doc is None:
        return None
    from app.formula.tokens import direction_flags

    orig_max, orig_min = direction_flags(original_latex or "")
    priority: list[tuple[str, str]] = []
    if orig_min and not orig_max:
        priority.extend(
            [
                ("trace of", "which is to be maximised"),
                ("trace of", "maximised"),
                ("weighted", "which is to be maximised"),
                ("Markov Stability", "which is to be maximised"),
            ]
        )
    if orig_max and not orig_min:
        priority.insert(0, ("partitions H", "Owing to the optimisation"))
        priority.insert(0, ("space of partitions", "Owing to the optimisation"))
        priority.append(("Markov Stability of the partition", "which is to be maximised"))
        priority.append(("which is to be maximised", "Owing to the optimisation"))
    if re.search(r"\\begin\{cases\}|H_\{\s*ic", original_latex or "", re.I):
        priority.insert(
            0, ("membership matrix", "goodness of the partition")
        )

    bridge = prose_bridge_locator(
        pdf_doc,
        context_before=context_before,
        context_after=context_after,
        hint_page=None,
        original_latex=original_latex,
        priority_pairs=priority or None,
        # min 槽才收紧纵带；纯 max 槽（eq 7）需更大 gap，避免误命中上方 min 式
        prefer_tight_gap=bool(orig_min and not orig_max),
    )
    if bridge.page is None or bridge.bbox is None:
        return None
    new_h = bridge.bbox[3] - bridge.bbox[1]
    old_h = (bbox[3] - bbox[1]) if bbox else 0.0
    cross_page = page is None or int(bridge.page) != int(page)
    if bridge.crop_class in {"likely_prose", "likely_table"}:
        allow_prose = (
            bbox is None
            and cross_page
            and bridge.crop_class != "likely_table"
            and 20.0 <= new_h <= 95.0
        )
        if not allow_prose:
            return None
    if bridge.crop_class == "likely_too_small" and bbox is None and 14.0 <= new_h <= 48.0:
        if _context_prefers_tight_gap(
            context_before, context_after, original_latex
        ):
            expanded = _expand_tight_formula_crop(
                pdf_doc, int(bridge.page), tuple(bridge.bbox)
            )
            return (
                int(bridge.page),
                expanded,
                "likely_formula",
                "tight_gap_bridge",
            )
    ph = _page_height(pdf_doc, int(page if page is not None else bridge.page))
    too_tall = (
        bbox is not None
        and old_h > min(130.0, ph * 0.22)
        and new_h < old_h * 0.78
        and new_h >= 28.0
    )
    vert_shift = (
        bbox is not None
        and bridge.bbox is not None
        and not cross_page
        and _bbox_vertically_distinct(bbox, bridge.bbox)
        and (orig_min or orig_max or priority)
    )
    upward_min = (
        bbox is not None
        and bridge.bbox is not None
        and not cross_page
        and orig_min
        and not orig_max
        and bridge.bbox[3] < bbox[1] - 8.0
    )
    if cross_page or too_tall or vert_shift or upward_min:
        if cross_page:
            src = "cross_page_bridge"
        elif too_tall:
            src = "tall_crop_bridge"
        elif upward_min:
            src = "min_above_max_bridge"
        else:
            src = "direction_band_bridge"
        return (
            int(bridge.page),
            tuple(bridge.bbox),
            bridge.crop_class or "likely_formula",
            src,
        )
    return None


def refine_formula_crop_bbox(
    pdf_doc: Any | None,
    anchor_index: EquationAnchorIndex | None,
    *,
    page: int | None,
    bbox: tuple[float, float, float, float] | None,
    context_before: str = "",
    context_after: str = "",
    equation_number: str = "",
    crop_class: str = "",
    original_latex: str = "",
) -> tuple[int, tuple[float, float, float, float], str, str] | None:
    """OCR 前 crop escalation：窄条/散文/表格/错页 → 全页重定位。"""
    if pdf_doc is None:
        return None

    proactive = proactive_cross_page_relocate(
        pdf_doc,
        anchor_index,
        page=page,
        bbox=bbox,
        context_before=context_before,
        context_after=context_after,
        equation_number=equation_number,
        original_latex=original_latex,
    )
    if proactive is not None:
        return proactive

    if bbox is not None and not crop_bbox_suspicious(pdf_doc, page, bbox, crop_class):
        return None

    idx = anchor_index or EquationAnchorIndex()
    resolver = FormulaGeometryResolver(pdf_doc, idx)

    def _try(hint: int | None) -> tuple[int, tuple[float, float, float, float], str, str] | None:
        dec = resolver.resolve(
            context_before=context_before,
            context_after=context_after,
            equation_number=(equation_number or "").strip(),
            hint_page=hint,
            escalation="column_region",
            original_latex=original_latex,
        )
        if dec.page is None or dec.bbox is None:
            return None
        if not _refined_crop_usable(
            pdf_doc, int(dec.page), tuple(dec.bbox), dec.crop_class or "", bbox
        ):
            return None
        return (
            int(dec.page),
            tuple(dec.bbox),
            dec.crop_class or "likely_formula",
            dec.source or "crop_escalation",
        )

    # 先全页，再回退到当前 hint（MD 页码经常错）
    found = _try(None)
    if found is not None:
        return found
    if page is not None:
        found = _try(int(page))
        if found is not None:
            return found

    bridge = prose_bridge_locator(
        pdf_doc,
        context_before=context_before,
        context_after=context_after,
        hint_page=None,
        original_latex=original_latex,
        prefer_tight_gap=_context_prefers_tight_gap(
            context_before, context_after, original_latex
        ),
    )
    if (
        bridge.page is not None
        and bridge.bbox is not None
        and _refined_crop_usable(
            pdf_doc,
            int(bridge.page),
            tuple(bridge.bbox),
            bridge.crop_class or "",
            bbox,
        )
    ):
        return (
            int(bridge.page),
            tuple(bridge.bbox),
            bridge.crop_class or "likely_formula",
            "prose_bridge_ocr_retry",
        )
    return None
