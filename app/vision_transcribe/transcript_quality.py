"""转录正文质量评分与择优（复制 vs DOM）。"""
from __future__ import annotations

import re

from app.vision_transcribe.clipboard_sanitize import page_numbers_in_text
from app.vision_transcribe.vision_structure_repair import markdown_lacks_structure

_BATCH_PAGE_RE = re.compile(r"本批次为 PAGE (\d+) 至 PAGE (\d+)")


def parse_batch_pages_from_prompt(prompt: str) -> tuple[int | None, int | None]:
    m = _BATCH_PAGE_RE.search(prompt or "")
    if not m:
        return None, None
    return int(m.group(1)), int(m.group(2))


def min_chars_for_page_span(start_page: int, end_page: int) -> int:
    n = max(1, end_page - start_page + 1)
    if n == 1:
        return 400  # 末页参考文献等
    return n * 1200


def is_references_heavy(md: str) -> bool:
    head = (md or "")[:12_000]
    return bool(
        re.search(r"\bReferences\b", head, re.I)
        or re.search(r"\[\d{1,3}\].{10,}https?://", head)
    )


def transcript_rank(md: str) -> int:
    """越高越好；不可用返回 -1。"""
    t = (md or "").strip()
    if len(t) < 200:
        return -1
    try:
        from app.vision_transcribe.browser.katex_scrap import has_dom_katex_scrap

        if has_dom_katex_scrap(t):
            return -1
    except Exception:
        pass
    try:
        from app.vision_transcribe.clipboard_sanitize import has_clipboard_contamination

        if has_clipboard_contamination(t):
            return -1
    except Exception:
        pass

    score = len(t)
    pages = page_numbers_in_text(t)
    if pages:
        score += len(set(pages)) * 5000
    if not markdown_lacks_structure(t):
        score += 200_000
    if re.search(r"(?m)^#{1,4}\s", t):
        score += 80_000
    if re.search(r"(?m)^\|[^\n]+\|", t):
        score += 80_000
    if "<!-- PDF2MD:FIGURE:" in t or "PDF2MD:FIGURE" in t:
        score += 5000
    return score


def batch_transcript_complete(
    md: str,
    *,
    start_page: int | None = None,
    end_page: int | None = None,
) -> bool:
    """批次 PAGE 范围 + 字数是否达标。"""
    if start_page is None or end_page is None:
        return len((md or "").strip()) >= 2000
    return not looks_truncated_transcript(
        md or "", start_page=start_page, end_page=end_page
    )


def looks_truncated_transcript(
    md: str,
    *,
    start_page: int | None = None,
    end_page: int | None = None,
) -> bool:
    """疑似复制截断 / 压平。有批次页码时以 PAGE 集合 + 最短字数为准，勿对参考文献页强求 ##。"""
    t = (md or "").strip()
    if not t:
        return True

    pages = page_numbers_in_text(t)
    n_batch = (
        (end_page - start_page + 1)
        if start_page is not None and end_page is not None
        else None
    )

    if start_page is not None and end_page is not None:
        min_len = min_chars_for_page_span(start_page, end_page)
        if len(t) < min_len:
            return True
        expected = set(range(start_page, end_page + 1))
        found = set(pages)
        if found == expected:
            return False
        # 单页参考文献偶发缺 PAGE：字数够 + 文献特征 → 交给 batch_validator 告警
        if n_batch == 1 and len(t) >= min_len and is_references_heavy(t):
            return False
        if not found and n_batch == 1 and len(t) >= min_len * 2:
            return False
        return True

    # 无批次上下文（复制按钮快速检查）
    if pages:
        n = len(set(pages))
        min_len = min_chars_for_page_span(1, n)
        if len(t) >= min_len:
            if n == 1:
                return False
            if not markdown_lacks_structure(t):
                return False
    if is_references_heavy(t) and len(t) >= 2500:
        return False
    if len(t) < 600:
        return True
    if markdown_lacks_structure(t) and len(t) < 3500:
        return True
    return False


def pick_best_transcript(
    *candidates: tuple[str, str],
) -> tuple[str, str]:
    """从 (来源名, markdown) 列表中选最佳；公式完整性优先于字数。"""
    from app.vision_transcribe.formula_integrity import formula_integrity_errors

    scored: list[tuple[int, int, str, str]] = []
    for name, text in candidates:
        t = (text or "").strip()
        rank = transcript_rank(t)
        if rank < 0:
            continue
        err_n = len(formula_integrity_errors(t))
        # (错误数, -rank) 升序 → 先无错误，再高分
        scored.append((err_n, -rank, name, t))

    if not scored:
        return "", ""

    scored.sort(key=lambda x: (x[0], x[1]))
    _, _, best_name, best_text = scored[0]
    return best_name, best_text
