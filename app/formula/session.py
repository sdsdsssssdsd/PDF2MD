"""Document-scope PDF 复用 + EquationAnchorIndex（整篇只开一次、只扫一次）。"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.formula.config import FormulaConfig, RecoveryBudget
from app.formula.types import FormulaTelemetry

# 延迟导入避免循环；geometry 使用 session 中的 column_bounds 等


@dataclass
class BudgetTracker:
    budget: RecoveryBudget
    doc_ocr_calls: int = 0
    doc_seconds: float = 0.0

    def allow_ocr(self, formula_calls: int, formula_seconds: float = 0.0) -> bool:
        b = self.budget
        if b.max_ocr_calls_per_formula <= 0:
            return False
        if formula_calls >= b.max_ocr_calls_per_formula:
            return False
        if b.max_ocr_calls_per_document > 0 and self.doc_ocr_calls >= b.max_ocr_calls_per_document:
            return False
        if b.max_recovery_seconds_per_formula > 0 and formula_seconds >= b.max_recovery_seconds_per_formula:
            return False
        if b.max_recovery_seconds_per_document > 0 and self.doc_seconds >= b.max_recovery_seconds_per_document:
            return False
        return True

    def record_ocr(self, seconds: float) -> None:
        self.doc_ocr_calls += 1
        self.doc_seconds += max(0.0, seconds)


@dataclass(frozen=True)
class EquationAnchor:
    page: int
    bbox: tuple[float, float, float, float]  # number token box
    x_ratio: float


class EquationAnchorIndex:
    """一次扫描 PDF 中的 (n)，之后 O(1) 查 Eq. (4)。"""

    def __init__(self) -> None:
        self.by_number: dict[str, list[EquationAnchor]] = {}

    def add(self, number: str, anchor: EquationAnchor) -> None:
        self.by_number.setdefault(str(number), []).append(anchor)

    def lookup(
        self, number: str, page: int | None = None
    ) -> EquationAnchor | None:
        hits = list(self.by_number.get(str(number)) or [])
        if page is not None:
            page_hits = [h for h in hits if h.page == int(page)]
            if page_hits:
                hits = page_hits
        if not hits:
            return None
        # 同页多个 (n) 时优先栏外展示编号（右缘），避免正文行内 (1)
        try:
            pw = 612.0
            if hits:
                pw = max(400.0, hits[0].bbox[2] / max(0.01, hits[0].x_ratio))
            margin_hits = [
                h
                for h in hits
                if is_display_equation_number(pw, h.bbox[0], h.bbox[2])
            ]
            if margin_hits:
                hits = margin_hits
        except Exception:
            pass
        # 阅读序：先页码再 y；同位置再取更靠右（栏右公式号）
        hits.sort(key=lambda a: (a.page, a.bbox[1], -a.x_ratio))
        return hits[0]

    def numbers_on_page(self, page: int) -> list[str]:
        out: list[str] = []
        for n, hits in self.by_number.items():
            if any(h.page == int(page) for h in hits):
                out.append(n)
        return sorted(out, key=lambda x: int(x) if x.isdigit() else x)

    def all_numbers(self) -> list[str]:
        return sorted(self.by_number.keys(), key=lambda x: int(x) if x.isdigit() else x)


_EQ_TOKEN = re.compile(
    r"^\(\s*([A-Za-z]?\d+(?:\.\d+)?[A-Za-z]?|[A-Za-z]\.\d+|[Ss]\d+)\s*\)$"
)


_INLINE_EQ_PREFIX = re.compile(r"^(eq|eqs|equation|equations)\.?$", re.I)


def is_display_equation_number(page_w: float, x0: float, x1: float) -> bool:
    """展示公式编号：栏外右对齐 (n)，排除正文行内引用（如 similarity (1)）。"""
    mid = page_w * 0.5
    tw = max(1.0, x1 - x0)
    if tw > page_w * 0.12:
        return False
    right_col = x0 >= mid - 12.0
    if right_col:
        return x0 >= page_w * 0.70
    return x1 >= mid - page_w * 0.04


def _is_inline_eq_reference(words: list, num_word: tuple) -> bool:
    """同行左侧紧邻 Eq./Equation → 正文引用，不是展示公式编号。"""
    nx0, ny0, nx1, ny1 = num_word[0], num_word[1], num_word[2], num_word[3]
    cy = (ny0 + ny1) * 0.5
    left: list[tuple] = []
    for w in words:
        if len(w) < 5:
            continue
        wy = (w[1] + w[3]) * 0.5
        if abs(wy - cy) > 5.0:
            continue
        if w[2] <= nx0 + 1.0:
            left.append(w)
    left.sort(key=lambda w: w[0])
    for w in left[-3:]:
        tok = str(w[4]).strip()
        if _INLINE_EQ_PREFIX.match(tok):
            return True
        # 「Eq.(4)」粘连或带冒号的引用
        if re.match(r"^eq\.?\s*\(?\d", tok, re.I):
            return True
    return False


def build_equation_anchor_index(doc: Any) -> EquationAnchorIndex:
    """索引展示公式编号 (n)（含左栏）；排除正文 Eq.(n) 引用。"""
    index = EquationAnchorIndex()
    if doc is None:
        return index
    t0 = time.perf_counter()
    try:
        for page_index in range(len(doc)):
            page = doc[page_index]
            page_w = float(page.rect.width)
            words = page.get_text("words") or []
            for w in words:
                if len(w) < 5:
                    continue
                x0, y0, x1, y1, token = w[0], w[1], w[2], w[3], str(w[4])
                m = _EQ_TOKEN.match(token.strip())
                if not m:
                    continue
                if _is_inline_eq_reference(words, w):
                    continue
                if not is_display_equation_number(page_w, float(x0), float(x1)):
                    continue
                n = m.group(1)
                index.add(
                    n,
                    EquationAnchor(
                        page=page_index,
                        bbox=(float(x0), float(y0), float(x1), float(y1)),
                        x_ratio=float(x0) / max(1.0, page_w),
                    ),
                )
    except Exception:
        pass
    index.build_seconds = time.perf_counter() - t0  # type: ignore[attr-defined]
    return index

def column_bounds(
    page_w: float,
    number_x0: float,
    number_x1: float,
    *,
    margin: float = 36.0,
) -> tuple[float, float]:
    """按编号所在栏给出公式裁切左右边界，避免双栏串台。"""
    mid = page_w * 0.5
    # 编号在右半页 → 右栏公式（O-018 实测）
    if number_x0 >= mid - 12.0:
        x0 = max(margin, mid - 8.0)
        x1 = min(page_w - 8.0, max(number_x1 + 6.0, page_w * 0.98))
        return x0, x1
    # 左半页 → 左栏
    x0 = max(8.0, margin * 0.5)
    x1 = min(mid + 8.0, number_x1 + 10.0)
    return x0, x1


def formula_band_from_number(
    page_w: float,
    page_h: float,
    number_bbox: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    """由公式编号框推出公式裁切框：同栏 + 紧贴编号的横条（避免吃到上下正文）。"""
    nx0, ny0, nx1, ny1 = number_bbox
    nh = max(8.0, ny1 - ny0)
    # 展示公式与编号同基线；宁可略矮也不要吃上下散文行
    band = max(28.0, min(48.0, nh * 3.2))
    cy = (ny0 + ny1) * 0.5
    y0 = max(0.0, cy - band * 0.45)
    y1 = min(page_h, cy + band * 0.55)
    x0, x1 = column_bounds(page_w, nx0, nx1)
    return (x0, y0, x1, y1)
class FormulaRecoverySession:
    """整篇文档共享：pymupdf.Document、锚点索引、OCR 预算、telemetry。"""

    def __init__(
        self,
        pdf_path: str | Path | None,
        config: FormulaConfig | None = None,
    ) -> None:
        self.config = config or FormulaConfig()
        self.pdf_path = Path(pdf_path) if pdf_path else None
        self.pdf_doc: Any = None
        self.anchor_index = EquationAnchorIndex()
        self.tracker = BudgetTracker(self.config.budget)
        self.telemetry = FormulaTelemetry()
        self._opened = False

    def __enter__(self) -> FormulaRecoverySession:
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def open(self) -> None:
        if self._opened:
            return
        self._opened = True
        if self.pdf_path is None or not self.pdf_path.exists():
            return
        try:
            import pymupdf
        except Exception:
            return
        t0 = time.perf_counter()
        try:
            self.pdf_doc = pymupdf.open(self.pdf_path)
            t_bbox = time.perf_counter()
            self.anchor_index = build_equation_anchor_index(self.pdf_doc)
            self.telemetry.bbox_seconds += time.perf_counter() - t_bbox
        except Exception:
            self.pdf_doc = None
        self.telemetry.total_seconds += time.perf_counter() - t0

    def close(self) -> None:
        doc = self.pdf_doc
        self.pdf_doc = None
        if doc is not None:
            try:
                doc.close()
            except Exception:
                pass

    def formula_bbox_from_eq(
        self, number: str, page: int | None = None, *, use_v2: bool = True
    ) -> tuple[int, tuple[float, float, float, float]] | None:
        anchor = self.anchor_index.lookup(number, page=page)
        if anchor is None:
            return None
        if self.pdf_doc is None:
            if use_v2:
                from app.formula.geometry import formula_bbox_from_anchor_v2

                return anchor.page, formula_bbox_from_anchor_v2(
                    612.0, 792.0, anchor, self.anchor_index
                )
            return anchor.page, formula_band_from_number(612.0, 792.0, anchor.bbox)
        try:
            page_obj = self.pdf_doc[anchor.page]
        except Exception:
            if use_v2:
                from app.formula.geometry import formula_bbox_from_anchor_v2

                return anchor.page, formula_bbox_from_anchor_v2(
                    612.0, 792.0, anchor, self.anchor_index
                )
            return anchor.page, formula_band_from_number(612.0, 792.0, anchor.bbox)
        page_w = float(page_obj.rect.width)
        page_h = float(page_obj.rect.height)
        if use_v2:
            from app.formula.geometry import formula_bbox_from_anchor_v2, _page_text_blocks

            blocks = _page_text_blocks(page_obj)
            return anchor.page, formula_bbox_from_anchor_v2(
                page_w,
                page_h,
                anchor,
                self.anchor_index,
                page_blocks=blocks,
            )
        return anchor.page, formula_band_from_number(page_w, page_h, anchor.bbox)
