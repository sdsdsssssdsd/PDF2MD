"""从 Markdown 中检测 parser 图片候选。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote


_IMG_MD = re.compile(
    r"!\[(?P<alt>[^\]]*)\]\((?P<url>[^)]+)\)",
)


@dataclass
class ImageCandidate:
    """Markdown 中出现的一张本地图片。"""

    order: int  # 1-based appearance in MD
    alt: str
    url: str
    line_index: int
    match_start: int
    match_end: int
    local_path: Path | None


def _is_remote(url: str) -> bool:
    u = url.strip().lower()
    return u.startswith("http://") or u.startswith("https://") or u.startswith("data:")


def resolve_image_path(url: str, md_path: Path, images_dir: Path | None) -> Path | None:
    raw = unquote(url.strip().strip("<>").split()[0])
    if _is_remote(raw):
        return None
    p = Path(raw)
    if p.is_file():
        return p.resolve()
    cand = (md_path.parent / raw).resolve()
    if cand.is_file():
        return cand
    name = Path(raw.replace("\\", "/")).name
    if images_dir:
        cand2 = (images_dir / name).resolve()
        if cand2.is_file():
            return cand2
    return None


def detect_markdown_images(
    md_text: str,
    md_path: Path,
    images_dir: Path | None,
) -> list[ImageCandidate]:
    lines = md_text.splitlines(keepends=True)
    out: list[ImageCandidate] = []
    offset = 0
    order = 0
    for li, line in enumerate(lines):
        for m in _IMG_MD.finditer(line):
            url = m.group("url").strip()
            if _is_remote(url):
                continue
            order += 1
            local = resolve_image_path(url, md_path, images_dir)
            out.append(
                ImageCandidate(
                    order=order,
                    alt=m.group("alt") or "",
                    url=url,
                    line_index=li,
                    match_start=offset + m.start(),
                    match_end=offset + m.end(),
                    local_path=local,
                )
            )
        offset += len(line)
    return out
