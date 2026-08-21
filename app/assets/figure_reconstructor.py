"""将 parser 候选重建为语义 Figure 资产（V1：一图一资产 + caption 关联）。"""
from __future__ import annotations

from pathlib import Path

from app.assets.caption_matcher import find_caption_near_lines
from app.assets.figure_detector import ImageCandidate
from app.assets.models import FigureAsset


def reconstruct_figures(
    candidates: list[ImageCandidate],
    md_lines: list[str],
    *,
    pdf_stem: str,
    parser_source: str | None = None,
) -> list[FigureAsset]:
    """
    V1 策略：
    - 每个 Markdown 图片引用 = 一个语义 Figure asset（按出现顺序编号）
    - 不合并/拆分 parser bbox（避免误伤）
    - 用邻近 caption 绑定 figure_label / caption
    """
    figures: list[FigureAsset] = []
    for cand in candidates:
        idx = cand.order
        asset_id = f"fig_{idx:04d}"
        cap = find_caption_near_lines(md_lines, cand.line_index)
        parser_file = cand.local_path.name if cand.local_path else Path(cand.url).name
        ext = Path(parser_file).suffix.lower() or ".png"
        if ext not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
            ext = ".png"
        out_name = f"image_{idx}_{pdf_stem}{ext}"
        figures.append(
            FigureAsset(
                asset_id=asset_id,
                asset_index=idx,
                file=out_name,
                figure_label=cap.label if cap else None,
                caption=cap.raw if cap else None,
                caption_body=cap.body if cap else None,
                parser_source=parser_source,
                parser_file=parser_file,
                confidence=0.9 if cap else 0.6,
                path=cand.local_path,
                subfigure_status="none",
            )
        )
    return figures
