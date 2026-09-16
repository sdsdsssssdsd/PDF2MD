"""Parser providers：包装现有 Docling / MinerU，不改算法。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from app.engines.base import ConversionResult
from app.task_model import EngineChoice

ProgressCB = Callable[[str], None]


class DoclingParserProvider:
    name = "docling"

    def available(self) -> bool:
        try:
            import docling  # noqa: F401

            return True
        except Exception:
            return False

    def convert_pdf(self, pdf_path: Path, out_dir: Path, **kwargs: Any) -> ConversionResult:
        from app.engines import docling_engine

        return docling_engine.convert_pdf(
            pdf_path,
            out_dir,
            keep_images=kwargs.get("keep_images", True),
            keep_tables=kwargs.get("keep_tables", True),
            keep_formulas=kwargs.get("keep_formulas", True),
            ocr_mode=kwargs.get("ocr_mode", "auto"),
            images_scale=kwargs.get("images_scale", 2.0),
            image_path_mode=kwargs.get("image_path_mode", "relative"),
            progress=kwargs.get("progress"),
        )


class MineruParserProvider:
    name = "mineru"

    def available(self) -> bool:
        from app.utils.paths import MINERU_EXE, PYTHON_EXE

        return bool(MINERU_EXE or PYTHON_EXE)

    def convert_pdf(self, pdf_path: Path, out_dir: Path, **kwargs: Any) -> ConversionResult:
        from app.engines import mineru_engine

        return mineru_engine.convert_pdf(
            pdf_path,
            out_dir,
            ocr_mode=kwargs.get("ocr_mode", "auto"),
            keep_tables=kwargs.get("keep_tables", True),
            keep_formulas=kwargs.get("keep_formulas", True),
            progress=kwargs.get("progress"),
        )


class DeepSeekOCR2FormulaProvider:
    name = "deepseek_ocr2"

    def available(self) -> bool:
        try:
            from app.ocr import deepseek_worker_client  # noqa: F401

            return True
        except Exception:
            return False


class DeepSeekApiVisionProvider:
    name = "deepseek_api"

    def available(self) -> bool:
        from app.deepseek_api.key_store import api_key_configured

        return api_key_configured()


class DeepSeekWebVisionProvider:
    name = "deepseek_web"

    def available(self) -> bool:
        return True


_PARSERS = {
    "docling": DoclingParserProvider(),
    "mineru": MineruParserProvider(),
}


def get_parser(name: str) -> DoclingParserProvider | MineruParserProvider:
    key = (name or "docling").strip().lower()
    if key not in _PARSERS:
        raise KeyError(f"unknown parser: {name}")
    return _PARSERS[key]


def parse_pdf(
    *,
    engine: str,
    pdf_path: Path,
    out_dir: Path,
    ocr_mode: str = "auto",
    keep_images: bool = True,
    keep_tables: bool = True,
    keep_formulas: bool = True,
    images_scale: float = 2.0,
    image_path_mode: str = "relative",
    progress: ProgressCB | None = None,
) -> ConversionResult:
    """AUTO 时按 profiler 选择优先 parser，失败再 fallback。显式引擎不改道。"""

    def emit(msg: str) -> None:
        if progress:
            progress(msg)

    kwargs = dict(
        ocr_mode=ocr_mode,
        keep_images=keep_images,
        keep_tables=keep_tables,
        keep_formulas=keep_formulas,
        images_scale=images_scale,
        image_path_mode=image_path_mode,
        progress=progress,
    )
    if engine == EngineChoice.MINERU.value:
        return get_parser("mineru").convert_pdf(pdf_path, out_dir, **kwargs)
    if engine == EngineChoice.DOCLING.value:
        return get_parser("docling").convert_pdf(pdf_path, out_dir, **kwargs)

    from app.core.providers.descriptor import Capability, ResolveConstraints
    from app.core.providers.registry import get_registry
    from app.core.routing.router import suggest_parser

    preferred = suggest_parser(pdf_path, engine=engine)

    handles = get_registry().resolve_all(
        Capability.PARSE_STRUCTURE,
        ResolveConstraints(
            capability=Capability.PARSE_STRUCTURE,
            preferred_ids=(f"parser.{preferred}",),
        ),
    )
    names = [h.short_name for h in handles if h.short_name in _PARSERS]
    if not names:
        names = [preferred]
    last_exc: Exception | None = None
    for index, name in enumerate(names):
        try:
            if index == 0:
                emit(f"自动路由：优先 {name}")
            else:
                emit(f"{names[index - 1]} 失败，切换 {name}：{last_exc}")
            return get_parser(name).convert_pdf(pdf_path, out_dir, **kwargs)
        except Exception as exc:
            last_exc = exc
    if last_exc is not None:
        raise last_exc
    return get_parser(preferred).convert_pdf(pdf_path, out_dir, **kwargs)
