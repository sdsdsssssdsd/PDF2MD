"""兼容层：DeepSeekVisionClient = DeepSeekClient。"""
from app.deepseek_api.client import (
    DeepSeekClient,
    DeepSeekVisionClient,
    build_message_content,
    empty_content_hint,
    extract_assistant_text,
    normalize_detail,
)

__all__ = [
    "DeepSeekClient",
    "DeepSeekVisionClient",
    "build_message_content",
    "empty_content_hint",
    "extract_assistant_text",
    "normalize_detail",
]
