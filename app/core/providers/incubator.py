"""Incubator Provider：登记新 backend，默认关闭，不进 UI，不改默认 Router。

PP-Structure = table / layout / reading-order specialist。
Docling VLM = 严重页级 fallback。
Marker = optional parser，OpenRAIL-M 不能晋级为 default-eligible。
"""
from __future__ import annotations

import importlib.util
import os
from typing import Any

from app.core.domain.recovery import RecoveryPatch, RecoveryRequest
from app.core.providers.descriptor import (
    Capability,
    IsolationMode,
    ProviderDescriptor,
    ProviderType,
    RuntimeKind,
)
from app.core.providers.promotion import PromotionTrack

INCUBATOR_EXECUTE_ENV = "PDF2MD_INCUBATOR_EXECUTE"


def _has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def incubator_execute_allowed() -> bool:
    return os.environ.get(INCUBATOR_EXECUTE_ENV, "").strip() == "1"


PP_STRUCTURE = ProviderDescriptor(
    id="table.pp_structure",
    version="0.1",
    provider_type=ProviderType.TABLE,
    capabilities=(
        Capability.TABLE_STRUCTURE,
        Capability.LAYOUT_DETECTION,
        Capability.READING_ORDER,
    ),
    runtime=(RuntimeKind.CPU, RuntimeKind.CUDA),
    dependencies=("paddleocr",),
    isolation_mode=IsolationMode.SUBPROCESS,
    license_class="apache-2.0",
    experimental=True,
    default_enabled=False,
    source="incubator",
    track=PromotionTrack.EXPERIMENTAL,
)

DOCLING_VLM = ProviderDescriptor(
    id="vision.docling_vlm",
    version="0.1",
    provider_type=ProviderType.VISION,
    capabilities=(Capability.VISION_PAGE,),
    runtime=(RuntimeKind.CUDA, RuntimeKind.CPU),
    dependencies=("docling",),
    isolation_mode=IsolationMode.INPROCESS,
    license_class="mit",
    experimental=True,
    default_enabled=False,
    source="incubator",
    track=PromotionTrack.EXPERIMENTAL,
)

MARKER = ProviderDescriptor(
    id="parser.marker",
    version="0.1",
    provider_type=ProviderType.PARSER,
    capabilities=(Capability.PARSE_STRUCTURE, Capability.PARSE_TEXT),
    runtime=(RuntimeKind.CUDA, RuntimeKind.CPU),
    dependencies=("marker",),
    isolation_mode=IsolationMode.INPROCESS,
    license_class="openrail-m",
    experimental=True,
    default_enabled=False,
    source="incubator",
    track=PromotionTrack.EXPERIMENTAL,
)


class IncubatorProvider:
    """默认不执行推理。显式 PDF2MD_INCUBATOR_EXECUTE=1 才允许 recover。"""

    name = ""
    descriptor: ProviderDescriptor | None = None

    def available(self) -> bool:
        return False

    def recover_blocks(self, request: RecoveryRequest, document: Any, markdown: str) -> RecoveryPatch | None:
        del request, document, markdown
        if not incubator_execute_allowed():
            return None
        return None


class PPStructureTableProvider(IncubatorProvider):
    name = "pp_structure"
    descriptor = PP_STRUCTURE

    def available(self) -> bool:
        return _has_module("paddleocr") or _has_module("paddlex")


class DoclingVlmProvider(IncubatorProvider):
    name = "docling_vlm"
    descriptor = DOCLING_VLM

    def available(self) -> bool:
        return _has_module("docling")


class MarkerIncubatorProvider(IncubatorProvider):
    name = "marker"
    descriptor = MARKER

    def available(self) -> bool:
        return _has_module("marker")
