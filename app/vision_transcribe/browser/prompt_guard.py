"""Prompt 填写后精确校验（P3）。"""
from __future__ import annotations

import hashlib
from typing import Callable

from app.vision_transcribe.browser.dom_locator import _read_composer_text


def prompt_fingerprint(text: str) -> dict[str, int | str]:
    t = (text or "").strip()
    n = len(t)
    head = min(48, n)
    tail = min(48, n)
    return {
        "len": n,
        "prefix": t[:head],
        "suffix": t[-tail:] if tail else "",
        "hash": hashlib.sha256(t.encode("utf-8")).hexdigest()[:16],
    }


def verify_prompt_exact(
    page,
    expected: str,
    *,
    log: Callable[[str], None] | None = None,
) -> tuple[bool, str]:
    """发送前校验：长度、首尾片段一致。"""
    exp = (expected or "").strip()
    if not exp:
        return True, ""
    actual = (_read_composer_text(page) or "").strip()
    if not actual:
        return False, "输入框为空"

    fp_e = prompt_fingerprint(exp)
    fp_a = prompt_fingerprint(actual)

    if fp_a["len"] < int(fp_e["len"]) * 0.95:
        msg = f"Prompt 长度不足（{fp_a['len']} < {fp_e['len']}）"
        if log:
            log(f"[PromptGuard] {msg}")
        return False, msg

    if fp_e["prefix"] and not actual.startswith(str(fp_e["prefix"])):
        msg = "Prompt 前缀不一致"
        if log:
            log(f"[PromptGuard] {msg}")
        return False, msg

    if fp_e["suffix"] and not actual.endswith(str(fp_e["suffix"])):
        msg = "Prompt 后缀不一致"
        if log:
            log(f"[PromptGuard] {msg}")
        return False, msg

    if log:
        log(
            f"[PromptGuard] 通过（{fp_a['len']} 字，hash={fp_a['hash']}）"
        )
    return True, ""
