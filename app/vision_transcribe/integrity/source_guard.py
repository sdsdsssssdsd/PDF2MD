"""PDF 文本层 Source Guard（仅校验，不作输出来源）。"""
from __future__ import annotations

import json
import re
from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz  # type: ignore

from app.vision_transcribe.manifest import vision_dir

_GUARD_MIN_TEXT = 80
_MAX_ANCHORS = 48

# 高置信度：实验数值、表图编号、公式号（页眉页脚 DOI/年份/引用号不在此列）
_STRONG_NUMERIC = re.compile(
    r"(?:"
    r"\b0\.\d{2,}\b|"  # 0.913
    r"\b[1-9]\d*\.\d+\b|"  # 3.7, 64.5（排除 0.48 类页眉碎片时仍保留 ≥1）
    r"\b\d+\.\d+%\b|"
    r"\bN\s*=\s*[\d,]+\b|"
    r"(?:Eq\.|Equation)\s*\(?\d+\)?|"
    r"(?:Table|Fig\.|Figure)\s+\d+"
    r")",
    re.I,
)
_WORD_ANCHOR = re.compile(r"\b[A-Za-z][A-Za-z0-9\-]{5,}\b")
_STOP = frozenset(
    {
        "which", "their", "these", "those", "where", "while",
        "would", "could", "should", "about", "after", "before",
        "between", "through", "during", "under", "over", "such",
        "than", "that", "this", "with", "from", "have", "been",
        "were", "will", "also", "into", "more", "most", "some",
        "other", "using", "used", "based", "paper", "figure",
        "table", "section", "abstract", "introduction", "results",
        "method", "methods", "pages", "volume", "series", "press",
        "university", "conference", "proceedings", "copyright",
        "permission", "reproduced", "published", "springer",
    }
)
_JUNK_ANCHOR = re.compile(
    r"(?:"
    r"^\d{7}\.\d{7}$|"  # ACM 论文 ID
    r"^\d{4}$|"  # 单独年份
    r"^\[\d{1,3}\]$|"  # 单独引用号（跨页不可靠）
    r"^10\.\d+.*$|"  # DOI 片段
    r"^\d{1,4}$"  # 页码/会议号碎片
    r")",
    re.I,
)


def source_guard_dir(output_dir: Path) -> Path:
    return vision_dir(output_dir) / "source_guard"


def _is_junk_anchor(tok: str) -> bool:
    t = (tok or "").strip()
    if not t or len(t) < 3:
        return True
    if _JUNK_ANCHOR.match(t):
        return True
    if re.fullmatch(r"\d{7}\.\d{7}", t):
        return True
    return False


def extract_anchors(text: str) -> list[str]:
    """只抽取高置信度锚点，避免页眉 DOI/年份/引用号误报。"""
    t = re.sub(r"\s+", " ", (text or "").strip())
    if len(t) < _GUARD_MIN_TEXT:
        return []
    anchors: list[str] = []
    seen: set[str] = set()

    for m in _STRONG_NUMERIC.finditer(t):
        tok = m.group(0).strip()
        if _is_junk_anchor(tok):
            continue
        key = tok.lower()
        if key in seen:
            continue
        seen.add(key)
        anchors.append(tok)

    for m in _WORD_ANCHOR.finditer(t):
        tok = m.group(0).strip()
        key = tok.lower()
        if key in seen or key in _STOP or _is_junk_anchor(tok):
            continue
        if not re.search(r"[A-Za-z]{3,}", tok):
            continue
        seen.add(key)
        anchors.append(tok)
        if len(anchors) >= _MAX_ANCHORS:
            break

    return anchors


def build_page_guard(pdf_path: Path, page_no: int) -> dict | None:
    doc = fitz.open(str(pdf_path))
    try:
        if page_no < 1 or page_no > doc.page_count:
            return None
        raw = doc.load_page(page_no - 1).get_text("text") or ""
        raw = raw.strip()
        if len(raw) < _GUARD_MIN_TEXT:
            return None
        anchors = extract_anchors(raw)
        if len(anchors) < 4:
            return None
        numeric = [a for a in anchors if _STRONG_NUMERIC.search(a)]
        if len(numeric) < 2:
            return None
        return {
            "page": page_no,
            "enabled": True,
            "text_chars": len(raw),
            "anchors": anchors,
            "numeric_anchors": numeric[:16],
        }
    finally:
        doc.close()


def build_all_source_guards(pdf_path: Path, output_dir: Path) -> int:
    out_dir = source_guard_dir(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(str(pdf_path))
    try:
        n = 0
        for i in range(doc.page_count):
            page_no = i + 1
            guard = build_page_guard(pdf_path, page_no)
            path = out_dir / f"page_{page_no:04d}.json"
            if guard is None:
                if path.is_file():
                    path.unlink()
                continue
            path.write_text(
                json.dumps(guard, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            n += 1
        return n
    finally:
        doc.close()


def load_page_guard(output_dir: Path, page_no: int) -> dict | None:
    path = source_guard_dir(output_dir) / f"page_{page_no:04d}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if data.get("enabled") else None
    except (OSError, json.JSONDecodeError):
        return None


def _anchor_in_text(anchor: str, vision: str) -> bool:
    if not anchor or not vision:
        return False
    if anchor in vision:
        return True
    a = anchor.lower()
    v = vision.lower()
    if a in v:
        return True
    if re.search(r"\d", anchor):
        a2 = re.sub(r"[,\s]", "", a)
        v2 = re.sub(r"[,\s]", "", v)
        if a2 and a2 in v2:
            return True
    return False


def check_page_anchors(page_no: int, vision_text: str, guard: dict) -> list[str]:
    """返回缺失的高置信度锚点（空 = 通过）。仅 numeric 强锚点参与否决。"""
    if not guard or not guard.get("enabled"):
        return []
    numeric: list[str] = list(guard.get("numeric_anchors") or [])
    if len(numeric) < 2:
        return []

    missing = [a for a in numeric if not _anchor_in_text(a, vision_text)]
    # 极严格：≥3 个强数值锚点同时缺失才报（避免重跑循环）
    if len(missing) >= 3 and len(missing) >= len(numeric) // 2:
        return missing[:8]
    return []
