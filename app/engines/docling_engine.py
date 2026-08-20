"""Docling 引擎：优先 Python API，默认走快速配置；模型优先用本地缓存。"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Callable

from app.utils.paths import DOCLING_ARTIFACTS_DIR

ProgressCB = Callable[[str], None]

# 复用转换器，避免每个 PDF 重复加载模型
_converter_cache: dict[tuple, object] = {}


def _artifacts_dir() -> Path:
    """Docling 本地模型目录：PDF2MD_DOCLING_ARTIFACTS > 项目 .cache。"""
    override = os.environ.get("PDF2MD_DOCLING_ARTIFACTS", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return DOCLING_ARTIFACTS_DIR


def _ensure_runtime_env() -> None:
    """无争议运行时开关；不强制 HF 镜像（尊重用户已设置的 HF_ENDPOINT）。"""
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
    os.environ.setdefault("USE_TF", "0")
    os.environ.setdefault("USE_TORCH", "1")


def _build_pipeline(
    *,
    keep_images: bool,
    keep_tables: bool,
    keep_formulas: bool,
    ocr_mode: str,
    images_scale: float = 2.0,
):
    from docling.datamodel.pipeline_options import (
        AcceleratorDevice,
        AcceleratorOptions,
        PdfPipelineOptions,
        TableFormerMode,
        TableStructureOptions,
    )

    pipeline = PdfPipelineOptions()

    artifacts = _artifacts_dir()
    if artifacts.exists():
        pipeline.artifacts_path = artifacts

    # OCR：自动/禁用都先关；仅「强制 OCR」开启（文字层 PDF 开 OCR 极慢）
    pipeline.do_ocr = ocr_mode == "force"

    # 表格：需要时用 FAST 模式
    pipeline.do_table_structure = keep_tables
    if keep_tables:
        pipeline.table_structure_options = TableStructureOptions(
            mode=TableFormerMode.FAST
        )

    # 公式：开启后会跑 CodeFormula 模型，把公式图转成 LaTeX；关闭则留下 placeholder
    pipeline.do_formula_enrichment = bool(keep_formulas)
    pipeline.do_code_enrichment = False
    pipeline.do_picture_classification = False
    pipeline.do_picture_description = False
    if hasattr(pipeline, "do_chart_extraction"):
        pipeline.do_chart_extraction = False

    # 标题层级：用字号/字体粗细推断 heading level（不直接恢复正文粗体，但有助于结构）
    try:
        pipeline.heading_hierarchy_options.enabled = True
    except Exception:
        pass

    # 图片：scale 越大越清晰，也越慢（1=快速，2=标准，3=高清）
    scale = max(1.0, min(3.0, float(images_scale)))
    pipeline.generate_page_images = False
    pipeline.generate_picture_images = keep_images
    pipeline.images_scale = scale

    # 加速器：有 CUDA 用 GPU，否则拉满 CPU 线程
    threads = min(16, max(4, (os.cpu_count() or 8)))
    try:
        import torch

        use_cuda = bool(torch.cuda.is_available())
    except Exception:
        use_cuda = False

    pipeline.accelerator_options = AcceleratorOptions(
        num_threads=threads,
        device=AcceleratorDevice.CUDA if use_cuda else AcceleratorDevice.CPU,
    )
    return pipeline, use_cuda, threads


def _get_converter(
    *,
    keep_images: bool,
    keep_tables: bool,
    keep_formulas: bool,
    ocr_mode: str,
    images_scale: float = 2.0,
):
    from docling.datamodel.base_models import InputFormat
    from docling.document_converter import DocumentConverter, PdfFormatOption

    key = (
        keep_images,
        keep_tables,
        keep_formulas,
        ocr_mode,
        float(images_scale),
        str(_artifacts_dir()),
    )
    cached = _converter_cache.get(key)
    if cached is not None:
        return cached, None, None

    pipeline, use_cuda, threads = _build_pipeline(
        keep_images=keep_images,
        keep_tables=keep_tables,
        keep_formulas=keep_formulas,
        ocr_mode=ocr_mode,
        images_scale=images_scale,
    )
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline),
        }
    )
    _converter_cache[key] = converter
    return converter, use_cuda, threads


def _rewrite_image_paths(md_text: str, md_path: Path, *, relative: bool) -> str:
    """把 Markdown 图片链接改成相对或绝对路径。"""
    import re

    md_dir = md_path.parent.resolve()
    pattern = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")

    def repl(m: re.Match[str]) -> str:
        alt, raw = m.group(1), m.group(2).strip().strip('"').strip("'")
        # 忽略 data URI / http(s)
        if raw.startswith(("http://", "https://", "data:")):
            return m.group(0)
        try:
            p = Path(raw)
            if not p.is_absolute():
                p = (md_dir / p).resolve()
            else:
                p = p.resolve()
        except Exception:
            return m.group(0)

        if relative:
            try:
                rel = os.path.relpath(p, md_dir)
            except ValueError:
                rel = str(p)
            # Markdown 通用正斜杠
            link = rel.replace("\\", "/")
        else:
            link = str(p)
        return f"![{alt}]({link})"

    return pattern.sub(repl, md_text)


def _export_markdown(
    result,
    md_path: Path,
    keep_images: bool,
    *,
    image_path_mode: str = "relative",
) -> None:
    """仅导出解析器原始 Markdown，不做智能修复。"""
    images_dir = md_path.parent / "images"
    text: str | None = None
    if keep_images:
        images_dir.mkdir(parents=True, exist_ok=True)
        try:
            from docling_core.types.doc import ImageRefMode

            result.document.save_as_markdown(
                md_path,
                image_mode=ImageRefMode.REFERENCED,
                artifacts_dir=images_dir,
            )
            text = md_path.read_text(encoding="utf-8")
            text = _rewrite_image_paths(
                text,
                md_path,
                relative=(image_path_mode != "absolute"),
            )
        except Exception:
            text = None
    if text is None:
        text = result.document.export_to_markdown()
    md_path.write_text(text, encoding="utf-8")


def convert_pdf(
    pdf_path: Path,
    out_dir: Path,
    *,
    keep_images: bool = True,
    keep_tables: bool = True,
    keep_formulas: bool = True,
    ocr_mode: str = "auto",
    images_scale: float = 2.0,
    image_path_mode: str = "relative",
    progress: ProgressCB | None = None,
):
    """将 PDF 转为原始 Markdown，返回 ConversionResult。"""
    from app.engines.base import ConversionResult

    _ensure_runtime_env()

    def emit(msg: str) -> None:
        if progress:
            progress(msg)

    out_dir.mkdir(parents=True, exist_ok=True)
    emit("正在加载 Docling...")

    converter, use_cuda, threads = _get_converter(
        keep_images=keep_images,
        keep_tables=keep_tables,
        keep_formulas=keep_formulas,
        ocr_mode=ocr_mode,
        images_scale=images_scale,
    )
    if use_cuda is not None:
        device = "CUDA GPU" if use_cuda else f"CPU ({threads} threads)"
        emit(f"加速设备：{device}")
    emit("公式识别：" + ("开启" if keep_formulas else "关闭"))
    if keep_images:
        emit(f"图片质量：scale={float(images_scale):.1f}")
        emit(
            "图片路径："
            + ("相对路径" if image_path_mode != "absolute" else "绝对路径")
        )

    emit("正在解析 PDF...")
    t0 = time.time()
    try:
        result = converter.convert(str(pdf_path))
    except Exception as e:
        msg = str(e)
        if keep_tables and (
            "huggingface" in msg.lower()
            or "LocalEntryNotFoundError" in type(e).__name__
            or "FileMetadataError" in type(e).__name__
            or "Hub" in msg
        ):
            emit(f"表格模型不可用，改为无表格模式重试：{e}")
            _converter_cache.clear()
            converter, _, _ = _get_converter(
                keep_images=keep_images,
                keep_tables=False,
                keep_formulas=keep_formulas,
                ocr_mode=ocr_mode,
                images_scale=images_scale,
            )
            result = converter.convert(str(pdf_path))
        else:
            raise

    emit("正在生成原始 Markdown...")
    raw_path = out_dir / f"{pdf_path.stem}.raw.md"
    _export_markdown(
        result,
        raw_path,
        keep_images,
        image_path_mode=image_path_mode,
    )

    try:
        text = raw_path.read_text(encoding="utf-8")
        n = text.count("<!-- formula-not-decoded -->")
        if n:
            emit(f"警告：仍有 {n} 处公式未解码（formula-not-decoded）")
    except Exception:
        pass

    artifacts = out_dir / "images"
    elapsed = time.time() - t0
    emit(f"解析完成，耗时 {elapsed:.1f}s → {raw_path.name}")
    return ConversionResult(
        markdown_path=raw_path,
        parser="docling",
        artifacts_dir=artifacts if artifacts.exists() else None,
        metadata={
            "elapsed_sec": elapsed,
            "keep_formulas": keep_formulas,
            "images_scale": images_scale,
        },
    )
