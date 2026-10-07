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
    images_dir: Path | None = None,
    image_path_mode: str = "relative",
    figure_labels: dict[str, int] | None = None,
) -> str:
    """按标记替换；已是 ![](...) 的不重复追加。幂等。

    images_dir：图片实际所在目录（默认 <output_dir>/images）。扁平保存时可能是
    <导出目录>/<PDF名>.images/，md 与图片不同目录也按真实相对路径写出。
    """
    by_key = {f.marker: f for f in figures if f.status == "done" and f.file}
    check_exists = output_dir is not None or images_dir is not None
    if images_dir is None:
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
        if check_exists and not (images_dir / fname).is_file():
            return m.group(0)
        url = _format_url(images_dir, fname, md_parent, image_path_mode)
        alt = f"Figure {labels[key]}" if key in labels else "Figure"
        return f"![{alt}]({url})"

    return FIGURE_MARKER_RE.sub(_repl, md or "")
