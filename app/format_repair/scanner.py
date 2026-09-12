"""Markdown 词法保护区域扫描。"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ProtectedRegion:
    start: int
    end: int
    kind: str
    token: str
    original: str = ""


_FENCE_RE = re.compile(r"```[\s\S]*?```|~~~[\s\S]*?~~~")
_INLINE_CODE_RE = re.compile(r"(?<!`)`[^`\n]+`(?!`)")
_URL_RE = re.compile(r"https?://[^\s<>\"']+")
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_HTML_RE = re.compile(r"<[A-Za-z][^>]*>")
_YAML_RE = re.compile(r"\A---\s*\n[\s\S]*?\n---\s*(?:\n|$)")


def extract_protected_regions(text: str) -> tuple[str, list[ProtectedRegion]]:
    spans: list[tuple[int, int, str]] = []
    for pattern, kind in (
        (_FENCE_RE, "fenced_code"),
        (_INLINE_CODE_RE, "inline_code"),
        (_IMAGE_RE, "image"),
        (_URL_RE, "url"),
        (_HTML_RE, "html"),
        (_YAML_RE, "yaml"),
    ):
        for m in pattern.finditer(text):
            spans.append((m.start(), m.end(), kind))

    spans.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    kept: list[tuple[int, int, str]] = []
    last_end = -1
    for start, end, kind in spans:
        if start < last_end:
            continue
        kept.append((start, end, kind))
        last_end = end

    regions: list[ProtectedRegion] = []
    out = text
    ordered = sorted(kept, reverse=True)
    for index, (start, end, kind) in enumerate(ordered):
        token = f"@@PDF2MD_PROTECTED_{index:04d}@@"
        regions.append(
            ProtectedRegion(
                start=start,
                end=end,
                kind=kind,
                token=token,
                original=text[start:end],
            )
        )
        out = out[:start] + token + out[end:]

    regions.sort(key=lambda r: r.start)
    return out, regions


def restore_protected_regions(text: str, regions: list[ProtectedRegion]) -> str:
    out = text
    for region in sorted(regions, key=lambda r: r.start, reverse=True):
        out = out.replace(region.token, region.original, 1)
    return out


def protect_markdown(text: str) -> tuple[str, list[tuple[str, str]]]:
    """返回 (masked_text, [(token, original), ...])。"""
    masked, regions = extract_protected_regions(text)
    return masked, [(r.token, r.original) for r in regions]
