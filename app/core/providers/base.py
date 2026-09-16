"""Provider 协议。具体模型只实现接口，不进入 JobRunner。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from app.engines.base import ConversionResult


class ParserProvider(Protocol):
    name: str

    def available(self) -> bool: ...

    def convert_pdf(self, pdf_path: Path, out_dir: Path, **kwargs: Any) -> ConversionResult: ...


class FormulaProvider(Protocol):
    name: str

    def available(self) -> bool: ...


class VisionProvider(Protocol):
    name: str

    def available(self) -> bool: ...
