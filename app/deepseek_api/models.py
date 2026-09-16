"""DeepSeek API 请求/响应模型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ImagePayload:
    path: Path
    mime: str
    data_url: str = ""
    file_id: str = ""


@dataclass
class ChatResult:
    text: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    request_id: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    finish_reason: str = ""
    task_profile: str = ""
    thinking: str = "disabled"
    transport: str = ""
    semantic_retry_count: int = 0
    transport_retry_count: int = 0
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def markdown(self) -> str:
        return self.text


@dataclass
class TranscribeResult:
    """兼容旧 Vision 调用。"""

    markdown: str
    request_id: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    finish_reason: str = ""
    task_profile: str = ""
    thinking: str = "disabled"
    transport: str = ""
    semantic_retry_count: int = 0
    transport_retry_count: int = 0
    raw: dict[str, Any] = field(default_factory=dict, repr=False)
