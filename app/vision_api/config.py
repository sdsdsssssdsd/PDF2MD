"""兼容层：VisionApiConfig = DeepSeekApiConfig。"""
from app.deepseek_api.config import (
    DEFAULT_API_BASE,
    DEFAULT_MAX_CONCURRENT,
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_MODEL,
    DEFAULT_STRICT_TEXT_MODEL,
    DEFAULT_TEXT_MODEL,
    DEFAULT_TIMEOUT_S,
    DEFAULT_VISION_MODEL,
    DeepSeekApiConfig,
    VisionApiConfig,
)

__all__ = [
    "DEFAULT_API_BASE",
    "DEFAULT_MAX_CONCURRENT",
    "DEFAULT_MAX_OUTPUT_TOKENS",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_MODEL",
    "DEFAULT_STRICT_TEXT_MODEL",
    "DEFAULT_TEXT_MODEL",
    "DEFAULT_TIMEOUT_S",
    "DEFAULT_VISION_MODEL",
    "DeepSeekApiConfig",
    "VisionApiConfig",
]
