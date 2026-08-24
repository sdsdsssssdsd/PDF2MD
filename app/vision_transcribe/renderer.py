"""PDF → bookfigures（PyMuPDF 本地渲染）。"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz  # type: ignore

from app.vision_transcribe.models import PageInfo, page_png_name
from app.vision_transcribe.page_labeler import add_page_label


ProgressCb = Callable[[int, int], None] | None


def render_pdf_to_bookfigures(
    pdf_path: Path,
    bookfigures_dir: Path,
    *,
    scale: float = 3.0,
    banner_px: int = 48,
    force: bool = False,
    progress: ProgressCb = None,
    cancelled: Callable[[], bool] | None = None,
) -> list[PageInfo]:
    """渲染全部页面为 page_XXXX.png，并加页码横幅。幂等：已有非空文件可跳过。"""
    bookfigures_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(str(pdf_path))
    try:
        n = doc.page_count
        pages: list[PageInfo] = []
        mat = fitz.Matrix(scale, scale)
        for i in range(n):
            if cancelled and cancelled():
                raise RuntimeError("cancelled")
            page_no = i + 1
            name = page_png_name(page_no)
            out = bookfigures_dir / name
            rel = f"bookfigures/{name}"
            if force or not out.exists() or out.stat().st_size == 0:
                pix = doc.load_page(i).get_pixmap(matrix=mat, alpha=False)
                pix.save(str(out))
                add_page_label(out, page_no, banner_px=banner_px, inplace=True)
            pages.append(PageInfo(page=page_no, file=rel))
            if progress:
                progress(page_no, n)
        return pages
    finally:
        doc.close()


def page_count(pdf_path: Path) -> int:
    doc = fitz.open(str(pdf_path))
    try:
        return int(doc.page_count)
    finally:
        doc.close()
