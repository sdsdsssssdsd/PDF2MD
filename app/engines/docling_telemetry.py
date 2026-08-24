"""Phase 5D：Docling 转换器复用与一级计时遥测。"""
from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class DoclingTelemetry:
    converter_create_count: int = 0
    converter_reuse_count: int = 0
    last_converter_reused: bool = False
    last_converter_key: str = ""
    last_init_seconds: float = 0.0
    last_convert_seconds: float = 0.0
    last_export_seconds: float = 0.0
    last_total_seconds: float = 0.0
    # 差分估算（仅 A/B / profile 填充）
    est_formula_enrich_seconds: float | None = None
    est_table_seconds: float | None = None
    est_picture_seconds: float | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_LOCK = threading.Lock()
_TELEM = DoclingTelemetry()


def get_docling_telemetry() -> DoclingTelemetry:
    return _TELEM


def reset_docling_telemetry() -> None:
    global _TELEM
    with _LOCK:
        _TELEM = DoclingTelemetry()


def record_converter_access(*, created: bool, key: str, init_seconds: float = 0.0) -> None:
    with _LOCK:
        if created:
            _TELEM.converter_create_count += 1
            _TELEM.last_converter_reused = False
        else:
            _TELEM.converter_reuse_count += 1
            _TELEM.last_converter_reused = True
        _TELEM.last_converter_key = key
        if created:
            _TELEM.last_init_seconds = float(init_seconds)


def record_convert_phases(
    *,
    init_seconds: float,
    convert_seconds: float,
    export_seconds: float,
) -> dict[str, Any]:
    with _LOCK:
        _TELEM.last_init_seconds = float(init_seconds)
        _TELEM.last_convert_seconds = float(convert_seconds)
        _TELEM.last_export_seconds = float(export_seconds)
        _TELEM.last_total_seconds = float(init_seconds + convert_seconds + export_seconds)
        return {
            "converter_create_count": _TELEM.converter_create_count,
            "converter_reuse_count": _TELEM.converter_reuse_count,
            "converter_reused": _TELEM.last_converter_reused,
            "converter_key": _TELEM.last_converter_key,
            "docling_init_seconds": round(_TELEM.last_init_seconds, 3),
            "docling_convert_seconds": round(_TELEM.last_convert_seconds, 3),
            "docling_export_seconds": round(_TELEM.last_export_seconds, 3),
            "docling_total_seconds": round(_TELEM.last_total_seconds, 3),
        }
