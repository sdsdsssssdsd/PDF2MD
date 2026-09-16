"""DeepSeek API 唯一配置：生产模型固定为 deepseek-flash。不依赖 GUI。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable

DEFAULT_API_BASE = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-flash"
DEFAULT_MODEL_FAMILY = "DeepSeek-V4.1-Flash"
DEFAULT_TIMEOUT_S = 300
DEFAULT_MAX_RETRIES = 4
DEFAULT_MAX_CONCURRENT = 2
DEFAULT_MAX_OUTPUT_TOKENS = 16384

# 兼容别名：业务代码不要再用这些名字选模型
DEFAULT_TEXT_MODEL = DEFAULT_MODEL
DEFAULT_STRICT_TEXT_MODEL = DEFAULT_MODEL
DEFAULT_VISION_MODEL = DEFAULT_MODEL

SETTINGS_ORG = "PDF2MD"
SETTINGS_APP = "PDF2MD"

LEGACY_MODEL_ALIASES = {
    "deepseek-v4-flash": DEFAULT_MODEL,
    "deepseek-v4-pro": DEFAULT_MODEL,
    "deepseek-v4-flash-vision-exp": DEFAULT_MODEL,
    "deepseek-chat": DEFAULT_MODEL,
    "deepseek-reasoner": DEFAULT_MODEL,
}


def migrate_legacy_model_name(name: str | None) -> str:
    raw = (name or "").strip()
    if not raw:
        return DEFAULT_MODEL
    mapped = LEGACY_MODEL_ALIASES.get(raw) or LEGACY_MODEL_ALIASES.get(raw.lower())
    return mapped or raw


SettingsLoader = Callable[[], dict]

_settings_loader: SettingsLoader | None = None


def set_settings_loader(loader: SettingsLoader | None) -> None:
    """由 GUI 注册。Core / 测试不直接读桌面设置。"""
    global _settings_loader
    _settings_loader = loader


def migrate_qsettings(settings) -> None:
    """把旧模型键迁到 deepseek_model。旧键保留一个版本但不参与调用。"""
    if settings is None:
        return
    try:
        if bool(settings.value("deepseek_model_migrated_v41", False, type=bool)):
            current = migrate_legacy_model_name(str(settings.value("deepseek_model", "") or ""))
            if current:
                settings.setValue("deepseek_model", current)
            return
    except TypeError:
        flag = str(settings.value("deepseek_model_migrated_v41", "") or "").lower()
        if flag in {"true", "1"}:
            current = migrate_legacy_model_name(str(settings.value("deepseek_model", "") or ""))
            if current:
                settings.setValue("deepseek_model", current)
            return

    candidates = [
        settings.value("deepseek_model", ""),
        settings.value("deepseek_vision_model", ""),
        settings.value("correction_text_model", ""),
        settings.value("correction_strict_model", ""),
        settings.value("correction_vision_model", ""),
    ]
    chosen = DEFAULT_MODEL
    for item in candidates:
        text = str(item or "").strip()
        if text:
            chosen = migrate_legacy_model_name(text)
            break
    settings.setValue("deepseek_model", chosen)
    settings.setValue("deepseek_model_migrated_v41", True)


@dataclass
class DeepSeekApiConfig:
    api_base: str = DEFAULT_API_BASE
    model: str = DEFAULT_MODEL
    timeout_s: int = DEFAULT_TIMEOUT_S
    max_retries: int = DEFAULT_MAX_RETRIES
    auto_retry: bool = True
    transport: str = "auto"  # auto | base64 | file_id
    detail: str = "original"  # low | high | original
    max_concurrent: int = DEFAULT_MAX_CONCURRENT
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    compatibility_mode: bool = False
    thinking: str = "disabled"

    @classmethod
    def from_mapping(cls, values: dict | None = None) -> DeepSeekApiConfig:
        raw = dict(values or {})
        env_model = (os.environ.get("PDF2MD_DEEPSEEK_MODEL") or "").strip()
        env_base = (os.environ.get("PDF2MD_DEEPSEEK_API_BASE") or "").strip()
        model = migrate_legacy_model_name(str(raw.get("model") or env_model or DEFAULT_MODEL))
        api_base = str(raw.get("api_base") or env_base or DEFAULT_API_BASE).rstrip("/")
        return cls(
            api_base=api_base or DEFAULT_API_BASE,
            model=model or DEFAULT_MODEL,
            timeout_s=int(raw.get("timeout_s") or DEFAULT_TIMEOUT_S),
            max_retries=int(raw.get("max_retries") or DEFAULT_MAX_RETRIES),
            auto_retry=bool(raw.get("auto_retry", True)),
            transport=str(raw.get("transport") or "auto"),
            detail=str(raw.get("detail") or "original"),
            max_concurrent=int(raw.get("max_concurrent") or DEFAULT_MAX_CONCURRENT),
            max_output_tokens=int(raw.get("max_output_tokens") or DEFAULT_MAX_OUTPUT_TOKENS),
            compatibility_mode=bool(raw.get("compatibility_mode", False)),
            thinking=str(raw.get("thinking") or "disabled"),
        )

    @classmethod
    def from_settings(cls) -> DeepSeekApiConfig:
        values = _settings_loader() if _settings_loader else {}
        return cls.from_mapping(values or {})

    def chat_completion_urls(self) -> list[str]:
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


# 兼容旧类型名
VisionApiConfig = DeepSeekApiConfig
