"""DeepSeek 操作演示录制：在真实浏览器里点一遍，保存 DOM 步骤。"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.vision_transcribe.browser.dom_locator import (
    RECORD_GUIDE_STEPS,
    RECORD_OPTIONAL_STEPS,
    capture_click_descriptor,
    inject_record_banner,
)
from app.vision_transcribe.browser.deepseek_ui import load_ui_config, save_ui_config
from app.vision_transcribe.browser.profile_utils import (
    DEEPSEEK_BROWSER_ARGS,
    clear_stale_profile_locks,
    kill_profile_chromium,
    maximize_browser_window,
)

_MAX_CAPTURE_RETRIES = 3


def _capture_step_click(
    page,
    *,
    step_id: str,
    hint: str,
    log: Callable[[str], None],
) -> dict[str, Any]:
    """等待用户点击；超时或点错可重试，不立刻退出。"""
    last_err = ""
    for attempt in range(1, _MAX_CAPTURE_RETRIES + 1):
        try:
            inject_record_banner(page, step_id=step_id, hint=hint)
        except Exception:
            pass
        if attempt > 1:
            log(f"    重试 {attempt}/{_MAX_CAPTURE_RETRIES}…")
        else:
            log("    在浏览器窗口点击目标元素（点错可再点一次；超时会提示重试）")
        try:
            return capture_click_descriptor(page, timeout_ms=180_000)
        except Exception as e:
            last_err = str(e)
            log(f"    本步未成功: {last_err[:160]}")
            if attempt < _MAX_CAPTURE_RETRIES:
                log("    请重新点击正确元素…")
                time.sleep(0.5)
    raise RuntimeError(
        f"步骤 [{step_id}] 在 {_MAX_CAPTURE_RETRIES} 次尝试后仍未捕获点击。"
        f"最后错误: {last_err or '超时'}"
    )


def record_deepseek_workflow(
    *,
    profile_dir: Path,
    url: str = "https://chat.deepseek.com/",
    log: Callable[[str], None] | None = None,
    skip_upload_click: bool = False,  # 保留参数兼容；上传已不再录制
) -> dict[str, Any]:
    """引导用户在 DeepSeek 页面上演示一遍，写入 recorded_workflow。"""
    _ = skip_upload_click
    _log = log or print
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError(
            "未安装 playwright。请执行: pip install playwright && playwright install chromium"
        ) from e

    profile_dir = Path(profile_dir)
    profile_dir.mkdir(parents=True, exist_ok=True)
    clear_stale_profile_locks(profile_dir)
    kill_profile_chromium(profile_dir)

    steps_out: list[dict[str, Any]] = []
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
            no_viewport=True,
            args=DEEPSEEK_BROWSER_ARGS,
            ignore_default_args=["--enable-automation"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        maximize_browser_window(page, log=_log)
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1200)
        _log(
            "浏览器已打开。\n"
            "必填 3 步：新对话 → 识图模式 → 点一下输入框（仅记位置，不用打字）。\n"
            "运行时自动：键入 batch Prompt → 上传 bookfigures → 发送。\n"
            "可选第 4 步：在输入框输入 test 后点蓝色发送箭头（录位置，可跳过）。"
        )

        for step_id, action, hint in RECORD_GUIDE_STEPS:
            _log(f"\n>>> [{step_id}] {hint}")
            captured = _capture_step_click(
                page, step_id=step_id, hint=hint, log=_log
            )
            locators = list(captured.get("strategies") or [])
            if not locators:
                raise RuntimeError(f"步骤 {step_id} 未捕获到有效 DOM，请重试")

            step_entry: dict[str, Any] = {
                "id": step_id,
                "action": action,
                "locators": locators,
                "captured_tag": captured.get("tag"),
            }
            if step_id == "prompt":
                step_entry["note"] = "运行时自动 fill batch Prompt"
                _log(
                    "    ✓ 已记录输入框；下一步起将自动键入 Prompt、上传图片并发送（无需手打）"
                )
            steps_out.append(step_entry)
            if step_id != "prompt":
                _log(f"    已记录 {len(locators)} 条定位")
            time.sleep(0.3)

        for step_id, action, hint in RECORD_OPTIONAL_STEPS:
            _log(f"\n>>> [{step_id}]（可选）{hint}")
            _log("    30 秒内点击发送，或不做任何操作直接跳过…")
            try:
                captured = capture_click_descriptor(page, timeout_ms=30_000)
                locators = list(captured.get("strategies") or [])
                if locators:
                    steps_out.append(
                        {
                            "id": step_id,
                            "action": action,
                            "locators": locators,
                            "captured_tag": captured.get("tag"),
                            "optional": True,
                        }
                    )
                    _log(f"    已记录发送按钮 {len(locators)} 条定位")
                else:
                    _log("    已跳过发送录制（将用蓝色箭头自动定位）")
            except Exception:
                _log("    已跳过发送录制（将用蓝色箭头自动定位）")

        ctx.close()

    workflow = {
        "enabled": True,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "viewport": page.evaluate(
            "() => ({ width: window.innerWidth, height: window.innerHeight })"
        ),
        "runtime_auto": ["auto_fill_prompt", "auto_upload", "auto_send"],
        "steps": steps_out,
    }
    cfg = load_ui_config()
    cfg["recorded_workflow"] = workflow
    if cfg.get("click_strategy") == "auto":
        cfg["click_strategy"] = "recorded"
    save_ui_config(cfg)
    _log(f"\n已保存 {len(steps_out)} 步到 data/deepseek_ui.json（recorded_workflow）")
    return workflow
