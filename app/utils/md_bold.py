"""从 PDF 还原粗体短语。从 md_postprocess 拆出。"""
from __future__ import annotations

import re
from pathlib import Path

from app.utils.md_inline_math import _PROTECT

def extract_bold_phrases(
    pdf_path: Path, *, min_len: int = 3, max_len: int = 60
) -> list[str]:
    """用 PyMuPDF 从 PDF 提取粗体短语。"""
    try:
        import pymupdf
    except Exception:
        return []

    phrases: dict[str, int] = {}
    try:
        doc = pymupdf.open(pdf_path)
    except Exception:
        return []

    try:
        for page in doc:
            for block in page.get_text("dict").get("blocks", []):
                for line in block.get("lines", []):
                    bold_bits: list[str] = []
                    for span in line.get("spans", []):
                        raw = (span.get("text") or "").replace("\xa0", " ")
                        font = (span.get("font") or "").lower()
                        flags = int(span.get("flags") or 0)
                        is_bold = bool(flags & 2**4) or any(
                            k in font
                            for k in (
                                "bold",
                                "black",
                                "heavy",
                                "semibold",
                                "demibold",
                                "-bd",
                                "cmbx",
                                "cmbxti",
                            )
                        )
                        if is_bold and raw:
                            bold_bits.append(raw)
                        elif bold_bits:
                            phrase = re.sub(r"\s+", " ", "".join(bold_bits)).strip()
                            if min_len <= len(phrase) <= max_len:
                                phrases[phrase] = phrases.get(phrase, 0) + 1
                            bold_bits = []
                    if bold_bits:
                        phrase = re.sub(r"\s+", " ", "".join(bold_bits)).strip()
                        if min_len <= len(phrase) <= max_len:
                            phrases[phrase] = phrases.get(phrase, 0) + 1
    finally:
        doc.close()

    stop = {
        "abstract",
        "introduction",
        "references",
        "appendix",
        "acknowledgements",
        "acknowledgment",
        "day",
        "days",
        "fig",
        "figure",
        "table",
        "section",
        "eq",
        "equation",
        "and",
        "or",
        "the",
        "of",
        "to",
        "in",
        "on",
        "for",
        "with",
    }
    items = []
    for p in phrases:
        pl = p.lower().strip(" .:;,")
        if pl in stop:
            continue
        if p.startswith("http"):
            continue
        if re.fullmatch(r"[\d\W]+", p):
            continue
        # 过短且无字母数字混合的短语跳过（减少 **Day** 这类碎片）
        if len(p) < 4 and not re.search(r"[A-Za-z].*[0-9]|[0-9].*[A-Za-z]", p):
            if " " not in p:
                continue
        items.append(p)
    items.sort(key=len, reverse=True)
    return items


def apply_bold_phrases(md: str, phrases: list[str]) -> str:
    if not phrases:
        return md

    # 整篇统一计数，避免按段落重置导致 LEAP 被加粗几十次
    counters: dict[str, int] = {p: 0 for p in phrases}
    parts: list[str] = []
    last = 0
    for m in _PROTECT.finditer(md):
        parts.append(
            _bold_plain(md[last : m.start()], phrases, counters=counters)
        )
        parts.append(m.group(0))
        last = m.end()
    parts.append(_bold_plain(md[last:], phrases, counters=counters))
    return "".join(parts)


def _bold_plain(
    text: str,
    phrases: list[str],
    *,
    counters: dict[str, int],
) -> str:
    out = text
    for phrase in phrases:
        if len(phrase) < 2 or phrase not in out:
            continue
        limit = 2
        if " " not in phrase and phrase.isupper() and len(phrase) <= 6:
            limit = 1
        pat = re.compile(re.escape(phrase))

        def wrap(m: re.Match[str], _phrase=phrase, _limit=limit) -> str:
            if counters.get(_phrase, 0) >= _limit:
                return m.group(0)
            s, e = m.start(), m.end()
            left = m.string[max(0, s - 2) : s]
            right = m.string[e : e + 2]
            if left.endswith("**") or right.startswith("**"):
                return m.group(0)
            if s > 0 and m.string[s - 1].isalnum():
                return m.group(0)
            if e < len(m.string) and m.string[e].isalnum():
                return m.group(0)
            line_start = m.string.rfind("\n", 0, s) + 1
            if m.string[line_start : line_start + 1] == "#":
                return m.group(0)
            counters[_phrase] = counters.get(_phrase, 0) + 1
            return f"**{m.group(0)}**"

        out = pat.sub(wrap, out)
    return out

