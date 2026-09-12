"""DeepSeek API Key：环境变量优先，Windows 可选 keyring。"""
from __future__ import annotations

import os

SERVICE = "PDF2MD"
USER = "deepseek_api_key"


def get_api_key() -> str:
    env = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if env:
        return env
    try:
        import keyring

        val = keyring.get_password(SERVICE, USER)
        return (val or "").strip()
    except Exception:
        return ""


def set_api_key(value: str) -> None:
    text = (value or "").strip()
    try:
        import keyring

        if text:
            keyring.set_password(SERVICE, USER, text)
        else:
            try:
                keyring.delete_password(SERVICE, USER)
            except Exception:
                pass
    except Exception:
        pass


def api_key_configured() -> bool:
    return bool(get_api_key())
