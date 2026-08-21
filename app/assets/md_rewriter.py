"""重写 Markdown 图片引用：默认只引用完整主图。"""
from __future__ import annotations

import re
from pathlib import Path

from app.assets.caption_matcher import parse_caption_line
from app.assets.models import FigureAsset
from app.utils.md_postprocess import _is_md_table_line, ensure_figure_table_separation

_IMG_LINE = re.compile(r"^(\s*)!\[([^\]]*)\]\(([^)]+)\)(\s*)$")


def _format_url(images_dir: Path, filename: str, md_path: Path, mode: str) -> str:
    dest = images_dir / filename
    if mode == "absolute":
        return str(dest.resolve())
    try:
        rel = dest.resolve().relative_to(md_path.parent.resolve())
        return rel.as_posix()
    except ValueError:
        return f"images/{filename}"


def _caption_md_block(figure: FigureAsset) -> str | None:
    if not figure.figure_label:
        return None
    body = (figure.caption_body or "").strip()
    if body:
        return f"**{figure.figure_label}.** {body}"
    return f"**{figure.figure_label}.**"


def _is_same_caption(line: str, figure: FigureAsset) -> bool:
    if not figure.figure_label:
        return False
    pc = parse_caption_line(line)
    if not pc:
        return False
    return pc.label.lower() == figure.figure_label.lower()


def rewrite_markdown_figures(
    md_text: str,
    figures: list[FigureAsset],
    *,
    md_path: Path,
    images_dir: Path,
    image_path_mode: str = "relative",
) -> str:
    """
    - 替换为 image_X_stem；alt = 原文 figure_label（无则空）
    - 正文不插入子图
    - caption 规范为独立 **Label.** body，并去掉紧邻重复行
    """
    if not figures:
        return ensure_figure_table_separation(md_text)

    by_order = {f.asset_index: f for f in figures}
    lines = md_text.splitlines(keepends=True)
    out: list[str] = []
    img_seen = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        core = line[:-1] if line.endswith("\n") else line
        nl = "\n" if line.endswith("\n") else ""
        m = _IMG_LINE.match(core)
        if not m:
            out.append(line)
            i += 1
            continue

        img_seen += 1
        fig = by_order.get(img_seen)
        if not fig:
            out.append(line)
            i += 1
            continue

        # 若上方最近非空行是同一 caption，去掉（caption 改到图后）
        while out and not (out[-1][:-1] if out[-1].endswith("\n") else out[-1]).strip():
            out.pop()
        if out:
            prev_core = out[-1][:-1] if out[-1].endswith("\n") else out[-1]
            if _is_same_caption(prev_core, fig):
                out.pop()
                while out and not (out[-1][:-1] if out[-1].endswith("\n") else out[-1]).strip():
                    out.pop()

        url = _format_url(images_dir, fig.file, md_path, image_path_mode)
        alt = fig.figure_label or ""
        # 硬规则：若上一非空行是表格，图片前必须空一行（否则图片会并进表格）
        if out:
            prev_core = out[-1][:-1] if out[-1].endswith("\n") else out[-1]
            if _is_md_table_line(prev_core):
                out.append("\n")
        out.append(f"{m.group(1)}![{alt}]({url}){nl}")

        # 跳过图后紧邻的同 caption
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        if j < len(lines):
            nxt = lines[j][:-1] if lines[j].endswith("\n") else lines[j]
            if _is_same_caption(nxt, fig):
                i = j + 1
            else:
                i += 1
        else:
            i += 1

        block = _caption_md_block(fig)
        if block:
            out.append(block + "\n")
        continue

    return ensure_figure_table_separation("".join(out))
