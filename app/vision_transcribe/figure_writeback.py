"""将 FIGURE 标记替换为图片引用（相对/绝对路径，与快速自动一致）。"""
from __future__ import annotations

import re
from pathlib import Path

from app.assets.md_rewriter import _format_url
from app.vision_transcribe.models import FIGURE_MARKER_RE, FigureRecord


def writeback_figures(
    md: str,
    figures: list[FigureRecord],
    *,
    md_path: Path | None = None,
    output_dir: Path | None = None,
    image_path_mode: str = "relative",
    figure_labels: dict[str, int] | None = None,
) -> str:
    """按标记替换；已是 ![](...) 的不重复追加。幂等。"""
    by_key = {f.marker: f for f in figures if f.status == "done" and f.file}
    images_dir = (output_dir / "images") if output_dir else Path("images")
    md_parent = md_path.parent if md_path else Path(".")
    labels = figure_labels or {}

    def _repl(m: re.Match[str]) -> str:
        page = int(m.group(1))
        idx = int(m.group(2))
        key = f"p{page:04d}:f{idx:02d}"
        rec = by_key.get(key)
        if not rec:
            return m.group(0)
        fname = Path(str(rec.file).replace("\\", "/")).name
        if output_dir is not None:
            if not (output_dir / "images" / fname).is_file():
                return m.group(0)
            url = f"images/{fname}"
        elif image_path_mode == "absolute":
            url = _format_url(images_dir, fname, md_parent, "absolute")
        else:
            url = _format_url(images_dir, fname, md_parent, image_path_mode)
        alt = f"Figure {labels[key]}" if key in labels else "Figure"
        return f"![{alt}]({url})"

    return FIGURE_MARKER_RE.sub(_repl, md or "")
