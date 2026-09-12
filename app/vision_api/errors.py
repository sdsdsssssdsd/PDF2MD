"""DeepSeek Vision API 错误分类。"""
from __future__ import annotations


class VisionApiError(RuntimeError):
    """API 调用基类。"""

    retryable: bool = False


class AuthenticationError(VisionApiError):
    retryable = False


class RateLimitError(VisionApiError):
    retryable = True


class RequestTooLargeError(VisionApiError):
    retryable = True


class UnsupportedImageError(VisionApiError):
    retryable = False


class VisionModelError(VisionApiError):
    retryable = True


class NetworkError(VisionApiError):
    retryable = True


class ResponseValidationError(VisionApiError):
    retryable = True
