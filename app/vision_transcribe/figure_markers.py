"""FIGURE 占位符：补全缺失标记、从题注解析 Figure 编号。"""
from __future__ import annotations

import re

from app.vision_transcribe.models import FIGURE_MARKER_RE, PAGE_MARKER_RE

# Figure 1: / Figure 1. / **Figure 1.** / **Figure 1:**
_FIGURE_CAPTION_LINE = re.compile(
    r"^(?:\*\*)?\s*Figure\s+(\d+)\s*[\.:：]\s*(?:\*\*)?",
    re.I,
)
_MD_IMAGE_LINE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


def figure_numbers_by_marker(md: str) -> dict[str, int]:
    """从每个 FIGURE 标记后题注解析 Figure 编号 → marker key。"""
    out: dict[str, int] = {}
    text = md or ""
    for m in FIGURE_MARKER_RE.finditer(text):
        key = f"p{int(m.group(1)):04d}:f{int(m.group(2)):02d}"
        tail = text[m.end() : m.end() + 600]
        cap = _FIGURE_CAPTION_LINE.search(tail.lstrip())
        if cap:
            out[key] = int(cap.group(1))
    return out


def repair_missing_figure_markers(md: str) -> str:
    """题注 Figure N 前无占位符、附近也无图片时，插入 FIGURE 标记（按最近 PAGE）。"""
    if not md:
        return md
    lines = md.splitlines(keepends=True)
    out: list[str] = []
    last_page = 1
    fig_on_page: dict[int, int] = {}
    for i, line in enumerate(lines):
        pm = PAGE_MARKER_RE.search(line)
        if pm:
            last_page = int(pm.group(1))
        stripped = line.strip()
        cap = _FIGURE_CAPTION_LINE.match(stripped)
        if cap:
            prefix = "".join(lines[max(0, i - 6) : i])
            nearby_has_marker = "PDF2MD:FIGURE" in prefix
            nearby_has_image = "![" in prefix
            if not nearby_has_marker and not nearby_has_image:
                fig_on_page[last_page] = fig_on_page.get(last_page, 0) + 1
                idx = fig_on_page[last_page]
                out.append(
                    f"<!-- PDF2MD:FIGURE:p{last_page:04d}:f{idx:02d} -->\n\n"
                )
        out.append(line)
    return "".join(out)


def strip_orphan_figure_markers_after_images(md: str) -> str:
    """图片行后紧跟的未替换 FIGURE 标记删掉（避免 ![] 与注释双写）。"""
    if not md or "PDF2MD:FIGURE" not in md:
        return md or ""
    lines = (md or "").splitlines(keepends=True)
    out: list[str] = []
    i = 0
    while i < len(lines):
        out.append(lines[i])
        if _MD_IMAGE_LINE.search(lines[i]):
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                out.append(lines[j])
                j += 1
            if j < len(lines) and FIGURE_MARKER_RE.search(lines[j]):
                j += 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                i = j
                continue
        i += 1
    return "".join(out)


_MARKER_ONLY_LINE = re.compile(r"^\s*<!--\s*PDF2MD:FIGURE:p(\d{4}):f(\d{2})\s*-->\s*$")


def _adjacent_figure_runs(lines: list[str]) -> list[list[int]]:
    """连续紧邻（中间只有空行）且同一页的 FIGURE 占位符行号分组；≥2 个才算一组。"""
    runs: list[list[int]] = []
    current: list[int] = []
    current_page: int | None = None

    def _flush() -> None:
        nonlocal current, current_page
        if len(current) >= 2:
            runs.append(current)
        current = []
        current_page = None

    for i, line in enumerate(lines):
        m = _MARKER_ONLY_LINE.match(line)
        if m:
            page = int(m.group(1))
            if current and page != current_page:
                _flush()
            if not current:
                current_page = page
            current.append(i)
            continue
        if not line.strip() and current:
            continue  # 空行不打断连续段
        _flush()
    _flush()
    return runs


def collapse_adjacent_figure_markers(md: str) -> str:
    """同一页连续紧邻的多个 FIGURE 占位符合并成一个（保留第一个）。

    实测 [01]_Kuzilek2017 第 7 页：整页只有一张 Figure 5，是 a–f 六个子图，模型却连着
    写了 6 个占位符；Docling 那一页只出 1 张图 → 3 个占位符无图可插 → 完成门判整篇失败。
    只合并「同一页 + 彼此之间没有任何正文」的连续占位符；像该文第 3 页那样中间夹着正文的
    两个占位符（确实是两张图）原样保留。
    """
    text = md or ""
    if "PDF2MD:FIGURE" not in text:
        return text
    lines = text.splitlines(keepends=True)
    drop: set[int] = set()
    for run in _adjacent_figure_runs(lines):
        drop.update(run[1:])
    if not drop:
        return text
    return "".join(line for i, line in enumerate(lines) if i not in drop)


def adjacent_figure_merge_notes(md: str) -> list[str]:
    """给日志用：说明哪些页发生了「连续占位符合并」，不修改正文。"""
    lines = (md or "").splitlines(keepends=True)
    notes: list[str] = []
    for run in _adjacent_figure_runs(lines):
        first = _MARKER_ONLY_LINE.match(lines[run[0]])
        if not first:
            continue
        page = int(first.group(1))
        keep = f"p{page:04d}:f{int(first.group(2)):02d}"
        notes.append(
            f"第 {page} 页有 {len(run)} 个连续 FIGURE 占位符"
            f"（多半是同一张图的 a–f 子图），按一张图处理，保留 {keep}"
        )
    return notes


def count_figure_captions(md: str) -> list[int]:
    nums: list[int] = []
    for line in (md or "").splitlines():
        m = _FIGURE_CAPTION_LINE.match(line.strip())
        if m:
            nums.append(int(m.group(1)))
    return nums


def figure_completion_errors(md: str) -> list[str]:
    """完成门禁：占位符须全部换成图片，图题数量不得明显多于已插图。"""
    text = md or ""
    errors: list[str] = []
    bare = list(FIGURE_MARKER_RE.finditer(text))
    if bare:
        sample = ", ".join(
            f"p{int(m.group(1)):04d}:f{int(m.group(2)):02d}" for m in bare[:5]
        )
        more = f" 等{len(bare)}处" if len(bare) > 5 else ""
        errors.append(
            f"仍有未替换的 FIGURE 占位符（{sample}{more}），图片未全部写入"
        )
    try:
        from app.vision_transcribe.vision_structure_repair import (
            has_deepseek_placeholder_images,
        )

        if has_deepseek_placeholder_images(text):
            errors.append("仍含 example.com 虚构图片 URL")
    except Exception:
        pass

    captions = count_figure_captions(text)
    images = _MD_IMAGE_LINE.findall(text)
    # 去重图题编号：同一 Figure N 重复出现只计一次
    unique_caps = sorted(set(captions))
    if unique_caps and len(images) < len(unique_caps):
        errors.append(
            f"图题 {len(unique_caps)} 个（Figure {unique_caps[0]}–{unique_caps[-1]}），"
            f"但仅插入图片 {len(images)} 张，图片未全部插入"
        )
    return errors
