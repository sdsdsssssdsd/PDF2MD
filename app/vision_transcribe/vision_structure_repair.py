"""高保真 Markdown 结构修复：换行、章节标题、DeepSeek 占位图 URL。"""
from __future__ import annotations

import re

from app.vision_transcribe.models import FIGURE_MARKER_RE, PAGE_MARKER_RE

_PAGE_BREAK = re.compile(r"(<!--\s*PDF2MD:PAGE:(\d{4})\s*-->)")
# DeepSeek 幻觉图：fig1 / figure1 / figure_1 等
_EXAMPLE_FIG_URL = re.compile(
    r"https?://example\.com/(?:fig(?:ure)?[_-]?)(\d+)\.(?:png|jpg|jpeg|gif|webp)",
    re.I,
)
_EXAMPLE_FIG_MD = re.compile(
    r"!\[[^\]]*\]\(\s*https?://example\.com/(?:fig(?:ure)?[_-]?)(\d+)\.[^)]+\)",
    re.I,
)

_TOP_SECTIONS = (
    "Introduction",
    "Related work",
    "Methods",
    "Results",
    "Discussion",
    "Conclusion",
    "References",
)

_SUBSECTION = re.compile(
    r"(?:^|\n)(?P<num>\d+\.\d+)\s{2,}(?P<title>[A-Z][^\n]{4,90}?)"
    r"(?=[A-Z][a-z])",
    re.M,
)
_TOP_SECTION = re.compile(
    r"(?:^|\n)(?P<num>[1-6])\s{2,}(?P<title>"
    + "|".join(re.escape(s) for s in _TOP_SECTIONS)
    + r")(?=[A-Z])",
    re.M,
)


def repair_page_marker_breaks(md: str) -> str:
    if not md:
        return md
    text = _PAGE_BREAK.sub(r"\1\n\n", md)
    return text


def repair_section_line_breaks(md: str) -> str:
    """扁平文本中在「1  Introduction」等章节号前强制断行。"""
    if not md:
        return md
    text = md
    tops = "|".join(re.escape(s) for s in _TOP_SECTIONS)
    text = re.sub(
        rf"(?<=[a-z.)\"\'>])(?<![\d.])([1-6]\s{{2,}}(?:{tops}))(?=[A-Z])",
        r"\n\n\1",
        text,
    )
    text = re.sub(
        r"(?<=[a-z.)\"\'>])(?<!\d)((?:\d+\.\d+)\s{2,}[A-Z][A-Za-z])",
        r"\n\n\1",
        text,
    )
    # DOI/长数字与「1  Introduction」粘连（如 …37859301  Introduction）
    text = re.sub(
        rf"(\d{{5,}})([1-6]\s{{2,}}(?:{tops}))(?=[A-Z])",
        r"\1\n\n\2",
        text,
    )
    return text


def repair_section_headings(md: str) -> str:
    """`1  Introduction` / `2.1  Title` → Markdown 标题。"""
    if not md:
        return md

    def _top(m: re.Match[str]) -> str:
        return f"\n\n## {m.group('num')} {m.group('title')}\n\n"

    def _sub(m: re.Match[str]) -> str:
        return f"\n\n### {m.group('num')} {m.group('title').strip()}\n\n"

    text = _TOP_SECTION.sub(_top, md)
    text = _SUBSECTION.sub(_sub, text)
    return text


def repair_block_breaks(md: str) -> str:
    """摘要、关键词、图表题等块前补空行。"""
    if not md:
        return md
    text = md
    for kw in (
        "Abstract",
        "Keywords",
        "CCS Concepts",
        "ACM Reference Format",
        "References",
    ):
        text = re.sub(rf"([^\n])({re.escape(kw)})(?=[A-Z\s])", r"\1\n\n\2", text)
    text = re.sub(r"([^\n])(Figure \d+:|Table \d+:)", r"\1\n\n\2", text)
    return text


def repair_deepseek_placeholder_figures(md: str) -> str:
    """DeepSeek 幻觉 URL → FIGURE 机器标记（按最近 PAGE 与序号）。"""
    if not md or "example.com" not in md.lower():
        return md

    text = md
    spans: list[tuple[int, int, int]] = []
    for m in _EXAMPLE_FIG_MD.finditer(text):
        spans.append((m.start(), m.end(), int(m.group(1))))
    for m in _EXAMPLE_FIG_URL.finditer(text):
        spans.append((m.start(), m.end(), int(m.group(1))))
    if not spans:
        return md

    spans.sort(key=lambda x: x[0])
    merged: list[tuple[int, int, int]] = []
    for start, end, fig_n in spans:
        if merged and start < merged[-1][1]:
            continue
        merged.append((start, end, fig_n))

    last_page = 1
    out: list[str] = []
    pos = 0
    for start, end, fig_n in merged:
        chunk = text[pos:start]
        out.append(chunk)
        for pm in PAGE_MARKER_RE.finditer(chunk):
            last_page = int(pm.group(1))
        marker = f"<!-- PDF2MD:FIGURE:p{last_page:04d}:f{fig_n:02d} -->"
        out.append(marker)
        pos = end
    out.append(text[pos:])
    return "".join(out)


def repair_vision_markdown_structure(md: str) -> str:
    """仅做无损/低风险的格式修复；不猜测章节标题（避免拆坏 DeepSeek 原文）。"""
    text = md or ""
    text = repair_page_marker_breaks(text)
    text = repair_deepseek_placeholder_figures(text)
    from app.vision_transcribe.figure_markers import repair_missing_figure_markers

    text = repair_missing_figure_markers(text)
    if markdown_lacks_structure(text):
        text = repair_block_breaks(text)
        text = repair_section_line_breaks(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def has_deepseek_placeholder_images(md: str) -> bool:
    t = md or ""
    if "example.com" not in t.lower():
        return False
    return bool(_EXAMPLE_FIG_URL.search(t) or _EXAMPLE_FIG_MD.search(t))


def markdown_lacks_structure(md: str) -> bool:
    """检测是否像 selectNodeContents / inner_text 压平后的文本。"""
    if not md:
        return True
    if re.search(r"^#{1,4}\s", md, re.M):
        return False
    if re.search(r"(?m)^\|[^\n]+\|", md):
        return False
    n = len(md)
    if n < 800:
        return False
    newlines = md.count("\n")
    blanks = md.count("\n\n")
    # 长文但几乎无换行 → 扁平复制
    if n > 3000 and newlines < max(8, n // 800):
        return True
    if n > 5000 and blanks < 6:
        return True
    # PAGE 标记与正文粘在同一行
    if re.search(r"PDF2MD:PAGE:\d{4} -->[^\n]{40,}", md):
        return True
    if re.search(r"\d{2}<!-- PDF2MD:PAGE:", md):
        return True
    # 有章节痕迹但无 Markdown 标题
    if (_TOP_SECTION.search(md) or re.search(r"\d+\.\d+\s{2,}[A-Z]", md)) and blanks < 10:
        return True
    return False
