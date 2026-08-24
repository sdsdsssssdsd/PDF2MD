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
    ensure_batch_prompt,
    fill_batch_prompt,
    prompt_present_in_composer,
    upload_files_by_descriptors,
    wait_for_upload_settled,
)


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
    for factory in (
        lambda: page.get_by_placeholder("使用识图模式开始对话"),
        lambda: page.get_by_text("使用识图模式开始对话", exact=False),
    ):
        try:
            loc = factory()
            if loc.count() > 0 and loc.first.is_visible():
                return True
        except Exception:
            continue
    return False


def click_vision_mode_robust(
    page,
    *,
    log: Callable[[str], None] | None = None,
    timeout_ms: int = 20_000,
) -> bool:
    """识图模式：等待按钮出现后点击，并校验已进入。"""
    if is_vision_mode_active(page):
        if log:
            log("[录制回放] 已在识图模式，跳过")
        return True
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        if click_vision_mode_fallback(page, log=log):
            time.sleep(0.6)
            if is_vision_mode_active(page):
                return True
        try:
            from app.vision_transcribe.browser.deepseek_ui import load_ui_config, smart_click

            cfg = load_ui_config()
            dom = [
                lambda: page.get_by_role("button", name="识图模式"),
                lambda: page.get_by_text("识图模式", exact=True),
            ]

            def _dom(fs, optional: bool) -> bool:
                del optional
                return click_vision_mode_fallback(page, log=None)

            if smart_click(
                page,
                "vision_mode",
                dom_factories=dom,
                config=cfg,
                log=log,
                dom_click_fn=_dom,
            ):
                time.sleep(0.6)
                if is_vision_mode_active(page):
                    return True
        except Exception:
            pass
        time.sleep(0.5)
    if log:
        log("[录制回放] 识图模式超时（页面可能仍在加载）")
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
        return click_vision_mode_robust(page, log=log)
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
    wait_for_upload_settled(page, len(file_paths), log=log)
    if not prompt_present_in_composer(page, prompt):
        if log:
            log("[录制回放] 上传后 Prompt 被清空，重新键入…")
        if not fill_batch_prompt(page, prompt, recorded_locators=locators, log=log):
            if log:
                log("[录制回放] 上传后补填 Prompt 失败")
            return False
    time.sleep(delay)

    if log:
        log("[录制回放] 5/5 等发送变亮后点击")
    send_step = by_id.get("send")
    if not click_send_when_ready(page, send_step, log=log, timeout_ms=120_000):
        if log:
            log("[录制回放] 发送失败（发送钮可能仍灰色）")
        return False
    return True
