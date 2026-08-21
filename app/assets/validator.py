"""AssetPipeline 输出校验。"""
from __future__ import annotations

import re
from pathlib import Path

from app.assets.models import FigureAsset


_IMG = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


def validate_assets(
    md_text: str,
    md_path: Path,
    images_dir: Path,
    figures: list[FigureAsset],
) -> list[str]:
    warnings: list[str] = []

    for f in figures:
        p = images_dir / f.file
        if not p.is_file():
            warnings.append(f"manifest 主图缺失：{f.file}")
        for s in f.subfigures:
            sp = images_dir / s.file
            if not sp.is_file():
                warnings.append(f"子图文件缺失：{s.file}")
            # 子图不得出现在 MD 默认正文引用中（软检查）
        if f.figure_label is None and f.asset_index:
            # 允许无 label；禁止用 asset_index 冒充 Figure N —— 由 rewriter 保证
            pass

    for m in _IMG.finditer(md_text):
        url = m.group(2).strip()
        if url.lower().startswith(("http://", "https://", "data:")):
            continue
        name = Path(url.replace("\\", "/")).name
        # 禁止残留 parser hash 长名（启发式：超长 hex）
        if re.search(r"[a-f0-9]{40,}", name, re.I) and not name.startswith("image_"):
            warnings.append(f"疑似未改写的 parser 图片引用：{name}")
        # 子图文件不应作为正文唯一引用目标时的默认 —— 若引用了 *-N_ 也警告
        if re.match(r"image_\d+-\d+_", name):
            warnings.append(f"正文引用了子图（默认应引用主图）：{name}")
        # 文件存在性
        cand = Path(url)
        if not cand.is_file():
            cand = (md_path.parent / url).resolve()
        if not cand.is_file():
            cand2 = images_dir / name
            if not cand2.is_file():
                warnings.append(f"Markdown 引用文件不存在：{url}")

    # 每个 figure 应有主图
    for f in figures:
        if not f.file:
            warnings.append(f"{f.asset_id} 缺少 file")

    return warnings
