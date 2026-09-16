"""GUI → AppConfig 桥：Core 不读 QSettings。"""
from __future__ import annotations

from typing import Any

from app.deepseek_api.config import (
    DEFAULT_API_BASE,
    DEFAULT_MAX_CONCURRENT,
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT_S,
    SETTINGS_APP,
    SETTINGS_ORG,
    migrate_qsettings,
    set_settings_loader,
)


def deepseek_qsettings_map() -> dict[str, Any]:
    try:
        from PySide6.QtCore import QSettings
    except Exception:
        return {}
    try:
        s = QSettings(SETTINGS_ORG, SETTINGS_APP)
        migrate_qsettings(s)

        def _bool(key: str, default: bool) -> bool:
            try:
                return bool(s.value(key, default, type=bool))
            except TypeError:
                return str(s.value(key, default)).lower() in {"true", "1", "yes"}

        return {
            "api_base": s.value("deepseek_api_base", DEFAULT_API_BASE),
            "model": s.value("deepseek_model", DEFAULT_MODEL),
            "transport": s.value("deepseek_api_transport", "auto"),
            "detail": s.value("deepseek_api_detail", "original"),
            "timeout_s": s.value("deepseek_api_timeout", DEFAULT_TIMEOUT_S),
            "max_retries": s.value("deepseek_api_max_retries", DEFAULT_MAX_RETRIES),
            "max_concurrent": s.value("deepseek_api_max_concurrent", DEFAULT_MAX_CONCURRENT),
            "max_output_tokens": s.value(
                "deepseek_api_max_output_tokens", DEFAULT_MAX_OUTPUT_TOKENS
            ),
            "auto_retry": _bool("deepseek_api_auto_retry", True),
            "compatibility_mode": _bool("deepseek_compatibility_mode", False),
        }
    except Exception:
        return {}


def install_deepseek_settings_loader() -> None:
    set_settings_loader(deepseek_qsettings_map)
