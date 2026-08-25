"""从校验/抽取错误解析失败页与分类。"""
from __future__ import annotations

import json
import re
from pathlib import Path

from app.vision_transcribe.manifest import batch_dir
from app.vision_transcribe.recovery import taxonomy as T

_PAGE_NUM = re.compile(r"PAGE\s+(\d{4})")
_MISSING_PAGES = re.compile(r"缺页标记:\s*\[([^\]]+)\]")


def load_batch_validation_errors(output_dir: Path, batch_id: int) -> list[str]:
    path = batch_dir(output_dir, batch_id) / "validation.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        errs = data.get("errors") or []
        return [str(e) for e in errs if e]
    except (OSError, json.JSONDecodeError):
        return []


def failed_pages_from_errors(errors: list[str]) -> list[int]:
    found: set[int] = set()
    for e in errors or []:
        for m in _PAGE_NUM.finditer(e):
            found.add(int(m.group(1)))
        mm = _MISSING_PAGES.search(e)
        if mm:
            for part in mm.group(1).split(","):
                part = part.strip()
                if part.isdigit():
                    found.add(int(part))
    return sorted(found)


def classify_validation_errors(errors: list[str]) -> str:
    text = " ".join(errors or []).lower()
    if "模型输出退化" in text or "缩写循环" in text:
        return T.MODEL_DEGENERATION
    if "公式完整性" in text or "formula" in text:
        return T.FORMULA_INTEGRITY_FAILED
    if "缺页" in text or "未找到任何 pdf2md:page" in text:
        return T.PAGE_MARKER_MISSING
    if "过短" in text or "截断" in text:
        return T.PAGE_CONTENT_SUSPECT
    if "sourceguard" in text or "锚点" in text:
        return T.PAGE_CONTENT_SUSPECT
    if "extraction_unstable" in text:
        return T.EXTRACTION_UNSTABLE
    if "copy" in text and "未" in text:
        return T.COPY_NOT_FIRED
    return T.EXTRACTION_CONFLICT


def contiguous_page_groups(pages: list[int]) -> list[tuple[int, int]]:
    if not pages:
        return []
    pages = sorted(set(pages))
    groups: list[tuple[int, int]] = []
    start = pages[0]
    prev = pages[0]
    for p in pages[1:]:
        if p == prev + 1:
            prev = p
            continue
        groups.append((start, prev))
        start = prev = p
    groups.append((start, prev))
    return groups
