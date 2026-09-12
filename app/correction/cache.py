"""Correction API 审校结果缓存。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.utils.paths import APP_ROOT

_CACHE_DIR = APP_ROOT / ".cache" / "correction"
_PROMPT_VERSION = "k10-v1"


def _cache_key(
    *,
    fragment: str,
    issue_type: str,
    model: str,
) -> str:
    raw = f"{_PROMPT_VERSION}|{issue_type}|{model}|{fragment}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def cache_get(
    *,
    fragment: str,
    issue_type: str,
    model: str,
) -> dict | None:
    key = _cache_key(fragment=fragment, issue_type=issue_type, model=model)
    path = _CACHE_DIR / f"{key}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def cache_set(
    *,
    fragment: str,
    issue_type: str,
    model: str,
    payload: dict,
) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = _cache_key(fragment=fragment, issue_type=issue_type, model=model)
    path = _CACHE_DIR / f"{key}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
