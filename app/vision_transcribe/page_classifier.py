"""页面类型分类（Phase 1）。"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.vision_transcribe.capture.page_split import PageSlice, split_pages
from app.vision_transcribe.models import PageAnalysis, VisionQualityReport
from app.vision_transcribe.vision_structure_repair import markdown_lacks_structure


@dataclass(frozen=True)
class PageType:
    name: str
    min_chars: int
    risk: str = "low"
    need_format_fix: bool = False


EMPTY_PAGE = PageType("empty", 1, risk="high")
TEXT_PAGE = PageType("text", 100)
TEXT_SHORT_PAGE = PageType("text_short", 100, risk="high", need_format_fix=True)
IMAGE_PAGE = PageType("image", 20, need_format_fix=True)
IMAGE_TEXT_PAGE = PageType("image_text", 100, need_format_fix=True)
TITLE_PAGE = PageType("title", 5, need_format_fix=True)
SCREENSHOT_PAGE = PageType("screenshot", 20, need_format_fix=True)
TABLE_PAGE = PageType("table", 80, need_format_fix=True)
REFERENCE_PAGE = PageType("reference", 120)
BOILERPLATE_PAGE = PageType("boilerplate", 80)

_FIGURE_MARKER_RE = re.compile(r"<!--\s*PDF2MD:FIGURE:", re.I)
_FIGURE_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
_TABLE_ROW_RE = re.compile(r"(?m)^\|[^\n]+\|")
_REFERENCE_RE = re.compile(r"(?m)^\[\d{1,3}\]|\(\d{4}\)[\.,]", re.I)
_GUI_ACTION_RE = re.compile(
    r"\b(?:Click|Enter|Select|Save|Cancel|Continue|Help|Navigate|Press|Confirm|Exit)\b",
    re.I,
)
_SAP_GUI_RE = re.compile(
    r"\b(?:SAP|Company Code|Sales Org|Sales District|Distr[.]? Channel|"
    r"Division|Customer|Vendor|Business Partner|Purchase Order|Pricing|"
    r"Delivery|Shipping|Billing|Incoterms|Condition type|Material)\b",
    re.I,
)
_GUI_GLYPH_RE = re.compile(r"[▶☐☑☒]|(?:^\s*[<>]\s*$)", re.M)


def _is_figure_page(text: str) -> bool:
    return bool(
        _FIGURE_MARKER_RE.search(text)
        or _FIGURE_IMAGE_RE.search(text)
        or re.search(r"(?m)^\s*\*{0,2}\s*(?:Figure|Fig\.?)\s*\d+", text, re.I)
    )


def _is_screenshot_page(text: str) -> bool:
    if _GUI_GLYPH_RE.search(text):
        return True
    if _SAP_GUI_RE.search(text):
        return True
    return bool(
        _GUI_ACTION_RE.search(text)
        and len(text) < 500
    )


def _looks_like_title(text: str) -> bool:
    t = text.strip()
    if not t or len(t) > 80 or t.endswith("."):
        return False
    if t.isupper() or re.match(r"^[A-Z0-9][A-Za-z0-9 ,&/'-]{2,}$", t):
        return True
    return bool(re.search(r"\b(?:Case Study|Figure|Table|Chapter)\b", t, re.I))


def classify_page(text: str) -> PageType:
    t = (text or "").strip()
    if not t:
        return EMPTY_PAGE
    chars = len(t)
    if _is_figure_page(t):
        return IMAGE_TEXT_PAGE if chars >= 100 else IMAGE_PAGE
    if len(_TABLE_ROW_RE.findall(t)) >= 4:
        return TABLE_PAGE
    if _REFERENCE_RE.search(t):
        return REFERENCE_PAGE
    if "Published in partnership" in t or re.search(
        r"npj Science of Learning|www\.nature\.com/scientificreports", t, re.I
    ):
        return BOILERPLATE_PAGE
    if _is_screenshot_page(t):
        return SCREENSHOT_PAGE
    if chars < 100:
        return TITLE_PAGE if _looks_like_title(t) else TEXT_SHORT_PAGE
    return TEXT_PAGE


def _image_ratio(body: str) -> float:
    t = body or ""
    lines = [line for line in t.splitlines() if line.strip()]
    if not lines:
        return 0.0
    image_lines = sum(
        1
        for line in lines
        if _FIGURE_MARKER_RE.search(line) or _FIGURE_IMAGE_RE.search(line)
    )
    return image_lines / len(lines)


def page_analysis(page: int, body: str, slice_: PageSlice | None = None) -> PageAnalysis:
    ptype = classify_page(body)
    chars = slice_.chars if slice_ is not None else len((body or "").strip())
    needs_fix = ptype.need_format_fix or bool(body and markdown_lacks_structure(body))
    risk = ptype.risk
    if not body:
        risk = "high"
    return PageAnalysis(
        page=page,
        page_type=ptype.name,
        chars=chars,
        image_ratio=_image_ratio(body),
        need_format_fix=needs_fix,
        risk=risk,
    )


def analyze_batch_pages(
    md: str,
    *,
    start_page: int,
    end_page: int,
) -> VisionQualityReport:
    slices = split_pages(md)
    analyses: list[PageAnalysis] = []
    for p in range(start_page, end_page + 1):
        sl = slices.get(p)
        body = sl.body if sl else ""
        analyses.append(page_analysis(p, body, sl))

    high = [a for a in analyses if a.risk == "high"]
    score = max(0.0, 100.0 - len(high) * 15.0)
    report = VisionQualityReport(pages=analyses, score=score)
    report.warnings = [
        f"PAGE {a.page:04d} low text density classification:{a.page_type} "
        "action:FORMAT_NORMALIZE"
        for a in analyses
        if a.risk == "low" and a.chars < 100
    ]
    report.errors = [
        f"PAGE {a.page:04d} empty or high-risk classification:{a.page_type}"
        for a in high
    ]
    return report

