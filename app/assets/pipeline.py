"""AssetPipeline：Parser 图片候选 → 语义 Figure 资产 → 命名 / manifest / MD 引用。"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable

from app.assets.caption_matcher import extract_subfigure_labels
from app.assets.figure_detector import detect_markdown_images
from app.assets.figure_reconstructor import reconstruct_figures
from app.assets.manifest import build_manifest_payload, write_manifest
from app.assets.md_rewriter import rewrite_markdown_figures
from app.assets.models import AssetConfig, AssetPipelineResult, FigureAsset
from app.assets.renderer import render_subfigures
from app.assets.subfigure_detector import detect_subfigures, plans_to_assets
from app.assets.validator import validate_assets

ProgressCB = Callable[[str], None]


class AssetPipeline:
    def __init__(self, config: AssetConfig | None = None) -> None:
        self.config = config or AssetConfig()

    def run(
        self,
        *,
        pdf_path: Path,
        markdown_path: Path,
        images_dir: Path | None = None,
        parser_source: str | None = None,
        progress: ProgressCB | None = None,
        vision_provider: object | None = None,
    ) -> AssetPipelineResult:
        cfg = self.config
        warnings: list[str] = []

        def emit(msg: str) -> None:
            if progress:
                progress(msg)

        if not cfg.enabled:
            return AssetPipelineResult(
                markdown_path=markdown_path,
                images_dir=images_dir or (markdown_path.parent / "images"),
                manifest_path=None,
                warnings=["AssetPipeline disabled"],
            )

        md_path = markdown_path
        if not md_path.is_file():
            raise FileNotFoundError(md_path)

        images = images_dir or (md_path.parent / "images")
        images.mkdir(parents=True, exist_ok=True)
        pdf_stem = pdf_path.stem
        text = md_path.read_text(encoding="utf-8-sig")
        lines = text.splitlines()

        emit("AssetPipeline：检测 Markdown 图片候选")
        candidates = detect_markdown_images(text, md_path, images)
        if not candidates:
            emit("AssetPipeline：无本地图片引用，跳过")
            manifest_path = None
            if cfg.write_manifest:
                payload = build_manifest_payload(source_pdf=pdf_path.name, figures=[])
                manifest_path = write_manifest(images / "manifest.json", payload)
            return AssetPipelineResult(
                markdown_path=md_path,
                images_dir=images,
                manifest_path=manifest_path,
                figures=[],
                warnings=["no local images"],
            )

        missing = [c for c in candidates if c.local_path is None or not c.local_path.is_file()]
        for c in missing:
            warnings.append(f"图片文件缺失：{c.url}")

        emit(f"AssetPipeline：重建 {len(candidates)} 个 Figure 资产")
        figures = reconstruct_figures(
            candidates,
            lines,
            pdf_stem=pdf_stem,
            parser_source=parser_source,
        )

        # 物化主图（保留 composite；复制到规范名）
        used_sources: set[Path] = set()
        for fig, cand in zip(figures, candidates):
            if cand.local_path is None or not cand.local_path.is_file():
                continue
            dest = images / fig.file
            src = cand.local_path.resolve()
            if src != dest.resolve():
                if dest.exists() and dest.resolve() != src:
                    dest.unlink()
                shutil.copy2(src, dest)
                used_sources.add(src)
            fig.path = dest

            # 子图：仅在 Vision 证据充分时拆
            vision_result = None
            if cfg.enable_subfigure_split and vision_provider is not None:
                vision_result = _try_vision_subfigures(vision_provider, dest)
            elif cfg.enable_subfigure_split and extract_subfigure_labels(fig.caption or ""):
                # caption 暗示有子图，但无 vision → 记录 skipped
                fig.subfigure_status = "skipped"

            plans, status = detect_subfigures(
                fig,
                enable_split=cfg.enable_subfigure_split,
                require_all=cfg.require_all_subfigures,
                min_confidence=cfg.min_subfigure_confidence,
                vision_result=vision_result,
            )
            fig.subfigure_status = status
            if status == "extracted" and plans:
                try:
                    rendered = render_subfigures(
                        dest,
                        plans,
                        out_dir=images,
                        parent_index=fig.asset_index,
                        pdf_stem=pdf_stem,
                    )
                    if len(rendered) != len(plans):
                        # 保守：全部回滚子图文件
                        for _, p in rendered:
                            p.unlink(missing_ok=True)
                        fig.subfigures = []
                        fig.subfigure_status = "uncertain"
                        warnings.append(f"{fig.asset_id} 子图裁切不完整，已放弃拆分")
                    else:
                        ext = dest.suffix.lower() or ".png"
                        fig.subfigures = plans_to_assets(
                            plans,
                            parent_index=fig.asset_index,
                            pdf_stem=pdf_stem,
                            ext=ext,
                        )
                        for s, (_, p) in zip(fig.subfigures, rendered):
                            s.path = p
                        emit(
                            f"AssetPipeline：{fig.file} 拆出 {len(fig.subfigures)} 个子图"
                        )
                except Exception as e:
                    fig.subfigures = []
                    fig.subfigure_status = "uncertain"
                    warnings.append(f"{fig.asset_id} 子图裁切失败：{e}")

        # 清理已替换的 parser 原文件（绝不删除新主图 / 子图 / manifest）
        if cfg.cleanup_parser_files:
            keep_names = {f.file for f in figures}
            for f in figures:
                for s in f.subfigures:
                    keep_names.add(s.file)
            keep_names.add("manifest.json")
            for src in used_sources:
                try:
                    if src.parent.resolve() == images.resolve() and src.name not in keep_names:
                        if src.is_file():
                            src.unlink()
                except OSError:
                    pass

        emit("AssetPipeline：重写 Markdown 图片引用")
        new_text = rewrite_markdown_figures(
            text,
            figures,
            md_path=md_path,
            images_dir=images,
            image_path_mode=cfg.image_path_mode,
        )
        md_path.write_text(new_text, encoding="utf-8")

        manifest_path = None
        if cfg.write_manifest:
            payload = build_manifest_payload(source_pdf=pdf_path.name, figures=figures)
            manifest_path = write_manifest(images / "manifest.json", payload)
            emit(f"AssetPipeline：写入 {manifest_path.name}")

        val_warn = validate_assets(new_text, md_path, images, figures)
        warnings.extend(val_warn)
        for w in val_warn:
            emit(f"Asset 校验：{w}")

        return AssetPipelineResult(
            markdown_path=md_path,
            images_dir=images,
            manifest_path=manifest_path,
            figures=figures,
            warnings=warnings,
            metadata={"count": len(figures)},
        )


def _try_vision_subfigures(provider: object, image_path: Path) -> dict | None:
    """可选 VisionProvider：需实现 analyze_figure(path)->dict。"""
    try:
        fn = getattr(provider, "analyze_figure", None) or getattr(provider, "transcribe", None)
        if fn is None:
            return None
        # 优先专用接口
        if hasattr(provider, "analyze_figure"):
            data = provider.analyze_figure(image_path)  # type: ignore[attr-defined]
            return data if isinstance(data, dict) else None
        # 退化为 transcribe + 不解析
        return None
    except Exception:
        return None
