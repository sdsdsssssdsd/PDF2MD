"""新对话 / 识图模式状态校验（P3）。"""
from __future__ import annotations

from typing import Callable

_COUNT_ASSISTANT_JS = """
() => {
  let n = 0;
  for (const el of document.querySelectorAll(
    '[data-message-author-role="assistant"], .ds-message, .markdown-body'
  )) {
    const t = (el.innerText || '').trim();
    if (t.length > 80) n += 1;
  }
  return n;
}
"""


def verify_new_chat_clean(
    page,
    *,
    log: Callable[[str], None] | None = None,
) -> tuple[bool, str]:
    """新对话后不应仍有长 assistant 历史（软校验）。"""
    try:
        n = int(page.evaluate(_COUNT_ASSISTANT_JS))
    except Exception:
        return True, ""
    if n > 0:
        msg = f"新对话后仍有 {n} 条 assistant 回答（可能未清空）"
        if log:
            log(f"[NewChatGuard] 警告: {msg}")
        return False, msg
    if log:
        log("[NewChatGuard] 对话区干净 ✓")
    return True, ""


def verify_vision_mode_active(
    page,
    *,
    log: Callable[[str], None] | None = None,
) -> tuple[bool, str]:
    from app.vision_transcribe.browser.dom_replay import is_vision_mode_active

    if is_vision_mode_active(page):
        if log:
            log("[VisionModeGuard] 识图模式已激活 ✓")
        return True, ""
    msg = "识图模式未激活"
    if log:
        log(f"[VisionModeGuard] {msg}")
    return False, msg
