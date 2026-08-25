"""逐页完整性检测（P1）。"""
from __future__ import annotations

import re
from pathlib import Path

from app.vision_transcribe.capture.page_split import PageSlice, split_pages
from app.vision_transcribe.integrity.source_guard import check_page_anchors, load_page_guard
from app.vision_transcribe.models import BATCH_END_RE, PAGE_END_RE
from app.vision_transcribe.prompts import PROMPT_VERSION
from app.vision_transcribe.transcript_quality import is_references_heavy, min_chars_for_page_span

_FIGURE_MARKER_RE = re.compile(r"<!--\s*PDF2MD:FIGURE:", re.I)
# 允许 **Figure 6.** / Figure 6. / Fig. 6
_FIGURE_CAPTION_RE = re.compile(
    r"(?m)^\s*\*{0,2}\s*(?:Figure|Fig\.?)\s*\d+\s*\.?\s*\*{0,2}",
    re.I,
)
_TABLE_ROW_RE = re.compile(r"(?m)^\|[^\n]+\|")
_NEAR_MISS_RATIO = 0.88
# 学术单页正文通常 2k–8k；超过此值且伴随循环/继续膨胀则视为未完成
_MAX_SANE_PAGE_CHARS = 20_000
_MAX_HARD_PAGE_CHARS = 28_000


def is_figure_heavy_page(body: str) -> bool:
    t = body or ""
    if _FIGURE_MARKER_RE.search(t):
        return True
    return bool(_FIGURE_CAPTION_RE.search(t))


def is_figure_only_page(body: str) -> bool:
    """几乎只有图题/FIGURE 标记的短页（学术 PDF 常见整页大图）。"""
    t = (body or "").strip()
    if not t or len(t) > 280:
        return False
    if not is_figure_heavy_page(t):
        return False
    # 去掉图题/机器标记/批次标记后几乎无正文
    stripped = re.sub(r"<!--\s*PDF2MD:[^>]*-->", "", t, flags=re.I)
    stripped = _FIGURE_CAPTION_RE.sub("", stripped)
    stripped = re.sub(r"\*+", "", stripped)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    return len(stripped) < 40


def is_table_heavy_page(body: str) -> bool:
    return len(_TABLE_ROW_RE.findall(body or "")) >= 4


def is_reference_page_body(body: str) -> bool:
    """单页以参考文献条目为主（含末页续页）。"""
    t = (body or "").strip()
    if not t:
        return False
    if re.search(r"(?m)^\[\d{1,3}\]", t):
        return True
    if re.search(r"\(\d{4}\)[\.,]", t) and (
        "doi:" in t.lower() or "http" in t.lower() or "retrieved from" in t.lower()
    ):
        return True
    return False


def is_reference_continuation_page(body: str) -> bool:
    return bool(re.search(r"\(contd\.\s*from\s*page", body or "", re.I))


def is_boilerplate_header_page(body: str) -> bool:
    """期刊页眉/页脚重复行（末页常仅含刊名）。"""
    t = (body or "").strip()
    if len(t) > 280:
        return False
    if "Published in partnership" in t:
        return True
    if re.search(r"npj Science of Learning", t, re.I):
        return True
    if re.search(r"www\.nature\.com/scientificreports", t, re.I):
        return True
    return False


def min_chars_for_single_page(page_no: int, *, body: str = "") -> int:
    if is_references_heavy(body) or is_reference_page_body(body):
        return 120
    if is_reference_continuation_page(body):
        return 100
    if is_boilerplate_header_page(body):
        return 80
    if is_figure_only_page(body):
        return 25
    if is_figure_heavy_page(body):
        return 100
    if is_table_heavy_page(body):
        return 180
    return 280


def validate_page_integrity(
    md: str,
    *,
    start_page: int,
    end_page: int,
    batch_id: int = 0,
    output_dir: Path | None = None,
    prompt_version: str = "",
) -> tuple[list[str], list[str], dict[int, PageSlice]]:
    """返回 (errors, warnings, page_slices)。"""
    errors: list[str] = []
    warnings: list[str] = []
    slices = split_pages(md)
    require_end = (
        prompt_version >= PROMPT_VERSION
        or bool(PAGE_END_RE.search(md or ""))
    )
    require_batch_end = (
        prompt_version >= PROMPT_VERSION
        or bool(BATCH_END_RE.search(md or ""))
    )

    for p in range(start_page, end_page + 1):
        sl = slices.get(p)
        if sl is None:
            continue
        min_c = min_chars_for_single_page(p, body=sl.body)
        if sl.chars < min_c:
            near_miss = sl.has_end and sl.chars >= int(min_c * _NEAR_MISS_RATIO)
            if near_miss:
                warnings.append(
                    f"PAGE {p:04d} 略短（{sl.chars} 字，期望 ≥{min_c}），已放行"
                )
            else:
                errors.append(
                    f"PAGE {p:04d} 过短（{sl.chars} 字，期望 ≥{min_c}）"
                )
        if sl.chars > _MAX_SANE_PAGE_CHARS:
            from app.vision_transcribe.transcript_quality import has_model_degeneration

            if has_model_degeneration(sl.body) or sl.chars >= _MAX_HARD_PAGE_CHARS:
                errors.append(
                    f"PAGE {p:04d} 异常过长（{sl.chars} 字），疑似模型循环输出"
                )
        if require_end and not sl.has_end:
            warnings.append(f"PAGE {p:04d} 缺少 PAGE_END 标记")

        if output_dir is not None:
            guard = load_page_guard(output_dir, p)
            if guard:
                miss = check_page_anchors(p, sl.body, guard)
                if miss:
                    sample = ", ".join(miss[:5])
                    warnings.append(
                        f"PAGE {p:04d} SourceGuard 锚点疑似缺失: {sample}"
                    )

    if require_batch_end and batch_id > 0:
        if not BATCH_END_RE.search(md or ""):
            warnings.append(f"缺少 BATCH_END:{batch_id:04d} 标记")
        else:
            found = [int(m.group(1)) for m in BATCH_END_RE.finditer(md or "")]
            if batch_id not in found:
                warnings.append(
                    f"BATCH_END 批次号不符: got={found} expected={batch_id:04d}"
                )

    # 批次总字数仍作兜底（兼容旧逻辑）
    n_pages = end_page - start_page + 1
    if n_pages == 1:
        sl = slices.get(start_page)
        batch_min = min_chars_for_single_page(
            start_page, body=sl.body if sl else ""
        )
    else:
        batch_min = min_chars_for_page_span(start_page, end_page)
    if len((md or "").strip()) < batch_min:
        errors.append(
            f"批次过短（{len((md or '').strip())} 字，"
            f"{n_pages} 页期望 ≥{batch_min}）"
        )

    return errors, warnings, slices
