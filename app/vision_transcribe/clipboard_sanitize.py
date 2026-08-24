"""DeepSeek 剪贴板清洗：去掉侧栏历史、Prompt 回声，只保留转录正文。"""
from __future__ import annotations

import re

from app.vision_transcribe.models import PAGE_MARKER_RE
from app.vision_transcribe.vision_structure_repair import repair_vision_markdown_structure

_PROMPT_SIGNATURES = (
    "你正在执行 PDF",
    "PDF → Markdown 高保真",
    "高保真内容转录任务",
    "本批次为 PAGE",
    "只允许将原内容转换为 Typora",
)

_SIDEBAR_SIGNATURES = (
    "Cursor聊天记录",
    "开启新对话",
    "Cursor Origin",
    "Codex开源",
    "积分极限计算题",
)

# 侧栏会话标题行：短、无空格或纯英文短语
_SHORT_TITLE_LINE = re.compile(
    r"^[\s\u200b\t]*(?:"
    r"PDF转Markdown|PDF参考|SES|High-SES|Unicode|Typora|Cursor|Word公式|"
    r"[A-Za-z0-9][A-Za-z0-9 \-\.\']{0,48}"
    r")[\s\u200b\t]*$"
)


def first_page_marker_index(text: str) -> int | None:
    m = PAGE_MARKER_RE.search(text or "")
    return m.start() if m else None


def has_clipboard_contamination(text: str) -> bool:
    """剪贴板含侧栏 / Prompt 污染（即使后面有 PAGE 标记）。"""
    t = text or ""
    if any(sig in t for sig in _PROMPT_SIGNATURES):
        return True
    if any(sig in t for sig in _SIDEBAR_SIGNATURES):
        return True
    idx = first_page_marker_index(t)
    if idx is None:
        return False
    prefix = t[:idx]
    if len(prefix.strip()) < 80:
        return False
    lines = [ln.strip() for ln in prefix.splitlines() if ln.strip()]
    if len(lines) < 8:
        return False
    short = sum(1 for ln in lines if len(ln) <= 48 and _SHORT_TITLE_LINE.match(ln))
    return short >= max(6, int(len(lines) * 0.55))


def extract_from_first_page_marker(text: str) -> str:
    """丢弃第一个 PAGE 标记之前的侧栏 / Prompt 垃圾。"""
    t = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    idx = first_page_marker_index(t)
    if idx is None:
        return t.strip()
    return t[idx:].lstrip("\n")


def sanitize_vision_clipboard(text: str) -> str:
    """入库前确定性清洗（不改 PAGE 标记之后正文的语义）。"""
    body = extract_from_first_page_marker(text)
    body = repair_vision_markdown_structure(body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip() + ("\n" if body.strip() else "")


def page_numbers_in_text(text: str) -> list[int]:
    return [int(m.group(1)) for m in PAGE_MARKER_RE.finditer(text or "")]
