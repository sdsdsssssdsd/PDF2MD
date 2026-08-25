"""上传附件数量校验（P3）与「服务器繁忙」限流检测。"""
from __future__ import annotations

import time
from typing import Callable

from app.vision_transcribe.browser.base import ServerBusyCooldownError

_COUNT_ATTACHMENTS_JS = """
() => {
  const vh = window.innerHeight;
  const minTop = vh * 0.32;
  let badgeExtra = 0;
  let imgCount = 0;
  const seen = new Set();

  // 堆叠角标：+9、10张 等
  for (const el of document.querySelectorAll('span, div, p')) {
    const r = el.getBoundingClientRect();
    if (r.top < minTop || r.width < 6 || r.height < 6) continue;
    const t = (el.innerText || '').replace(/\\s+/g, '').trim();
    if (!t || t.length > 12) continue;
    let m = t.match(/^\\+(\\d{1,3})$/);
    if (m) {
      badgeExtra = Math.max(badgeExtra, parseInt(m[1], 10));
      continue;
    }
    m = t.match(/^(\\d{1,3})张$/);
    if (m) {
      badgeExtra = Math.max(badgeExtra, parseInt(m[1], 10) - 1);
    }
  }

  const nodes = document.querySelectorAll(
    'img, [class*="attachment"], [class*="file"], [class*="thumbnail"]'
  );
  for (const el of nodes) {
    const r = el.getBoundingClientRect();
    if (r.width < 18 || r.height < 18) continue;
    if (r.top < minTop) continue;
    const src = (el.src || el.getAttribute('src') || '').trim();
    const key = src || (
      Math.round(r.left) + ':' + Math.round(r.top) + ':' +
      Math.round(r.width) + 'x' + Math.round(r.height)
    );
    if (seen.has(key)) continue;
    seen.add(key);
    imgCount += 1;
  }

  if (badgeExtra > 0) {
    return Math.max(imgCount, 1 + badgeExtra);
  }
  return imgCount;
}
"""

_DETECT_SERVER_BUSY_JS = """
() => {
  const vh = window.innerHeight;
  const minTop = vh * 0.22;
  const needles = ['服务器繁忙', '服务繁忙', 'Server busy', 'server busy', 'Server Busy'];
  const hits = [];
  const nodes = document.querySelectorAll(
    'span, div, p, img, button, [class*="attachment"], [class*="thumbnail"], [class*="upload"]'
  );
  for (const el of nodes) {
    const r = el.getBoundingClientRect();
    if (r.width < 4 || r.height < 4) continue;
    if (r.top < minTop) continue;
    const parts = [
      el.innerText,
      el.alt,
      el.title,
      el.getAttribute('aria-label'),
    ];
    for (const raw of parts) {
      if (!raw) continue;
      const t = String(raw).trim();
      if (!t || t.length > 120) continue;
      for (const n of needles) {
        if (t.includes(n)) {
          hits.push(t.slice(0, 80));
          break;
        }
      }
    }
  }
  if (hits.length) {
    return { busy: true, sample: hits[0], count: hits.length };
  }
  return { busy: false, sample: '', count: 0 };
}
"""


def count_composer_attachments(page) -> int:
    try:
        n = page.evaluate(_COUNT_ATTACHMENTS_JS)
        return max(0, int(n))
    except Exception:
        return -1


def detect_upload_server_busy(
    page,
    *,
    config: dict | None = None,
    log: Callable[[str], None] | None = None,
) -> tuple[bool, str]:
    """输入区附件缩略图是否显示「服务器繁忙」（账户级限流）。"""
    try:
        raw = page.evaluate(_DETECT_SERVER_BUSY_JS)
    except Exception:
        raw = None
    if isinstance(raw, dict) and raw.get("busy"):
        sample = str(raw.get("sample") or "").strip()
        count = int(raw.get("count") or 1)
        if count > 1:
            return True, f"{sample}（{count} 处）"
        return True, sample or "DOM"

    try:
        from app.vision_transcribe.browser.deepseek_ui import (
            is_upload_server_busy_template_visible,
        )

        busy2, hint2 = is_upload_server_busy_template_visible(
            page, config=config, log=log
        )
        if busy2:
            return True, hint2 or "图识别"
    except Exception:
        pass
    return False, ""


