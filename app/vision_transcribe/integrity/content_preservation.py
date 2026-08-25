"""Cleaner 前后内容守恒 Gate（P4 轻量）。"""
from __future__ import annotations

import re

_ALNUM = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


def _alnum_tokens(text: str) -> int:
    return sum(len(m.group(0)) for m in _ALNUM.finditer(text or ""))


def content_preservation_check(
    raw: str,
    cleaned: str,
    *,
    max_drop_ratio: float = 0.12,
) -> tuple[bool, str, dict]:
    """返回 (ok, message, stats)。仅比较字母数字/中文 token 总量。"""
    raw_n = _alnum_tokens(raw)
    clean_n = _alnum_tokens(cleaned)
    if raw_n <= 0:
        return True, "", {"raw_tokens": 0, "clean_tokens": clean_n, "drop_ratio": 0.0}
    drop = max(0.0, (raw_n - clean_n) / raw_n)
    stats = {
        "raw_tokens": raw_n,
        "clean_tokens": clean_n,
        "drop_ratio": round(drop, 4),
    }
    if drop > max_drop_ratio:
        return (
            False,
            f"Cleaner 后内容减少 {drop:.1%}（>{max_drop_ratio:.0%}）",
            stats,
        )
    return True, "", stats
