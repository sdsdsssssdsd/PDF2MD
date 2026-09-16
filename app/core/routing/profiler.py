"""轻量 DocumentProfiler：给 Hybrid Router 用，不改变解析算法本身。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PageProfile:
    """单页信号。给 Hybrid Router 做局部 capability，不决定整篇 parser。"""

    number: int
    text_chars: int = 0
    scan_like: bool = False
    formula_like: bool = False
    table_like: bool = False
    multi_column: bool = False
    image_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "text_chars": self.text_chars,
            "scan_like": self.scan_like,
            "formula_like": self.formula_like,
            "table_like": self.table_like,
            "multi_column": self.multi_column,
            "image_count": self.image_count,
        }


@dataclass
class DocumentProfile:
    page_count: int = 0
    text_layer_ratio: float = 0.0
    scan_ratio: float = 0.0
    formula_density: float = 0.0
    table_density: float = 0.0
    multi_column_ratio: float = 0.0
    image_density: float = 0.0
    language: str = "unknown"
    layout_complexity: float = 0.0
    notes: list[str] = field(default_factory=list)
    page_profiles: list[PageProfile] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_count": self.page_count,
            "text_layer_ratio": round(self.text_layer_ratio, 4),
            "scan_ratio": round(self.scan_ratio, 4),
            "formula_density": round(self.formula_density, 4),
            "table_density": round(self.table_density, 4),
            "multi_column_ratio": round(self.multi_column_ratio, 4),
            "image_density": round(self.image_density, 4),
            "language": self.language,
            "layout_complexity": round(self.layout_complexity, 4),
            "notes": list(self.notes),
            "page_profiles": [p.to_dict() for p in self.page_profiles],
        }


def profile_source(path: Path | str) -> DocumentProfile:
    pdf = Path(path)
    if not pdf.is_file():
        return DocumentProfile(notes=["missing_file"])
    if pdf.suffix.lower() != ".pdf":
        return DocumentProfile(notes=["not_pdf"])
    return profile_pdf(pdf)


def profile_pdf(path: Path) -> DocumentProfile:
    backend = _open_pdf(path)
    if backend is None:
        return DocumentProfile(notes=["no_pdf_backend"])
    doc, closer = backend
    try:
        n = len(doc)
        if n <= 0:
            return DocumentProfile(notes=["empty_pdf"])
        pages = [_profile_one_page(doc[i], i + 1) for i in range(n)]
        text_pages = sum(1 for p in pages if p.text_chars >= 40)
        image_hits = sum(p.image_count for p in pages)
        math_hits = sum(1 for p in pages if p.formula_like)
        table_hits = sum(1 for p in pages if p.table_like)
        multi_col = sum(1 for p in pages if p.multi_column)
        text_ratio = text_pages / n
        return DocumentProfile(
            page_count=n,
            text_layer_ratio=text_ratio,
            scan_ratio=max(0.0, 1.0 - text_ratio),
            formula_density=math_hits / n,
            table_density=table_hits / n,
            multi_column_ratio=multi_col / n,
            image_density=min(1.0, image_hits / max(1, n * 2)),
            language=_guess_language(doc),
            layout_complexity=min(
                1.0,
                0.4 * (multi_col / n) + 0.3 * (table_hits / n) + 0.3 * min(1.0, image_hits / max(1, n)),
            ),
            page_profiles=pages,
        )
    finally:
        closer()


def _profile_one_page(page, number: int) -> PageProfile:
    text = ""
    try:
        text = page.get_text("text") or ""
    except Exception:
        text = ""
    compact = text.replace(" ", "")
    image_count = 0
    try:
        image_count = len(page.get_images(full=True) or [])
    except Exception:
        image_count = 0
    chars = len(text.strip())
    return PageProfile(
        number=number,
        text_chars=chars,
        scan_like=chars < 40,
        formula_like=any(tok in compact for tok in ("\\frac", "\\sum", "\\int", "∑", "∫", "≤", "≥")),
        table_like=_looks_table(text),
        multi_column=_looks_multicolumn(page),
        image_count=image_count,
    )


def _open_pdf(path: Path):
    try:
        import pymupdf

        doc = pymupdf.open(str(path))
        return doc, doc.close
    except Exception:
        try:
            import fitz as pymupdf  # type: ignore

            doc = pymupdf.open(str(path))
            return doc, doc.close
        except Exception:
            return None


def _looks_multicolumn(page) -> bool:
    try:
        blocks = page.get_text("blocks") or []
    except Exception:
        return False
    xs = []
    for b in blocks:
        if len(b) < 5:
            continue
        x0, _y0, x1, _y1 = b[0], b[1], b[2], b[3]
        if (x1 - x0) < 40:
            continue
        xs.append((x0, x1))
    if len(xs) < 6:
        return False
    width = float(getattr(page.rect, "width", 0) or 0)
    if width <= 0:
        return False
    left = sum(1 for x0, x1 in xs if x1 < width * 0.55)
    right = sum(1 for x0, x1 in xs if x0 > width * 0.45)
    return left >= 3 and right >= 3


def _looks_table(text: str) -> bool:
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    if len(lines) < 4:
        return False
    spaced = sum(1 for ln in lines if ln.count("  ") >= 3 or ln.count("\t") >= 2)
    return spaced >= 3


def _guess_language(doc) -> str:
    sample = ""
    try:
        limit = min(len(doc), 3)
        for i in range(limit):
            sample += doc[i].get_text("text") or ""
    except Exception:
        return "unknown"
    if not sample.strip():
        return "unknown"
    cjk = sum(1 for ch in sample if "\u4e00" <= ch <= "\u9fff")
    if cjk >= 20:
        return "zh"
    return "en"
