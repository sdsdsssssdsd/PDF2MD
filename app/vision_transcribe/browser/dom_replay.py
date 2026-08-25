"""回放用户演示录制的 DOM 步骤；填写/上传使用运行时 batch 数据。"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from app.vision_transcribe.browser.dom_locator import (
    click_by_descriptors,
    click_new_chat_fallback,
    click_send_when_ready,
    click_vision_mode_fallback,
    click_vision_mode_tab,
    ensure_batch_prompt,
    fill_batch_prompt,
    prompt_present_in_composer,
    upload_files_by_descriptors,
    wait_for_upload_settled,
)

_VISION_ACTIVE_JS = """
() => {
  const phHints = ['使用识图模式开始对话', '上传图片', '拖入图片', '识图'];
  for (const el of document.querySelectorAll('[placeholder]')) {
    const p = (el.getAttribute('placeholder') || '');
    if (!phHints.some((h) => p.includes(h))) continue;
    const r = el.getBoundingClientRect();
    if (r.height > 12 && r.width > 60 && r.bottom > 0) return true;
  }
  const labels = ['识图模式', '图片理解', '图像理解'];
  for (const label of labels) {
    for (const el of document.querySelectorAll('button, [role="tab"], [role="radio"], span, div')) {
      const t = (el.innerText || '').replace(/\\s+/g, ' ').trim();
      if (t !== label) continue;
      const r = el.getBoundingClientRect();
      if (!r.width || r.height < 8) continue;
      const sel = el.getAttribute('aria-selected') || el.getAttribute('aria-checked');
      if (sel === 'true') return true;
      const cls = (el.className || '').toString();
      if (/\\b(active|selected|checked|current|is-active)\\b/i.test(cls)) return true;
    }
  }
  return false;
}
"""


def workflow_enabled(cfg: dict[str, Any] | None) -> bool:
    if not cfg:
        return False
    wf = cfg.get("recorded_workflow")
    if not isinstance(wf, dict):
        return False
    if not wf.get("enabled"):
        return False
    steps = wf.get("steps")
    return isinstance(steps, list) and len(steps) > 0


def _steps_by_id(steps: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for step in steps:
        if isinstance(step, dict) and step.get("id"):
            out[str(step["id"])] = step
    return out


def is_vision_mode_active(page) -> bool:
    """是否已在识图模式（可跳过重复点击）。"""
    try:
        if bool(page.evaluate(_VISION_ACTIVE_JS)):
            return True
    except Exception:
        pass
    for factory in (
        lambda: page.get_by_placeholder("使用识图模式开始对话"),
        lambda: page.get_by_text("使用识图模式开始对话", exact=False),
        lambda: page.get_by_placeholder("上传图片", exact=False),
    ):
        try:
            loc = factory()
            if loc.count() > 0 and loc.first.is_visible():
                return True
        except Exception:
            continue
    try:
        loc = page.get_by_text("识图模式", exact=True)
        for i in range(min(loc.count(), 8)):
            el = loc.nth(i)
            if not el.is_visible():
                continue
            selected = el.get_attribute("aria-selected")
            if selected == "true":
                return True
    except Exception:
        pass
    return False


def _wait_vision_mode_active(page, *, timeout_s: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if is_vision_mode_active(page):
            return True
        time.sleep(0.25)
    return False


def click_vision_mode_robust(
    page,
    *,
    log: Callable[[str], None] | None = None,
    timeout_ms: int = 25_000,
    recorded_locators: list[dict[str, Any]] | None = None,
) -> bool:
    """识图模式：等待按钮出现后点击，并校验已进入。"""
    if is_vision_mode_active(page):
        if log:
            log("[识图模式] 已在识图模式，跳过")
        return True
    deadline = time.monotonic() + timeout_ms / 1000.0
    tried_template = False
    while time.monotonic() < deadline:
        clicked = False
        if click_vision_mode_tab(page, log=log):
            clicked = True
        elif click_vision_mode_fallback(page, log=log):
            clicked = True
        elif recorded_locators:
            # 录制到 radiogroup 时不能点组中心，会误选快速模式
            non_group = [
                d
                for d in recorded_locators
                if not (
                    str(d.get("strategy")) == "role"
                    and str(d.get("role")) == "radiogroup"
                )
            ]
            if non_group and click_by_descriptors(page, non_group, log=log):
                clicked = True
        if clicked:
            if _wait_vision_mode_active(page, timeout_s=3.5):
                if log:
                    log("[识图模式] 已进入 ✓")
                return True
            if log:
                log("[识图模式] 已点击但未检测到激活，重试…")
        if not tried_template:
            tried_template = True
            try:
                from app.vision_transcribe.browser.deepseek_ui import (
                    click_by_template,
                    load_ui_config,
                    smart_click,
                )

                cfg = load_ui_config()

                def _dom(fs, optional: bool) -> bool:
                    del fs, optional
                    return click_vision_mode_tab(page, log=None) or click_vision_mode_fallback(
                        page, log=None
                    )

                if smart_click(
                    page,
                    "vision_mode",
                    dom_factories=[],
                    config=cfg,
                    log=log,
                    dom_click_fn=_dom,
                ) or click_by_template(page, "vision_mode", config=cfg, log=log):
                    if _wait_vision_mode_active(page, timeout_s=3.5):
                        if log:
                            log("[识图模式] 模板/DOM 兜底已进入 ✓")
                        return True
            except Exception:
                pass
        time.sleep(0.45)
    if log:
        log("[识图模式] 超时（页面可能仍在加载或 UI 已变更）")
    return False


def _replay_click(
    page,
    step_id: str,
    step: dict[str, Any] | None,
    *,
    log: Callable[[str], None] | None,
) -> bool:
    locators = list((step or {}).get("locators") or [])
    if step_id == "vision_mode":
        return click_vision_mode_robust(
            page, log=log, recorded_locators=locators or None
        )
    if click_by_descriptors(page, locators, log=log):
        return True
    fallbacks = {
        "new_chat": click_new_chat_fallback,
        "vision_mode": click_vision_mode_fallback,
    }
    fn = fallbacks.get(step_id)
    if fn:
        return fn(page, log=log)
    return False


def replay_submit_steps(
    page,
    workflow: dict[str, Any],
    *,
    images: list[Path],
    prompt: str,
    log: Callable[[str], None] | None = None,
) -> bool:
    """回放：新对话 -> 识图 -> 填 Prompt -> 上传图 -> 必要时补填 -> 发送。"""
    steps = workflow.get("steps") or []
    by_id = _steps_by_id(steps)
    file_paths = [str(Path(p).resolve()).replace("\\", "/") for p in images]
    delay = 0.5

    if log:
        log(f"[录制回放] 开始（已录 {len(steps)} 步，batch 图 {len(file_paths)} 张）")

    if log:
        log("[录制回放] 1/5 开启新对话")
    if not _replay_click(page, "new_chat", by_id.get("new_chat"), log=log):
        if log:
            log("[录制回放] 失败: new_chat")
        return False
    time.sleep(1.0)

    if log:
        log("[录制回放] 2/5 识图模式")
    if not _replay_click(page, "vision_mode", by_id.get("vision_mode"), log=log):
        if log:
            log("[录制回放] 失败: vision_mode")
        return False
    time.sleep(delay)

    prompt_step = by_id.get("prompt")
    locators = list((prompt_step or {}).get("locators") or [])
    if log:
        log("[录制回放] 3/5 自动键入 Prompt")
    if not ensure_batch_prompt(page, prompt, recorded_locators=locators, log=log):
        if log:
            log("[录制回放] 填写 Prompt 失败")
        return False
    time.sleep(delay)

    upload_locators = list((by_id.get("upload") or {}).get("locators") or [])
    if not upload_locators:
        upload_locators = [{"strategy": "file_input"}]
    if log:
        log(f"[录制回放] 4/5 上传 bookfigures（{len(file_paths)} 张）")
    if not upload_files_by_descriptors(page, file_paths, upload_locators, log=log):
        if log:
            log("[录制回放] 上传图片失败")
        return False
    from app.vision_transcribe.browser.upload_guard import verify_upload_complete

    settled = wait_for_upload_settled(page, len(file_paths), log=log)
    up_ok, up_err = verify_upload_complete(
        page, len(file_paths), log=log, send_ready=settled
    )
    if not up_ok:
        if log:
            log(f"[录制回放] UploadGuard 失败: {up_err}")
        return False
    if not prompt_present_in_composer(page, prompt):
        if log:
            log("[录制回放] 上传后 Prompt 被清空，重新键入…")
        if not fill_batch_prompt(page, prompt, recorded_locators=locators, log=log):
            if log:
                log("[录制回放] 上传后补填 Prompt 失败")
            return False
    time.sleep(delay)

    from app.vision_transcribe.browser.prompt_guard import verify_prompt_exact

    ok_prompt, perr = verify_prompt_exact(page, prompt, log=log)
    if not ok_prompt:
        if log:
            log(f"[录制回放] PromptGuard 未通过，重填: {perr}")
        if not fill_batch_prompt(page, prompt, recorded_locators=locators, log=log):
            return False
        ok_prompt, perr = verify_prompt_exact(page, prompt, log=log)
        if not ok_prompt:
            if log:
                log(f"[录制回放] PromptGuard 仍失败: {perr}")
            return False

    if log:
        log("[录制回放] 5/5 等发送变亮后点击")
    send_step = by_id.get("send")
    if not click_send_when_ready(page, send_step, log=log, timeout_ms=120_000):
        if log:
            log("[录制回放] 发送失败（发送钮可能仍灰色）")
        return False
    return True
