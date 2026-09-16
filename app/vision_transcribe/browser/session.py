"""DeepSeek Web：浏览器会话生命周期。"""
from __future__ import annotations

import time
from pathlib import Path

from app.vision_transcribe.browser.base import NeedsUserError
from app.vision_transcribe.browser.deepseek_ui import smart_click
from app.vision_transcribe.browser.profile_utils import (
    DEEPSEEK_BROWSER_ARGS,
    clear_stale_profile_locks,
    kill_profile_chromium,
    maximize_browser_window,
)


class DeepSeekSessionMixin:
    def _page_disconnected_reason(self) -> str | None:
        page = self._page
        if page is None:
            return "浏览器页面未连接"
        try:
            if page.is_closed():
                return "浏览器页面已关闭"
        except Exception as e:
            return f"浏览器不可用: {e}"
        try:
            ctx = page.context
            br = ctx.browser if ctx is not None else None
            if br is not None and not br.is_connected():
                return "浏览器进程已断开"
        except Exception:
            pass
        return None
    def _raise_if_page_disconnected(self) -> None:
        reason = self._page_disconnected_reason()
        if reason:
            raise RuntimeError(
                f"DeepSeek {reason}（请保持浏览器窗口打开，或重试本批次）"
            )
    @staticmethod
    def _is_fatal_page_eval_error(err: Exception) -> bool:
        msg = str(err).lower()
        return (
            "has been closed" in msg
            or "target page, context or browser" in msg
            or "browser has been closed" in msg
        )
    def _log_dom_eval_error(self, stage: str, err: Exception) -> None:
        if self._is_fatal_page_eval_error(err):
            now = time.monotonic()
            if now - self._page_dead_log_at < 3.0:
                return
            self._page_dead_log_at = now
            self._log(f"[PW] {stage}：浏览器已关闭/断开")
            return
        self._log(f"[PW] {stage}失败: {err}")
    def ensure_browser(self) -> None:
        if self._page is not None:
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            raise RuntimeError(
                "未安装 playwright。请执行: pip install playwright && playwright install chromium"
            ) from e
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        last_err: Exception | None = None
        for attempt in range(2):
            try:
                cleared = clear_stale_profile_locks(self.profile_dir)
                if cleared:
                    self._log(f"清理 profile 锁: {cleared}")
                if attempt > 0:
                    n = kill_profile_chromium(self.profile_dir)
                    if n:
                        self._log(f"结束占用 profile 的进程: {n}")
                    time.sleep(1.5)
                self._playwright = sync_playwright().start()
                self._context = self._playwright.chromium.launch_persistent_context(
                    user_data_dir=str(self.profile_dir),
                    headless=self.headless,
                    accept_downloads=True,
                    no_viewport=True,
                    args=DEEPSEEK_BROWSER_ARGS,
                    ignore_default_args=["--enable-automation"],
                )
                from app.vision_transcribe.browser.clipboard_interceptor import (
                    install_clipboard_interceptor,
                )
                from app.vision_transcribe.browser.generation_guard import (
                    install_mutation_observer,
                )

                install_clipboard_interceptor(self._context)
                install_mutation_observer(self._context)
                self._page = (
                    self._context.pages[0]
                    if self._context.pages
                    else self._context.new_page()
                )
                maximize_browser_window(self._page, log=self._log)
                try:
                    self._context.grant_permissions(
                        ["clipboard-read", "clipboard-write"],
                        origin=self.url.rstrip("/") or "https://chat.deepseek.com",
                    )
                except Exception:
                    pass
                self._page.goto(self.url, wait_until="domcontentloaded", timeout=60000)
                self._page.wait_for_timeout(1500)
                from app.vision_transcribe.browser.clipboard_interceptor import (
                    inject_clipboard_interceptor,
                )

                inject_clipboard_interceptor(self._page)
                self._log("浏览器已打开 DeepSeek")
                return
            except Exception as e:
                last_err = e
                self._log(f"浏览器启动失败(尝试 {attempt + 1}/2): {e}")
                self.close()
        raise RuntimeError(
            f"无法启动 Playwright 浏览器（profile 可能被占用）。"
            f"请关闭所有 DeepSeek 自动化窗口后重试。详情: {last_err}"
        ) from last_err
    def close(self) -> None:
        try:
            if self._context is not None:
                self._context.close()
        finally:
            self._context = None
            self._page = None
            if self._playwright is not None:
                try:
                    self._playwright.stop()
                except Exception:
                    pass
                self._playwright = None

    # —— 细粒度 API（a2-1） ——
    def new_chat(self) -> None:
        page = self._require_page()
        dom = [
            lambda: page.get_by_role("button", name="开启新对话"),
            lambda: page.get_by_text("开启新对话", exact=True),
            lambda: page.get_by_role("button", name="新建对话"),
            lambda: page.get_by_role("button", name="New chat"),
            lambda: page.get_by_text("新建对话", exact=False),
            lambda: page.locator('[aria-label*="新对话"]'),
        ]
        smart_click(
            page,
            "new_chat",
            dom_factories=dom,
            config=self._ui_cfg,
            log=self._log,
            dom_click_fn=lambda fs, optional: self._click_first(
                fs, timeout_ms=8000, optional=optional
            ),
        )
        time.sleep(0.5)
        from app.vision_transcribe.browser.new_chat_guard import verify_new_chat_clean

        verify_new_chat_clean(page, log=self._log)
    def set_vision_mode(self) -> None:
        """识图模式 = 三按钮最右。L1 DOM → L2 截图 → L3 人工。"""
        page = self._require_page()
        from app.vision_transcribe.browser.dom_replay import click_vision_mode_robust
        from app.vision_transcribe.browser.new_chat_guard import (
            verify_vision_mode_active,
        )

        if click_vision_mode_robust(page, log=self._log, timeout_ms=25_000):
            verify_vision_mode_active(page, log=self._log)
            return
        raise NeedsUserError(
            "无法自动进入「识图模式」（三按钮最右侧）。"
            "请在浏览器中手动点击识图模式后点「继续」。"
        )
    def _click_mode_trio_rightmost(self, page) -> bool:
        """识图模式 = 三按钮最右。DeepSeek 常为 div/span，不限定 button。"""
        labels = ("快速模式", "专家模式", "识图模式")
        visible: list[tuple[float, object, str]] = []
        for label in labels:
            try:
                loc = page.get_by_text(label, exact=True)
                if loc.count() == 0:
                    loc = page.locator(f"text={label}")
                for i in range(min(loc.count(), 5)):
                    el = loc.nth(i)
                    if not el.is_visible():
                        continue
                    box = el.bounding_box()
                    if not box or box.get("width", 0) < 24:
                        continue
                    visible.append((float(box["x"]), el, label))
            except Exception:
                continue
        if not visible:
            self._log("未找到三模式按钮文字（快速/专家/识图）")
            return False
        visible.sort(key=lambda t: t[0])
        # 优先点「识图模式」；否则点横坐标最右
        target = next((t for t in visible if t[2] == "识图模式"), visible[-1])
        try:
            target[1].scroll_into_view_if_needed(timeout=5000)
            target[1].click(timeout=8000)
            self._log(f"已点击模式: {target[2]}")
            return True
        except Exception as e:
            self._log(f"点击模式失败 {target[2]}: {e}")
            try:
                target[1].click(force=True, timeout=5000)
                return True
            except Exception:
                return False
    def _require_page(self):
        self.ensure_browser()
        assert self._page is not None
        return self._page
    def _looks_logged_in(self) -> bool:
        """已登录页面上常见的输入区/侧栏元素（优先于「登录」字样误报）。"""
        page = self._page
        if page is None:
            return False
        for factory in (
            lambda: page.get_by_text("开启新对话", exact=True),
            lambda: page.get_by_placeholder("给 DeepSeek 发送消息"),
            lambda: page.get_by_text("识图模式", exact=True),
            lambda: page.get_by_text("快速模式", exact=True),
            lambda: page.locator("textarea"),
            lambda: page.locator('[contenteditable="true"]'),
        ):
            try:
                loc = factory()
                if loc.count() > 0 and loc.first.is_visible():
                    return True
            except Exception:
                continue
        return False
    def _raise_if_needs_user(self) -> None:
        """仅在明显未登录/验证码时打断。已登录时忽略「退出登录」等含「登录」字样。"""
        page = self._page
        if page is None:
            return
        if self._looks_logged_in():
            return
        try:
            body = page.inner_text("body")
        except Exception:
            return
        # 必须精确匹配「登录」，避免误伤侧栏「退出登录」
        for factory in (
            lambda: page.get_by_role("button", name="登录", exact=True),
            lambda: page.get_by_role("button", name="Log in", exact=True),
            lambda: page.get_by_role("button", name="Sign in", exact=True),
            lambda: page.get_by_role("link", name="登录", exact=True),
        ):
            try:
                loc = factory()
                if loc.count() > 0 and loc.first.is_visible():
                    raise NeedsUserError(
                        "DeepSeek 需要登录。请在浏览器中完成登录后点「继续」（不要关窗口）。"
                    )
            except NeedsUserError:
                raise
            except Exception:
                continue
        needles = (
            "验证码",
            "人机验证",
            "登录后继续",
            "Complete the security check",
        )
        for n in needles:
            if n in body:
                raise NeedsUserError(
                    f"DeepSeek 需要人工处理（{n}）。完成后点「继续」，不要关浏览器窗口。"
                )
