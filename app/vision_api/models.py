"""Vision API 请求/响应模型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TranscribeResult:
    markdown: str
    request_id: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class ImagePayload:
    path: Path
    mime: str
    data_url: str = ""
    file_id: str = ""