def raise_if_upload_server_busy(
    page,
    *,
    log: Callable[[str], None] | None = None,
    cooldown_seconds: int = 600,
    config: dict | None = None,
) -> None:
    """命中限流则抛出 ServerBusyCooldownError（勿继续发送/重试刷屏）。"""
    busy, hint = detect_upload_server_busy(page, config=config, log=log)
    if not busy:
        return
    wait_min = max(1, int(cooldown_seconds) // 60)
    msg = (
        f"DeepSeek 附件「服务器繁忙」（账户级限流，刷新无效），"
        f"需等待约 {wait_min} 分钟后重试"
    )
    if hint:
        msg += f"：{hint}"
    if log:
        log(f"[UploadGuard] {msg}")
    raise ServerBusyCooldownError(msg, cooldown_seconds=int(cooldown_seconds))


def _send_is_ready(page) -> bool:
    try:
        from app.vision_transcribe.browser.dom_locator import is_send_button_ready

        return bool(is_send_button_ready(page))
    except Exception:
        return False


def verify_upload_complete(
    page,
    expected: int,
    *,
    log: Callable[[str], None] | None = None,
    timeout_ms: int = 30_000,
    poll_ms: int = 400,
    send_ready: bool = False,
    cooldown_seconds: int = 600,
) -> tuple[bool, str]:
    """上传后确认附件数量（启发式）；不足时返回 UPLOAD_INCOMPLETE。

    DeepSeek 识图模式常把多图堆成 1 个缩略图 +「+N」角标，不可强求数满 N 个 img。
    若 ``send_ready``（发送键已变蓝）且至少见到 1 个附件或角标，则信任上传完成。
    """
    expected = max(1, int(expected))
    deadline = time.monotonic() + timeout_ms / 1000.0
    last = -1
    while time.monotonic() < deadline:
        raise_if_upload_server_busy(
            page, log=log, cooldown_seconds=cooldown_seconds
        )
        n = count_composer_attachments(page)
        last = n
        ready = send_ready or _send_is_ready(page)
        if n >= expected:
            if log:
                log(f"[UploadGuard] 附件 {n}/{expected} ✓")
            return True, ""
        if n >= expected - 1 and expected >= 3:
            if log:
                log(f"[UploadGuard] 附件 {n}/{expected}（差 1，放宽通过）")
            return True, ""
        if ready and n >= 1 and expected >= 2:
            if log:
                log(
                    f"[UploadGuard] 附件 {n}/{expected}（堆叠展示 + 发送已就绪 ✓）"
                )
            return True, ""
        if ready and n == 0 and expected >= 2:
            # 发送已蓝但缩略图未渲染：短等一轮
            time.sleep(min(0.8, poll_ms / 1000.0))
            raise_if_upload_server_busy(
                page, log=log, cooldown_seconds=cooldown_seconds
            )
            n2 = count_composer_attachments(page)
            last = n2
            if n2 >= 1:
                if log:
                    log(
                        f"[UploadGuard] 附件 {n2}/{expected}（延迟出现 + 发送已就绪 ✓）"
                    )
                return True, ""
        time.sleep(poll_ms / 1000.0)

    raise_if_upload_server_busy(page, log=log, cooldown_seconds=cooldown_seconds)

    ready = send_ready or _send_is_ready(page)
    if last < 0:
        if ready:
            msg = "无法数附件，但发送已就绪（放宽通过）"
            if log:
                log(f"[UploadGuard] {msg}")
            return True, msg
        msg = "无法检测附件数量（跳过硬失败）"
        if log:
            log(f"[UploadGuard] {msg}")
        return True, msg

    if last == 0:
        if ready and expected >= 2:
            msg = "未见到缩略图，但发送已就绪（信任 set_input_files）"
            if log:
                log(f"[UploadGuard] {msg}")
            return True, msg
        msg = f"未检测到附件（期望 {expected}）"
        if log:
            log(f"[UploadGuard] {msg}")
        return False, msg

    if ready and expected >= 2:
        if log:
            log(
                f"[UploadGuard] 附件 {last}/{expected}（堆叠/延迟 + 发送已就绪 ✓）"
            )
        return True, ""

    if last < expected // 2 and expected >= 4:
        msg = f"附件过少（{last}/{expected}）"
        if log:
            log(f"[UploadGuard] {msg}")
        return False, msg

    if log:
        log(f"[UploadGuard] 附件 {last}/{expected}（未达精确值，继续）")
    return True, ""
