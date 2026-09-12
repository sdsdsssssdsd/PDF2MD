"""DeepSeek 公共异常兼容层。"""
from app.vision_api.errors import (
    AuthenticationError,
    NetworkError,
    RateLimitError,
    RequestTooLargeError,
    ResponseValidationError,
    UnsupportedImageError,
    VisionApiError,
    VisionModelError,
)

__all__ = [
    "AuthenticationError",
    "NetworkError",
    "RateLimitError",
    "RequestTooLargeError",
    "ResponseValidationError",
    "UnsupportedImageError",
    "VisionApiError",
    "VisionModelError",
]
