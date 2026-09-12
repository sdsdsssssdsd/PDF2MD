"""DeepSeek Vision API 配置（非敏感项来自 QSettings）。"""
from __future__ import annotations

from dataclasses import dataclass

from app.dialogs.settings_dialog import settings


DEFAULT_API_BASE = "https://api.deepseek.com"
DEFAULT_TEXT_MODEL = "deepseek-v4-flash"
DEFAULT_STRICT_TEXT_MODEL = "deepseek-v4-pro"
DEFAULT_VISION_MODEL = "deepseek-v4-flash-vision-exp"
DEFAULT_TIMEOUT_S = 300
DEFAULT_MAX_RETRIES = 4
DEFAULT_MAX_CONCURRENT = 2
DEFAULT_MAX_OUTPUT_TOKENS = 16384


@dataclass
class VisionApiConfig:
    api_base: str = DEFAULT_API_BASE
    model: str = DEFAULT_VISION_MODEL
    transport: str = "auto"  # auto | base64 | file_id
    detail: str = "original"  # low | high | original
    timeout_s: int = DEFAULT_TIMEOUT_S
    max_retries: int = DEFAULT_MAX_RETRIES
    max_concurrent: int = DEFAULT_MAX_CONCURRENT
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    auto_retry: bool = True

    @classmethod
    def from_settings(cls) -> VisionApiConfig:
        s = settings()
        return cls(
            api_base=str(s.value("deepseek_api_base", DEFAULT_API_BASE) or DEFAULT_API_BASE).rstrip("/"),
            model=str(s.value("deepseek_vision_model", DEFAULT_VISION_MODEL) or DEFAULT_VISION_MODEL),
            transport=str(s.value("deepseek_api_transport", "auto") or "auto"),
            detail=str(s.value("deepseek_api_detail", "original") or "original"),
            timeout_s=int(s.value("deepseek_api_timeout", DEFAULT_TIMEOUT_S) or DEFAULT_TIMEOUT_S),
            max_retries=int(s.value("deepseek_api_max_retries", DEFAULT_MAX_RETRIES) or DEFAULT_MAX_RETRIES),
            max_concurrent=int(
                s.value("deepseek_api_max_concurrent", DEFAULT_MAX_CONCURRENT) or DEFAULT_MAX_CONCURRENT
            ),
            auto_retry=bool(s.value("deepseek_api_auto_retry", True, type=bool)),
            max_output_tokens=int(
                s.value("deepseek_api_max_output_tokens", DEFAULT_MAX_OUTPUT_TOKENS)
                or DEFAULT_MAX_OUTPUT_TOKENS
            ),
        )

    def chat_completion_urls(self) -> list[str]:
        """OpenAI 兼容 /v1 与官方 curl 直链 /chat/completions 均尝试。"""
        base = self.api_base.rstrip("/")
        if base.endswith("/v1"):
            return [f"{base}/chat/completions"]
        return [f"{base}/v1/chat/completions", f"{base}/chat/completions"]

    @property
    def chat_completions_url(self) -> str:
        return self.chat_completion_urls()[0]

    @property
    def files_url(self) -> str:
        base = self.api_base.rstrip("/")
        if base.endswith("/v1"):
            return f"{base}/files"
        return f"{base}/v1/files"
