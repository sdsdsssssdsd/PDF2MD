"""DeepSeek Web Playwright Adapter（细节见 a2-1.md）。

约束：
- headless=False（有头浏览器，便于处理验证码/登录）
- persistent profile 复用登录，不保存账号密码
- 多文件 set_input_files 上传，不模拟系统文件框
- 每个 batch 新对话；整份 PDF 共用一个浏览器会话
- 回答完成：停止按钮消失 AND 内容连续稳定 N ms
- 优先点「复制」读剪贴板；失败再读 assistant DOM
- Selector 只允许出现在本文件；多级 locator 容错
- 登录/验证码 → NeedsUserError，不直接判任务失败
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from app.vision_transcribe.browser.base import (
    AdapterResult,
    NeedsUserError,
    VisionWebAdapter,
)
from app.vision_transcribe.browser.deepseek_ui import (
    has_recorded_workflow,
    load_ui_config,
    smart_click,
)
from app.vision_transcribe.browser.dom_replay import replay_submit_steps
from app.vision_transcribe.browser.profile_utils import (
    DEEPSEEK_BROWSER_ARGS,
    clear_stale_profile_locks,
    kill_profile_chromium,
    maximize_browser_window,
)


class DeepSeekPlaywrightAdapter(VisionWebAdapter):
    def __init__(
        self,
        *,
        profile_dir: Path,
        url: str = "https://chat.deepseek.com/",
        headless: bool = False,
        response_stable_ms: int = 2500,
        response_timeout_ms: int = 300_000,
        log=None,
    ) -> None:
        self.profile_dir = Path(profile_dir)
        self.url = url
        self.headless = bool(headless)
        self.response_stable_ms = int(response_stable_ms)
        self.response_timeout_ms = int(response_timeout_ms)
        self._log = log or (lambda _m: None)
        self._ui_cfg = load_ui_config()
        self._playwright = None
        self._context = None
        self._page = None
        self._batch_start_page: int | None = None
        self._batch_end_page: int | None = None
        self._peak_dom_katex_chars: int = 0
        self.last_extract_stats: dict[str, Any] | None = None
        self._capture_output_dir: Path | None = None
        self._capture_batch_id: int | None = None
        self._contam_log_at: float = 0.0
        self._page_dead_log_at: float = 0.0

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

    def set_capture_context(self, output_dir: Path, batch_id: int) -> None:
        """Pipeline 注入：保存 CaptureBundle 到 .vision/batches/…/attempts/。"""
        self._capture_output_dir = Path(output_dir)
        self._capture_batch_id = int(batch_id)

    def _wait_transcript_complete(self, text: str | None = None) -> bool:
        """等待阶段：PAGE + 字数达标即可，不要求 BATCH_END（校验阶段再查）。"""
        from app.vision_transcribe.transcript_quality import batch_transcript_complete

        t = self._assistant_text() if text is None else text
        return batch_transcript_complete(
            t or "",
            start_page=self._batch_start_page,
            end_page=self._batch_end_page,
            batch_id=self._capture_batch_id,
            require_batch_end=False,
        )

    def _batch_transcript_complete(self, text: str | None = None) -> bool:
        from app.vision_transcribe.transcript_quality import batch_transcript_complete

        t = self._assistant_text() if text is None else text
        return batch_transcript_complete(
            t or "",
            start_page=self._batch_start_page,
            end_page=self._batch_end_page,
            batch_id=self._capture_batch_id,
            require_batch_end=False,
        )

    def _response_generation_ready(self, text: str) -> bool:
        from app.vision_transcribe.browser.generation_guard import (
            dom_quiet_ms,
            inject_mutation_observer,
        )

        page = self._page
        if page is not None:
            inject_mutation_observer(page)
        if not self._wait_transcript_complete(text):
            return False
        # 等待阶段不要求 BATCH_END（校验阶段再查）
        if page is not None and not dom_quiet_ms(page, quiet_ms=2500):
            return False
        return True

    def _log_contam_throttled(self, src: str) -> None:
        now = time.monotonic()
        if now - self._contam_log_at < 8.0:
            return
        self._contam_log_at = now
        self._log(f"[PW] {src} 疑似 Prompt/侧栏，忽略（非回答正文）")

    def _assistant_text_for_wait(self) -> str:
        """等待收尾时用 DOM 结构化正文（含 PAGE 标记），避免 KaTeX inner_text 漏标记。"""
        from app.vision_transcribe.clipboard_sanitize import recover_wait_transcript

        self._raise_if_page_disconnected()
        dom_md = self._assistant_markdown_from_dom()
        recovered = recover_wait_transcript(dom_md or "")
        if recovered:
            return recovered
        if (dom_md or "").strip():
            self._log_contam_throttled("DOM 抽取")
        raw = self._assistant_text() or ""
        recovered = recover_wait_transcript(raw)
        if recovered:
            return recovered
        if raw.strip():
            self._log_contam_throttled("KaTeX/inner_text")
        return ""

    def _raise_if_model_degeneration(self, text: str | None = None) -> None:
        """完成检查：循环垃圾一旦出现立刻失败，禁止点「继续生成」把 kkkk 拉长。"""
        from app.vision_transcribe.transcript_quality import has_model_degeneration

        t = text if text is not None else (self._assistant_text_for_wait() or "")
        if has_model_degeneration(t or ""):
            raise RuntimeError(
                "模型输出退化（连续重复字符/作者缩写循环），"
                "请开启新对话后重试本批次"
            )

    def _try_finish_wait_response(self, text: str, *, toolbar: bool) -> bool:
        """UI 已结束且正文达标时结束 wait；返回 True 表示应 return。"""
        from app.vision_transcribe.browser.generation_guard import text_has_batch_end

        t = (text or "").strip()
        self._raise_if_model_degeneration(t)
        if self._response_generation_ready(t):
            self._log("[PW] 生成完毕（BATCH_END + PAGE 完整 + DOM 稳定）")
            return True
        if self._wait_transcript_complete(t):
            if (
                self._capture_batch_id is not None
                and not text_has_batch_end(t, self._capture_batch_id)
            ):
                self._log(
                    f"[PW] 生成完毕（PAGE/字数达标 {len(t)} 字；"
                    "BATCH_END 将在校验阶段检查）"
                )
            else:
                self._log(
                    "[PW] 生成完毕（已滚到底：发送灰 + 无继续生成 + 操作栏/复制）"
                )
            return True
        return False

    def _click_continue_generate_now(self, *, reason: str = "") -> bool:
        """见到「继续生成」立即点击（DOM + 模板）。"""
        from app.vision_transcribe.browser.deepseek_ui import (
            click_continue_generate_if_visible,
            is_continue_generate_visible,
            scroll_chat_to_bottom,
        )

        page = self._page
        if page is None:
            return False
        if not is_continue_generate_visible(
            page, config=self._ui_cfg, allow_template=True
        ):
            return False
        scroll_chat_to_bottom(page, log=None)
        if not click_continue_generate_if_visible(
            page, config=self._ui_cfg, log=self._log, allow_template=True
        ):
            return False
        suffix = f"（{reason}）" if reason else ""
        self._log(f"[PW] 已点击「继续生成」{suffix}")
        return True

    def _click_regenerate_retry_now(self, *, reason: str = "") -> bool:
        """见到「重试」立即点击（生成失败时 DeepSeek 会出此钮）。"""
        from app.vision_transcribe.browser.deepseek_ui import (
            click_regenerate_retry_if_visible,
            is_regenerate_retry_visible,
            scroll_chat_to_bottom,
        )

        page = self._page
        if page is None:
            return False
        if not is_regenerate_retry_visible(
            page, config=self._ui_cfg, allow_template=True
        ):
            return False
        scroll_chat_to_bottom(page, log=None)
        if not click_regenerate_retry_if_visible(
            page, config=self._ui_cfg, log=self._log, allow_template=True
        ):
            return False
        suffix = f"（{reason}）" if reason else ""
        self._log(f"[PW] 已点击「重试」{suffix}")
        return True

    def _drain_continue_before_copy(self, *, max_rounds: int = 24) -> None:
        """复制/Capture 前：只要还有「继续生成」就连续点完。"""
        for _ in range(max_rounds):
            if not self._click_continue_generate_now(reason="复制前"):
                break
            self.wait_response(resume=True)
            self._scroll_chat_to_bottom()

    # —— 生命周期 ——
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

    def upload_images(self, paths: list[Path]) -> None:
        page = self._require_page()
        files = [str(Path(p).resolve()) for p in paths]
        if not files:
            raise ValueError("无图片可上传")

        # 优先直接 set_input_files；失败再用 filechooser
        inputs = page.locator('input[type="file"]')
        try:
            if inputs.count() > 0:
                inputs.first.set_input_files(files)
                return
        except Exception:
            pass

        def _attach(chooser) -> None:
            chooser.set_files(files)

        try:
            with page.expect_file_chooser(timeout=8000) as fc:
                attach_dom = [
                    lambda: page.get_by_role("button", name="上传"),
                    lambda: page.locator('[aria-label*="上传"]'),
                    lambda: page.locator('[aria-label*="附件"]'),
                ]
                if not smart_click(
                    page,
                    "attach",
                    dom_factories=attach_dom,
                    config=self._ui_cfg,
                    log=self._log,
                    dom_click_fn=lambda fs, optional: self._click_first(
                        fs
                        + [
                            lambda: page.locator("button")
                            .filter(has=page.locator("svg"))
                            .last,
                        ],
                        timeout_ms=5000,
                        optional=optional,
                    ),
                ):
                    raise RuntimeError("找不到附件/上传按钮")
            _attach(fc.value)
        except Exception as e:
            raise RuntimeError(f"上传图片失败: {e}") from e

    def _fill_prompt_only(self, prompt: str) -> None:
        from app.vision_transcribe.browser.dom_locator import fill_batch_prompt

        page = self._require_page()
        if not fill_batch_prompt(page, prompt, log=self._log):
            raise RuntimeError("填写 Prompt 失败（找不到输入框或填写后校验未通过）")

    def send_prompt(self, prompt: str) -> None:
        self._fill_prompt_only(prompt)
        from app.vision_transcribe.browser.dom_locator import (
            click_send_fallback,
            wait_for_send_ready,
        )

        wait_for_send_ready(self._page, log=self._log)
        if not click_send_fallback(self._page, log=self._log, timeout_ms=120_000):
            raise RuntimeError("找不到发送按钮（蓝色箭头）")

    def wait_response(self, *, resume: bool = False) -> None:
        """等待全部生成完毕。结束特征须先滚到底再判：
        发送变灰 + 无继续生成 + 操作栏/复制出现。

        「继续生成」：一旦出现立即点击，不等待其它条件。
        """
        from app.vision_transcribe.browser.deepseek_ui import (
            is_continue_generate_visible,
            is_generation_fully_done,
            is_send_composer_gray,
            looks_like_vision_response,
            match_action_toolbar_on_page,
            scroll_chat_to_bottom,
        )

        page = self._require_page()
        deadline = time.monotonic() + self.response_timeout_ms / 1000.0
        last_text = ""
        stable_since: float | None = None
        continue_clicks = 0
        retry_clicks = 0
        max_continue = 32
        max_retry = 8
        saw_generating = bool(resume)
        loop_start = time.monotonic()
        last_log = 0.0
        ui_done_stall_len = -1
        ui_done_stall_since: float | None = None

        def _stall_bail_seconds() -> float:
            sp, ep = self._batch_start_page, self._batch_end_page
            if sp is not None and ep is not None and sp == ep:
                return 22.0
            return 40.0

        def _check_ui_done_stall(cur_len: int, text: str = "") -> bool:
            nonlocal ui_done_stall_len, ui_done_stall_since
            if cur_len <= 0:
                if ui_done_stall_len != 0:
                    ui_done_stall_len = 0
                    ui_done_stall_since = time.monotonic()
                    return False
                if ui_done_stall_since is None:
                    ui_done_stall_since = time.monotonic()
                    return False
                stalled = time.monotonic() - ui_done_stall_since
                if stalled < 18.0:
                    return False
                # 无操作栏时 0 字多为 Prompt/侧栏误读或首轮未出字，继续等
                from app.vision_transcribe.browser.deepseek_ui import (
                    is_response_action_toolbar_visible,
                )

                if not is_response_action_toolbar_visible(
                    page, config=self._ui_cfg
                ):
                    return False
                raise TimeoutError(
                    "等待 DeepSeek 回答超时：UI 已结束但正文为 0 字"
                    "（抽取到用户 Prompt/侧栏，或尚未出现回答）"
                )
            if cur_len != ui_done_stall_len:
                ui_done_stall_len = cur_len
                ui_done_stall_since = time.monotonic()
                return False
            if ui_done_stall_since is None:
                ui_done_stall_since = time.monotonic()
                return False
            stalled = time.monotonic() - ui_done_stall_since
            if stalled < _stall_bail_seconds():
                return False
            sample = (text or self._assistant_text_for_wait() or "").strip()
            if self._batch_transcript_complete(sample):
                self._log(
                    f"[PW] 正文 {cur_len} 字已连续 {stalled:.0f}s 无增长"
                    "（UI 已结束），提前进入复制/校验"
                )
                return True
            if _try_continue_now("停滞未达标"):
                ui_done_stall_len = -1
                ui_done_stall_since = None
                return False
            from app.vision_transcribe.transcript_quality import (
                wait_should_release_to_copy,
            )

            if wait_should_release_to_copy(
                sample,
                start_page=self._batch_start_page,
                end_page=self._batch_end_page,
            ):
                self._log(
                    f"[PW] 正文 {cur_len} 字已连续 {stalled:.0f}s 无增长"
                    "（UI 已结束；等待阶段 PAGE 标记不齐，进入复制/校验）"
                )
                return True
            self._log(
                f"[PW] 正文 {cur_len} 字已停滞 {stalled:.0f}s 但 PAGE/字数未达标，"
                "继续等待…"
            )
            return False

        def _continue_armed() -> bool:
            return (
                resume
                or saw_generating
                or (time.monotonic() - loop_start) >= 1.5
            )

        def _try_regenerate_retry_now(reason: str = "") -> bool:
            nonlocal retry_clicks, stable_since, last_text, saw_generating
            nonlocal ui_done_stall_len, ui_done_stall_since
            if not _continue_armed():
                return False
            if not self._click_regenerate_retry_now(reason=reason):
                return False
            retry_clicks += 1
            if retry_clicks > max_retry:
                raise RuntimeError("「重试」点击次数过多，请检查页面状态")
            stable_since = None
            last_text = ""
            ui_done_stall_len = -1
            ui_done_stall_since = None
            saw_generating = True
            time.sleep(0.25)
            return True

        def _try_continue_now(reason: str = "") -> bool:
            nonlocal continue_clicks, stable_since, last_text, saw_generating
            nonlocal ui_done_stall_len, ui_done_stall_since
            if not _continue_armed():
                return False
            self._raise_if_model_degeneration()
            if not is_continue_generate_visible(
                page, config=self._ui_cfg, allow_template=False
            ):
                return False
            if not self._click_continue_generate_now(reason=reason):
                return False
            continue_clicks += 1
            if continue_clicks > max_continue:
                raise RuntimeError("「继续生成」点击次数过多，请检查页面状态")
            stable_since = None
            last_text = ""
            ui_done_stall_len = -1
            ui_done_stall_since = None
            saw_generating = True
            time.sleep(0.15)
            return True

        while time.monotonic() < deadline:
            self._raise_if_needs_user()
            self._raise_if_page_disconnected()

            # 生成失败时的「重试」优先于「继续生成」
            if _try_regenerate_retry_now("等待中"):
                continue

            # 最高优先级：继续生成 — 见到就点
            if _try_continue_now("等待中"):
                continue

            generating = self._is_generating()
            if generating:
                saw_generating = True
                stable_since = None
                now = time.monotonic()
                if now - last_log > 8.0:
                    sample = self._assistant_text_for_wait() or ""
                    self._log(f"[PW] 生成中…（{len(sample)} 字）")
                    last_log = now
                    self._raise_if_model_degeneration(sample)
                time.sleep(0.3)
                continue

            if not saw_generating:
                now = time.monotonic()
                if resume or (now - loop_start) > 8.0:
                    saw_generating = True
                elif now - last_log > 5.0:
                    self._log("[PW] 等待生成状态…")
                    last_log = now
                time.sleep(0.25)
                continue

            # 首轮 assistant 未出现时勿进收尾空转（避免误读 Prompt + 刷屏）
            warm_probe = self._assistant_text_for_wait() or ""
            if not warm_probe.strip():
                now_w = time.monotonic()
                if (now_w - loop_start) < 300.0:
                    if now_w - last_log > 8.0:
                        self._log(
                            "[PW] assistant 正文尚未出现，继续等待首轮输出…"
                        )
                        last_log = now_w
                    ui_done_stall_len = -1
                    ui_done_stall_since = None
                    stable_since = None
                    time.sleep(0.35)
                    continue

            # —— 结束：先滚到底，再在底部看结束特征 ——
            scroll_chat_to_bottom(page, log=None)
            now = time.monotonic()
            send_gray = is_send_composer_gray(page, config=self._ui_cfg)
            has_continue = is_continue_generate_visible(
                page, config=self._ui_cfg, allow_template=True
            )
            toolbar = match_action_toolbar_on_page(page, config=self._ui_cfg)
            if now - last_log > 5.0:
                self._log(
                    "[PW] 收尾检查：滚到底后 "
                    f"发送灰={'是' if send_gray else '否'}，"
                    f"继续生成={'有' if has_continue else '无'}，"
                    f"操作栏={'有' if toolbar else '无'}"
                )
                last_log = now

            if has_continue and _try_continue_now("收尾"):
                continue

            # 结束判定细节紧跟周期状态日志，避免刷屏
            detail_log = self._log if (now - last_log) < 0.05 else None
            if is_generation_fully_done(
                page,
                config=self._ui_cfg,
                scroll_first=False,
                log=detail_log,
            ):
                text = self._assistant_text_for_wait()
                if self._try_finish_wait_response(text or "", toolbar=bool(toolbar)):
                    return
                if now - last_log > 8.0:
                    self._log(
                        f"[PW] 结束特征已满足但 PAGE/字数未达标（{len(text or '')} 字），"
                        "继续等待…"
                    )
                    last_log = now
                if _try_continue_now("字数未达标"):
                    continue
                if _check_ui_done_stall(len(text or ""), text or ""):
                    return
                stable_since = None
                time.sleep(0.35)
                continue

            text = self._assistant_text_for_wait()
            if text:
                self._peak_dom_katex_chars = max(
                    self._peak_dom_katex_chars, len(text)
                )
            content_ok = looks_like_vision_response(
                text,
                start_page=self._batch_start_page,
                end_page=self._batch_end_page,
            )

            # 弱条件兜底：滚到底后发送已灰、无继续生成、内容稳定
            if send_gray and content_ok and not has_continue:
                if text == last_text and text.strip():
                    if stable_since is None:
                        stable_since = time.monotonic()
                    elif (time.monotonic() - stable_since) * 1000 >= self.response_stable_ms:
                        if self._try_finish_wait_response(text, toolbar=bool(toolbar)):
                            return
                        self._log(
                            f"[PW] 内容已稳定但 PAGE/字数未达标（{len(text)} 字），继续等待…"
                        )
                        if _try_continue_now("稳定未达标"):
                            continue
                        if send_gray and _check_ui_done_stall(len(text), text):
                            return
                        stable_since = None
                else:
                    stable_since = None
                    last_text = text
            else:
                stable_since = None
                last_text = text

            now = time.monotonic()
            if now - last_log > 8.0:
                self._log(
                    f"[PW] 等待收尾… 发送灰={'是' if send_gray else '否'}，"
                    f"操作栏={'有' if toolbar else '无'}，文本={len(text)} 字"
                )
                last_log = now
            time.sleep(0.5)
        raise TimeoutError("等待 DeepSeek 回答超时")

    def _scroll_chat_to_bottom(self) -> None:
        """输出完毕后滚到对话底部，便于露出复制按钮。"""
        from app.vision_transcribe.browser.deepseek_ui import scroll_chat_to_bottom

        scroll_chat_to_bottom(self._require_page(), log=self._log)

    def _last_assistant_locator(self):
        page = self._page
        if page is None:
            return None
        for sel in (
            '[data-message-author-role="assistant"]',
            ".ds-message",
            ".markdown-body",
            "div[class*='assistant']",
        ):
            try:
                loc = page.locator(sel)
                n = loc.count()
                if n > 0:
                    return loc.nth(n - 1)
            except Exception:
                continue
        return None

    def _click_copy_last_response(self) -> bool:
        """点最后一条回答旁的「复制」。"""
        page = self._require_page()
        last = self._last_assistant_locator()
        if last is not None:
            try:
                last.hover(timeout=3000)
                page.wait_for_timeout(250)
            except Exception:
                pass
        candidates: list = []
        if last is not None:
            candidates.extend(
                [
                    last.get_by_role("button", name="复制"),
                    last.locator('[aria-label*="复制"]'),
                    last.locator('[aria-label*="Copy" i]'),
                    last.locator("button").filter(has_text="复制"),
                ]
            )
        candidates.extend(
            [
                page.get_by_role("button", name="复制"),
                page.locator('[aria-label*="复制"]'),
                page.locator('[aria-label*="Copy" i]'),
                page.locator('[data-testid*="copy" i]'),
            ]
        )
        for factory in candidates:
            try:
                loc = factory()
                n = loc.count()
                if n <= 0:
                    continue
                for i in range(n - 1, -1, -1):
                    btn = loc.nth(i)
                    if not btn.is_visible():
                        continue
                    btn.scroll_into_view_if_needed(timeout=3000)
                    btn.click(timeout=5000)
                    self._log("[PW] 已点击复制按钮")
                    return True
            except Exception:
                continue
        return False

    _COPY_ASSISTANT_JS = """
    async () => {
      const selectors = [
        '[data-message-author-role="assistant"]',
        '.ds-message',
        '.markdown-body',
        '.assistant',
      ];
      let last = null;
      for (const sel of selectors) {
        const nodes = document.querySelectorAll(sel);
        if (nodes.length) last = nodes[nodes.length - 1];
      }
      if (!last) return { ok: false, text: '', via: 'none' };

      const copyBtn = last.querySelector(
        'button[aria-label*="复制"], button[aria-label*="Copy" i], '
        + '[aria-label*="复制"], [aria-label*="Copy" i]'
      );
      if (copyBtn) {
        for (let attempt = 0; attempt < 4; attempt++) {
          copyBtn.click();
          await new Promise((r) => setTimeout(r, 350 + attempt * 250));
          try {
            const t = await navigator.clipboard.readText();
            if (t && t.trim().length > 200) {
              return { ok: true, text: t, via: 'assistant-copy-btn' };
            }
          } catch (e) {}
        }
      }

      return { ok: false, text: '', via: 'none' };
    }
    """

    def _read_clipboard_text(self) -> str:
        """读剪贴板：优先隔离拦截内容，避免依赖/污染系统剪贴板。"""
        page = self._page
        if page is not None:
            try:
                from app.vision_transcribe.browser.clipboard_interceptor import (
                    latest_copy_api_text,
                )

                api = latest_copy_api_text(page)
                if str(api or "").strip():
                    return str(api)
            except Exception:
                pass
            try:
                text = page.evaluate(
                    "async () => { try { return await navigator.clipboard.readText(); }"
                    " catch(e) { return ''; } }"
                )
                if str(text or "").strip():
                    from app.vision_transcribe.vision_structure_repair import (
                        markdown_lacks_structure,
                    )

                    if not markdown_lacks_structure(str(text)):
                        return str(text)
            except Exception:
                pass

        from app.vision_transcribe.browser.html_to_markdown import html_fragment_to_markdown
        from app.vision_transcribe.browser.system_clipboard import read_system_clipboard_rich

        plain, html_raw = read_system_clipboard_rich()
        if plain.strip():
            from app.vision_transcribe.vision_structure_repair import (
                markdown_lacks_structure,
            )

            if not markdown_lacks_structure(plain):
                return plain
            html_md = html_fragment_to_markdown(html_raw)
            if html_md.strip() and not markdown_lacks_structure(html_md):
                self._log(f"[PW] 剪贴板 HTML 还原 Markdown（{len(html_md)} 字）")
                return html_md
            return plain

        if html_raw.strip():
            html_md = html_fragment_to_markdown(html_raw)
            if html_md.strip():
                return html_md

        if page is not None:
            try:
                text = page.evaluate(
                    "async () => { try { return await navigator.clipboard.readText(); }"
                    " catch(e) { return ''; } }"
                )
                if str(text or "").strip():
                    return str(text)
            except Exception:
                pass
        return ""

    def _copy_assistant_scoped(self) -> str:
        """仅复制最后一条 assistant 回答（禁止 Ctrl+A 全页）；优先隔离拦截。"""
        from app.vision_transcribe.browser.clipboard_interceptor import (
            copy_generation,
            inject_clipboard_interceptor,
            latest_copy_api_text,
            set_clipboard_isolate,
        )

        page = self._require_page()
        inject_clipboard_interceptor(page)
        set_clipboard_isolate(page, True)
        gen_before = copy_generation(page)
        last = self._last_assistant_locator()
        if last is None:
            return ""
        try:
            last.scroll_into_view_if_needed(timeout=4000)
            last.click(timeout=3000)
            page.wait_for_timeout(120)
        except Exception:
            pass
        try:
            result = page.evaluate(self._COPY_ASSISTANT_JS)
            if isinstance(result, dict) and result.get("ok") and result.get("text"):
                via = result.get("via") or "js"
                n = len(str(result["text"]))
                self._log(f"[PW] 已复制 assistant 回答（{via}，{n} 字）")
                return str(result["text"])
        except Exception as e:
            self._log(f"[PW] assistant scoped 复制失败: {e}")
        # 隔离模式下 write 不进 OS，从拦截器取
        deadline = time.monotonic() + 4.0
        while time.monotonic() < deadline:
            if copy_generation(page) > gen_before:
                api = latest_copy_api_text(page)
                if api.strip():
                    self._log(f"[PW] 已复制 assistant 回答（isolate，{len(api)} 字）")
                    return api
            page.wait_for_timeout(80)
        api = latest_copy_api_text(page)
        if api.strip():
            return api
        return ""

    def _copy_assistant_via_ctrl_c(self) -> bool:
        """兼容旧名：改为 scoped 复制，不再 Ctrl+A 全页。"""
        text = self._copy_assistant_scoped()
        if text.strip():
            return True
        self._log("[PW] scoped 复制未拿到内容")
        return False

    def _make_clipboard_sentinel(self) -> str:
        import secrets

        bid = self._capture_batch_id or 0
        return (
            f"PDF2MD_CLIPBOARD_SENTINEL\n"
            f"batch={bid:04d}\n"
            f"nonce={secrets.token_hex(8)}"
        )

    def _assistant_html_raw(self) -> str:
        page = self._page
        if page is None:
            return ""
        last = self._last_assistant_locator()
        if last is None:
            return ""
        try:
            html = last.evaluate("el => el.outerHTML")
            return str(html or "")
        except Exception:
            return ""

    def _read_clipboard_after_sentinel(
        self,
        sentinel: str,
        *,
        timeout_ms: int = 12_000,
    ) -> str:
        """等待剪贴板从 sentinel 变为新内容并稳定。"""
        from app.vision_transcribe.browser.deepseek_ui import _read_clipboard_when_stable

        deadline = time.monotonic() + timeout_ms / 1000.0
        while time.monotonic() < deadline:
            cur = self._read_clipboard_text()
            if cur.strip() and cur.strip() != sentinel.strip():
                return _read_clipboard_when_stable(
                    self._read_clipboard_text, log=self._log, timeout_ms=4000
                )
            time.sleep(0.12)
        return ""

    def _capture_copy_rounds(self, rounds: int = 3) -> list:
        """多轮点击复制；默认隔离模式，不写/不读系统剪贴板。"""
        from app.vision_transcribe.browser.clipboard_interceptor import (
            copy_generation,
            inject_clipboard_interceptor,
            latest_copy_api_html,
            latest_copy_api_text,
            set_clipboard_isolate,
        )
        from app.vision_transcribe.browser.deepseek_ui import (
            click_copy_response_button,
            scroll_chat_to_bottom,
        )
        from app.vision_transcribe.capture.models import CopyRound

        page = self._require_page()
        inject_clipboard_interceptor(page)
        set_clipboard_isolate(page, True)
        self._scroll_chat_to_bottom()
        self._log("[PW] Copy 隔离模式：不写入系统剪贴板（用户 Ctrl+C/V 不受影响）")

        out: list[CopyRound] = []
        captured_html = ""
        for i in range(1, rounds + 1):
            gen_before = copy_generation(page)
            sentinel = self._make_clipboard_sentinel()  # 仅作 round 标记，不写 OS
            page.wait_for_timeout(80)
            scroll_chat_to_bottom(page, log=None)

            clicked = click_copy_response_button(
                page, config=self._ui_cfg, log=self._log
            )
            copy_fired = False
            api_text = ""
            deadline = time.monotonic() + 12.0
            while time.monotonic() < deadline:
                gen_after = copy_generation(page)
                if gen_after > gen_before:
                    api_text = latest_copy_api_text(page)
                    if api_text.strip():
                        copy_fired = True
                        break
                page.wait_for_timeout(100)

            if not api_text.strip():
                api_text = latest_copy_api_text(page)
            html = latest_copy_api_html(page)
            if html.strip():
                captured_html = html

            if clicked and not copy_fired:
                self._log(
                    f"[PW] Copy round {i}：隔离通道未捕获（COPY_NOT_FIRED?），"
                    "跳过后续轮次"
                )

            # clipboard_text 字段：隔离模式下与 copy_api 同源（不读 OS）
            out.append(
                CopyRound(
                    round_index=i,
                    copy_api_text=api_text,
                    clipboard_text=api_text if copy_fired else "",
                    copy_api_generation=copy_generation(page),
                    sentinel=sentinel,
                    copy_fired=copy_fired and clicked,
                )
            )
            if clicked and not copy_fired:
                break
            if i < rounds:
                page.wait_for_timeout(280)

        # 供后续 HTML→MD 使用（不读系统剪贴板）
        self._last_isolated_copy_html = captured_html
        return out

    def _collect_capture_bundle(self):
        from app.vision_transcribe.browser.html_to_markdown import html_fragment_to_markdown
        from app.vision_transcribe.capture.consensus import (
            pick_copy_consensus,
        )
        from app.vision_transcribe.capture.models import CaptureBundle
        from app.vision_transcribe.capture.store import (
            allocate_attempt_dir,
            save_capture_bundle,
        )

        self._log("[PW] CaptureBundle：Copy 隔离（至多 3 轮）+ DOM 兜底")
        self._last_isolated_copy_html = ""
        copy_rounds = self._capture_copy_rounds(rounds=3)

        consensus_inputs: list[tuple[str, str]] = []
        for rnd in copy_rounds:
            if rnd.copy_api_text.strip():
                consensus_inputs.append((f"copy_api_{rnd.round_index}", rnd.copy_api_text))
            # 隔离模式下 clipboard_* 与 api 同源，避免重复加权；仅在不同时加入
            if (
                rnd.clipboard_text.strip()
                and rnd.clipboard_text.strip() != rnd.copy_api_text.strip()
            ):
                consensus_inputs.append(
                    (f"clipboard_{rnd.round_index}", rnd.clipboard_text)
                )

        copy_label, copy_text, copy_stable, copy_fail = pick_copy_consensus(
            consensus_inputs
        )

        from app.vision_transcribe.capture.consensus import diagnose_transport_mismatch

        best_api = max(
            (r.copy_api_text for r in copy_rounds if r.copy_api_text.strip()),
            key=len,
            default="",
        )
        best_clip = max(
            (r.clipboard_text for r in copy_rounds if r.clipboard_text.strip()),
            key=len,
            default="",
        )
        transport_fail = diagnose_transport_mismatch(
            copy_api_text=best_api,
            clipboard_text=best_clip,
        )
        if transport_fail and not copy_fail:
            copy_fail = transport_fail
            self._log(f"[PW] Copy 通道诊断：{transport_fail}")

        dom_md = self._assistant_markdown_from_dom()
        dom_katex = self._assistant_text() or ""
        html_md = ""
        try:
            iso_html = getattr(self, "_last_isolated_copy_html", "") or ""
            if iso_html.strip():
                html_md = html_fragment_to_markdown(iso_html)
        except Exception:
            html_md = ""

        bundle = CaptureBundle(
            batch_id=self._capture_batch_id,
            copy_rounds=copy_rounds,
            copy_api_selected=copy_text if "copy_api" in copy_label else "",
            clipboard_selected=copy_text if copy_label.startswith("clipboard") else "",
            dom_markdown=(dom_md or "").strip(),
            dom_katex=(dom_katex or "").strip(),
            clipboard_html_md=(html_md or "").strip(),
            assistant_html=self._assistant_html_raw(),
            consensus_source=copy_label,
            consensus_text=copy_text,
            consensus_stable=copy_stable,
            failure_class=copy_fail,
            meta={
                "copy_rounds": len(copy_rounds),
                "copy_label": copy_label,
                "transport_diagnosis": transport_fail,
                "clipboard_isolate": True,
            },
        )

        if self._capture_output_dir and self._capture_batch_id is not None:
            attempt_dir = allocate_attempt_dir(
                self._capture_output_dir, self._capture_batch_id
            )
            bundle.attempt = int(attempt_dir.name.split("_")[-1])
            save_capture_bundle(attempt_dir, bundle)
            self._log(f"[PW] 证据已保存 -> {attempt_dir}")

        if copy_fail == "COPY_NOT_FIRED" and not copy_text.strip():
            self._log("[PW] Copy 未触发，尝试 DOM 兜底…")
        elif copy_fail == "EXTRACTION_UNSTABLE":
            self._log("[PW] Copy 2-of-3 不一致（EXTRACTION_UNSTABLE）")

        return bundle, copy_text, copy_label, copy_stable

    def _extract_via_copy(self) -> str:
        from app.vision_transcribe.browser.deepseek_ui import extract_via_copy_button

        self._log("[PW] 复制阶段：滚到底并确认无「继续生成」")
        self._scroll_chat_to_bottom()
        self._drain_continue_before_copy()

        page = self._require_page()
        from app.vision_transcribe.browser.clipboard_interceptor import (
            inject_clipboard_interceptor,
            set_clipboard_isolate,
        )

        inject_clipboard_interceptor(page)
        set_clipboard_isolate(page, True)
        self._log("[PW] 开始图识别/DOM 定位复制按钮…")
        text = extract_via_copy_button(
            page,
            config=self._ui_cfg,
            log=self._log,
            read_clipboard=self._read_clipboard_text,
            start_page=self._batch_start_page,
            end_page=self._batch_end_page,
        )
        if not text.strip():
            self._log("[PW] 复制按钮未读到内容，尝试 DOM 结构化抽取…")
            dom_md = self._assistant_markdown_from_dom()
            if dom_md.strip():
                text = dom_md
            elif self._copy_assistant_via_ctrl_c():
                from app.vision_transcribe.browser.deepseek_ui import (
                    _read_clipboard_when_stable,
                )

                text = _read_clipboard_when_stable(
                    self._read_clipboard_text, log=self._log
                )
        if text.strip():
            self._log(f"[PW] 复制成功，共 {len(text)} 字符")
            return text
        # 再点一次复制重试
        self._log("[PW] 首次复制未读到内容，重试…")
        page.wait_for_timeout(500)
        text2 = extract_via_copy_button(
            page,
            config=self._ui_cfg,
            log=self._log,
            read_clipboard=self._read_clipboard_text,
            start_page=self._batch_start_page,
            end_page=self._batch_end_page,
        )
        if text2.strip():
            self._log(f"[PW] 重试复制成功，共 {len(text2)} 字符")
        else:
            self._log("[PW] 重试复制仍失败")
        return text2

    def extract_response(self) -> str:
        from app.vision_transcribe.browser.html_to_markdown import html_fragment_to_markdown
        from app.vision_transcribe.browser.clipboard_html import read_system_clipboard_html
        from app.vision_transcribe.clipboard_sanitize import sanitize_vision_clipboard
        from app.vision_transcribe.transcript_quality import (
            looks_truncated_transcript,
            pick_best_transcript,
            transcript_rank,
        )
        from app.vision_transcribe.formula_integrity import formula_integrity_errors
        from app.vision_transcribe.capture.consensus import pick_extraction_consensus

        sp, ep = self._batch_start_page, self._batch_end_page

        self._log("[PW] 复制阶段：滚到底并确认无「继续生成」")
        self._scroll_chat_to_bottom()
        self._drain_continue_before_copy()

        bundle, copy_consensus, copy_label, copy_stable = self._collect_capture_bundle()

        clip_s = (copy_consensus or "").strip()
        dom_md_s = (bundle.dom_markdown or "").strip()
        dom_katex = (bundle.dom_katex or "").strip()
        dom_katex_chars = len(dom_katex)
        html_md_s = (bundle.clipboard_html_md or "").strip()

        if not clip_s and not copy_stable:
            dom_usable = transcript_rank(dom_md_s) >= 0
            if bundle.failure_class == "COPY_NOT_FIRED" and dom_usable:
                self._log(
                    f"[PW] Copy 未触发，DOM 已就绪（{len(dom_md_s)} 字），"
                    "跳过重复点复制"
                )
            else:
                legacy = self._extract_via_copy()
                if (legacy or "").strip():
                    clip_s = legacy.strip()
                    self._log(
                        f"[PW] CaptureBundle 未稳定，legacy 复制 {len(clip_s)} 字"
                    )

        source, best = pick_extraction_consensus(
            copy_text=clip_s,
            dom_md=dom_md_s,
            dom_katex=dom_katex,
            html_md=html_md_s,
        )
        if transcript_rank(best) < 0:
            source, best = pick_best_transcript(
                ("copy-consensus", clip_s),
                ("dom-md", dom_md_s),
                ("dom-katex", dom_katex),
                ("clipboard-html", html_md_s),
            )

        if transcript_rank(best) < 0:
            fc = bundle.failure_class or "EXTRACTION_CONFLICT"
            raise RuntimeError(
                f"未能获取完整 DeepSeek 转录（{fc}）。"
                f"Copy共识 {len(clip_s)} 字，DOM {len(dom_md_s)} 字，"
                f"KaTeX {dom_katex_chars} 字"
                f"（批次 PAGE {sp or '?'}-{ep or '?'}）。"
            )

        if bundle.failure_class == "EXTRACTION_UNSTABLE":
            alt_source, alt_best = pick_best_transcript(
                ("dom-md", dom_md_s),
                ("dom-katex", dom_katex),
                ("clipboard-html", html_md_s),
            )
            if (
                transcript_rank(alt_best) >= 0
                and len(alt_best) > len(clip_s) + max(800, int(len(clip_s) * 0.05))
            ):
                source, best = alt_source, alt_best
                self._log(
                    f"[PW] Copy 2-of-3 不一致，DOM 明显更长"
                    f"（{len(alt_best)} vs {len(clip_s)}），采用 {source}"
                )
            elif source.startswith("copy"):
                raise RuntimeError(
                    "Copy 2-of-3 不一致（EXTRACTION_UNSTABLE），禁止静默接受。"
                    f"Copy {len(clip_s)} 字，DOM {len(dom_md_s)} 字，"
                    f"KaTeX {dom_katex_chars} 字（PAGE {sp}-{ep}）。"
                )

        integrity_errs = formula_integrity_errors(best)
        if integrity_errs:
            raise RuntimeError(
                "公式完整性校验失败（禁止静默丢式）："
                + "; ".join(integrity_errs)
                + f"。Copy {len(clip_s)} 字，DOM {len(dom_md_s)} 字。"
            )

        if looks_truncated_transcript(best, start_page=sp, end_page=ep):
            raise RuntimeError(
                "未能获取完整 DeepSeek 转录（PAGE/字数未达标）。"
                f"Copy {len(clip_s)} 字，DOM {len(dom_md_s)} 字，"
                f"KaTeX {dom_katex_chars} 字（PAGE {sp}-{ep}）。"
            )

        from app.vision_transcribe.transcript_quality import model_degeneration_errors

        deg = model_degeneration_errors(best)
        if deg:
            raise RuntimeError(deg[0] + f"（PAGE {sp}-{ep}）")

        self._log(f"[PW] 采用 {source}（{len(best)} 字，copy_stable={copy_stable}）")

        sanitized = sanitize_vision_clipboard(best)
        self.last_extract_stats = {
            "source": source,
            "copy_consensus_label": copy_label,
            "copy_consensus_stable": copy_stable,
            "capture_failure_class": bundle.failure_class,
            "capture_attempt": bundle.attempt,
            "chars_clipboard": len(clip_s),
            "chars_dom_md": len(dom_md_s),
            "chars_clipboard_html": len(html_md_s),
            "chars_dom_katex": dom_katex_chars,
            "chars_selected": len(best),
            "chars_sanitized": len(sanitized),
            "peak_dom_katex": self._peak_dom_katex_chars,
            "batch_start_page": sp,
            "batch_end_page": ep,
        }
        return sanitized

    def _finish_batch_response(self) -> str:
        """等待输出 -> 滚到底 -> 复制 -> 返回 Markdown。"""
        self._pw_step("步骤6 等待 AI 输出完成")
        self.wait_response()
        self._pw_step("步骤7 滚到底部并点击复制")
        md = self.extract_response()
        self._pw_step(f"步骤8 已获取回答（{len(md)} 字符）")
        return md

    def _pw_step(self, msg: str) -> None:
        self._log(f"[PW] {msg}")

    def recopy_batch(self, prompt: str = "") -> AdapterResult:
        """Level-0：不重新上传，仅对当前对话重新 Capture。"""
        try:
            from app.vision_transcribe.transcript_quality import parse_batch_pages_from_prompt

            if prompt:
                self._batch_start_page, self._batch_end_page = (
                    parse_batch_pages_from_prompt(prompt)
                )
            self._ui_cfg = load_ui_config()
            self.ensure_browser()
            self._raise_if_needs_user()
            self._pw_step("Level-0 仅重新抽取（不重新上传）")
            self._scroll_chat_to_bottom()
            md = self.extract_response()
            self._pw_step(f"Level-0 抽取完成（{len(md)} 字符）")
            return AdapterResult(
                markdown=md,
                needs_user=False,
                extract_stats=self.last_extract_stats,
            )
        except NeedsUserError as e:
            return AdapterResult(markdown="", needs_user=True, message=str(e))
        except Exception as e:
            return AdapterResult(markdown="", needs_user=False, message=str(e))

    def submit_batch(self, images: list[Path], prompt: str) -> AdapterResult:
        try:
            from app.vision_transcribe.transcript_quality import parse_batch_pages_from_prompt

            self._batch_start_page, self._batch_end_page = parse_batch_pages_from_prompt(
                prompt
            )
            self._peak_dom_katex_chars = 0
            self.last_extract_stats = None
            self._ui_cfg = load_ui_config()
            self._pw_step("步骤1 连接浏览器")
            self.ensure_browser()
            self._raise_if_needs_user()
            if self._try_recorded_submit(images, prompt):
                md = self._finish_batch_response()
                self._pw_step("步骤9 本批完成")
                return AdapterResult(
                    markdown=md,
                    needs_user=False,
                    extract_stats=self.last_extract_stats,
                )
            self._pw_step("步骤2 开启新对话（内置 DOM）")
            self.new_chat()
            self._pw_step("步骤3 识图模式（内置 DOM）")
            self.set_vision_mode()
            from app.vision_transcribe.browser.dom_locator import (
                ensure_batch_prompt,
                fill_batch_prompt,
                prompt_present_in_composer,
                wait_for_upload_settled,
            )

            self._pw_step("步骤4 自动键入 Prompt")
            page = self._require_page()
            if not ensure_batch_prompt(page, prompt, log=self._log):
                raise RuntimeError("填写 Prompt 失败（找不到输入框或填写后校验未通过）")
            self._pw_step(f"步骤5 上传 {len(images)} 张页面图")
            self.upload_images(images)
            settled = wait_for_upload_settled(self._page, len(images), log=self._log)
            from app.vision_transcribe.browser.upload_guard import verify_upload_complete

            up_ok, up_err = verify_upload_complete(
                page, len(images), log=self._log, send_ready=settled
            )
            if not up_ok:
                raise RuntimeError(f"UploadGuard: {up_err}")
            if not prompt_present_in_composer(page, prompt):
                self._pw_step("步骤5b 上传后补填 Prompt")
                if not fill_batch_prompt(page, prompt, log=self._log):
                    raise RuntimeError("上传后补填 Prompt 失败")
            from app.vision_transcribe.browser.prompt_guard import verify_prompt_exact

            ok_prompt, perr = verify_prompt_exact(page, prompt, log=self._log)
            if not ok_prompt:
                if not fill_batch_prompt(page, prompt, log=self._log):
                    raise RuntimeError(f"PromptGuard: {perr}")
                ok_prompt, perr = verify_prompt_exact(page, prompt, log=self._log)
                if not ok_prompt:
                    raise RuntimeError(f"PromptGuard: {perr}")
            self._pw_step("步骤6 点击发送")
            from app.vision_transcribe.browser.dom_locator import click_send_fallback

            if not click_send_fallback(self._page, log=self._log, timeout_ms=120_000):
                raise RuntimeError("发送按钮一直不可用（图片可能未传完）")
            md = self._finish_batch_response()
            self._pw_step("步骤9 本批完成")
            return AdapterResult(
                markdown=md,
                needs_user=False,
                extract_stats=self.last_extract_stats,
            )
        except NeedsUserError as e:
            self._pw_step(f"需人工: {e}")
            return AdapterResult(markdown="", needs_user=True, message=str(e))

    def _try_recorded_submit(self, images: list[Path], prompt: str) -> bool:
        """若已录制演示流程，则按步骤回放（图片/Prompt 用运行时 batch 数据）。"""
        strategy = str(self._ui_cfg.get("click_strategy", "auto"))
        wf = self._ui_cfg.get("recorded_workflow")
        use = strategy == "recorded" or (
            strategy == "auto" and has_recorded_workflow(self._ui_cfg)
        )
        if not use or not isinstance(wf, dict) or not wf.get("enabled"):
            self._log(
                f"[录制] 未走回放：策略={strategy}，"
                f"enabled={bool(isinstance(wf, dict) and wf.get('enabled'))}"
            )
            return False
        n = len(wf.get("steps") or [])
        self._log(f"[录制] 使用 recorded_workflow（策略={strategy}，{n} 步）")
        page = self._require_page()
        self._pw_step("步骤2-5 按录制演示回放")
        ok = replay_submit_steps(
            page,
            wf,
            images=images,
            prompt=prompt,
            log=self._log,
        )
        if ok:
            return True
        self._log("[录制] 回放失败，回退到内置 DOM/模板定位")
        return False

    # —— 内部 ——
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

    def _is_generating(self) -> bool:
        from app.vision_transcribe.browser.dom_locator import is_ai_generating

        return is_ai_generating(self._page)

    _KATEX_EXTRACT_JS = """
    () => {
      const promptNeedles = ['你正在执行 PDF', '本批次为 PAGE', '高保真内容转录任务'];
      const isUserPrompt = (t) => {
        if (!t) return true;
        let hits = 0;
        for (const s of promptNeedles) if (t.includes(s)) hits++;
        if (hits >= 2 && t.length < 4500) return true;
        if (t.includes('开启新对话') && t.length < 1200) return true;
        return false;
      };
      const selectors = [
        '[data-message-author-role="assistant"]',
        '.ds-message',
        '.markdown-body',
        '.assistant',
      ];
      let root = null;
      for (const sel of selectors) {
        const nodes = document.querySelectorAll(sel);
        for (let i = nodes.length - 1; i >= 0; i--) {
          const t = nodes[i].innerText || '';
          if (!isUserPrompt(t) && t.trim().length > 40) {
            root = nodes[i];
            break;
          }
        }
        if (root) break;
      }
      if (!root) return '';

      const clone = root.cloneNode(true);
      const replaceKatex = (katexEl) => {
        const ann = katexEl.querySelector(
          'annotation[encoding="application/x-tex"], semantics annotation'
        );
        const tex = ann && (ann.textContent || '').trim();
        const isDisplay =
          katexEl.classList.contains('katex-display') ||
          (katexEl.closest && katexEl.closest('.katex-display') !== null);
        const text = tex
          ? (isDisplay ? '\\n$$\\n' + tex + '\\n$$\\n' : '$' + tex + '$')
          : (() => {
              const raw = (katexEl.innerText || katexEl.textContent || '').trim();
              if (!raw) return '';
              return isDisplay ? '\\n$$\\n' + raw + '\\n$$\\n' : '$' + raw + '$';
            })();
        katexEl.replaceWith(document.createTextNode(text));
      };
      clone.querySelectorAll('.katex-display').forEach(replaceKatex);
      clone.querySelectorAll('.katex').forEach((el) => {
        if (!el.closest('.katex-display')) replaceKatex(el);
      });
      return (clone.innerText || '').replace(/\\r\\n/g, '\\n');
    }
    """

    _ASSISTANT_DOM_MD_JS = """
    () => {
      const promptNeedles = ['你正在执行 PDF', '本批次为 PAGE', '高保真内容转录任务'];
      const isUserPrompt = (t) => {
        if (!t) return true;
        let hits = 0;
        for (const s of promptNeedles) if (t.includes(s)) hits++;
        if (hits >= 2 && t.length < 4500) return true;
        if (t.includes('开启新对话') && t.length < 1200) return true;
        return false;
      };
      const selectors = [
        '[data-message-author-role="assistant"]',
        '.ds-message',
        '.markdown-body',
        '.assistant',
      ];
      let root = null;
      for (const sel of selectors) {
        const nodes = document.querySelectorAll(sel);
        for (let i = nodes.length - 1; i >= 0; i--) {
          const t = nodes[i].innerText || '';
          if (!isUserPrompt(t) && t.trim().length > 40) {
            root = nodes[i];
            break;
          }
        }
        if (root) break;
      }
      if (!root) return '';

      const clone = root.cloneNode(true);
      clone.querySelectorAll('button, svg, [aria-label*="复制"], [aria-label*="Copy"]').forEach((el) => {
        el.remove();
      });

      const replaceKatex = (katexEl) => {
        const ann = katexEl.querySelector(
          'annotation[encoding="application/x-tex"], semantics annotation'
        );
        const tex = ann && (ann.textContent || '').trim();
        const isDisplay =
          katexEl.classList.contains('katex-display') ||
          (katexEl.closest && katexEl.closest('.katex-display') !== null);
        const text = tex
          ? (isDisplay ? '\\n$$\\n' + tex + '\\n$$\\n' : '$' + tex + '$')
          : (() => {
              const raw = (katexEl.innerText || katexEl.textContent || '').trim();
              if (!raw) return '';
              return isDisplay ? '\\n$$\\n' + raw + '\\n$$\\n' : '$' + raw + '$';
            })();
        katexEl.replaceWith(document.createTextNode(text));
      };
      clone.querySelectorAll('.katex-display').forEach(replaceKatex);
      clone.querySelectorAll('.katex').forEach((el) => {
        if (!el.closest('.katex-display')) replaceKatex(el);
      });

      const tableToMd = (table) => {
        const rows = [];
        table.querySelectorAll('tr').forEach((tr) => {
          const cells = [];
          tr.querySelectorAll('th, td').forEach((c) => {
            cells.push((c.innerText || '').trim().replace(/\\|/g, '\\\\|').replace(/\\n+/g, ' '));
          });
          if (cells.length) rows.push(cells);
        });
        if (!rows.length) return '';
        const lines = rows.map((r) => '| ' + r.join(' | ') + ' |');
        if (lines.length > 1) {
          lines.splice(1, 0, '| ' + rows[0].map(() => '---').join(' | ') + ' |');
        }
        return '\\n\\n' + lines.join('\\n') + '\\n\\n';
      };

      const walk = (node) => {
        if (!node) return '';
        if (node.nodeType === 8) {
          const c = (node.nodeValue || node.textContent || '').trim();
          if (/PDF2MD:/i.test(c)) {
            const body = c.replace(/^<!--\\s*/, '').replace(/\\s*-->$/, '');
            return '\\n<!-- ' + body + ' -->\\n';
          }
          return '';
        }
        if (node.nodeType === 3) {
          let s = node.textContent || '';
          if (s.indexOf('PDF2MD:') >= 0 && s.indexOf('&lt;!--') >= 0) {
            s = s.replace(/&lt;!--/g, '<!--').replace(/--&gt;/g, '-->');
          }
          return s;
        }
        if (node.nodeType !== 1) return '';
        const tag = node.tagName.toLowerCase();
        if (tag === 'br') return '\\n';
        if (tag === 'h1') return '\\n\\n# ' + inner(node).trim() + '\\n\\n';
        if (tag === 'h2') return '\\n\\n## ' + inner(node).trim() + '\\n\\n';
        if (tag === 'h3') return '\\n\\n### ' + inner(node).trim() + '\\n\\n';
        if (tag === 'h4') return '\\n\\n#### ' + inner(node).trim() + '\\n\\n';
        if (tag === 'p') return '\\n\\n' + inner(node).trim() + '\\n\\n';
        if (tag === 'li') return '\\n- ' + inner(node).trim();
        if (tag === 'table') return tableToMd(node);
        if (tag === 'pre') {
          const t = (node.innerText || '').trim();
          return t ? '\\n\\n```\\n' + t + '\\n```\\n\\n' : '';
        }
        if (tag === 'code' && node.parentElement && node.parentElement.tagName !== 'PRE') {
          return '`' + (node.innerText || '') + '`';
        }
        if (tag === 'strong' || tag === 'b') return '**' + inner(node) + '**';
        if (tag === 'em' || tag === 'i') return '*' + inner(node) + '*';
        if (tag === 'a') {
          const href = node.getAttribute('href') || '';
          const label = inner(node).trim();
          if (href && href !== label) return '[' + label + '](' + href + ')';
          return label;
        }
        if (tag === 'img') {
          const src = node.getAttribute('src') || '';
          const alt = node.getAttribute('alt') || 'Figure';
          return src ? '\\n\\n![' + alt + '](' + src + ')\\n\\n' : '';
        }
        return inner(node);
      };

      const inner = (node) => {
        let s = '';
        for (const ch of node.childNodes) s += walk(ch);
        return s;
      };

      let md = inner(clone).replace(/\\r\\n/g, '\\n');
      md = md.replace(/\\n{3,}/g, '\\n\\n').trim();
      return md;
    }
    """

    def _assistant_markdown_from_dom(self) -> str:
        """从 assistant 渲染 DOM 还原 Markdown（含表格/标题），避免 inner_text 压平。"""
        page = self._page
        if page is None:
            return ""
        try:
            text = page.evaluate(self._ASSISTANT_DOM_MD_JS)
            if not str(text or "").strip():
                return ""
            self._log(f"[PW] DOM 结构化抽取（{len(str(text))} 字）")
            return str(text)
        except Exception as e:
            self._log_dom_eval_error("DOM 结构化抽取", e)
            if self._is_fatal_page_eval_error(e):
                self._raise_if_page_disconnected()
            return ""

    def _assistant_text(self) -> str:
        """优先从 KaTeX annotation 还原 LaTeX；失败才用 inner_text（会产生竖排碎片）。"""
        page = self._page
        if page is None:
            return ""
        try:
            text = page.evaluate(self._KATEX_EXTRACT_JS)
            if str(text or "").strip():
                from app.vision_transcribe.browser.katex_scrap import has_dom_katex_scrap

                if not has_dom_katex_scrap(str(text)):
                    self._log("[PW] DOM 抽取：KaTeX annotation → LaTeX")
                    return str(text)
        except Exception as e:
            self._log_dom_eval_error("KaTeX annotation 抽取", e)
            if self._is_fatal_page_eval_error(e):
                self._raise_if_page_disconnected()

        selectors = [
            '[data-message-author-role="assistant"]',
            ".ds-message",
            ".markdown-body",
            ".assistant",
            "div[class*='message']",
        ]
        from app.vision_transcribe.clipboard_sanitize import looks_like_user_prompt

        for sel in selectors:
            try:
                locs = page.locator(sel)
                n = locs.count()
                if n <= 0:
                    continue
                raw = ""
                for i in range(n - 1, -1, -1):
                    cand = locs.nth(i).inner_text(timeout=2000)
                    if not (cand or "").strip():
                        continue
                    if looks_like_user_prompt(cand):
                        continue
                    raw = cand
                    break
                if not raw.strip():
                    continue
                from app.vision_transcribe.browser.katex_scrap import has_dom_katex_scrap

                if has_dom_katex_scrap(raw):
                    self._log(
                        "[PW] DOM inner_text 含 KaTeX 竖排碎片，"
                        "不可用于转录（请用复制按钮/系统剪贴板）"
                    )
                return raw
            except Exception:
                continue
        try:
            from app.vision_transcribe.browser.assistant_root import (
                assistant_text_from_root,
            )

            root_text = assistant_text_from_root(page)
            if str(root_text or "").strip():
                self._log("[PW] DOM 抽取：AssistantRoot 兜底")
                return str(root_text)
        except Exception:
            pass
        try:
            return page.inner_text("body")
        except Exception:
            return ""

    def _first_locator(self, factories: list):
        page = self._page
        for factory in factories:
            try:
                loc = factory()
                if loc.count() > 0:
                    return loc.first
            except Exception:
                continue
        return None

    def _click_first(self, factories: list, *, timeout_ms: int, optional: bool) -> bool:
        page = self._page
        last_err = ""
        for factory in factories:
            try:
                loc = factory()
                if loc.count() == 0:
                    continue
                target = loc.first
                if not target.is_visible():
                    continue
                target.scroll_into_view_if_needed(timeout=3000)
                target.click(timeout=timeout_ms)
                return True
            except Exception as e:
                last_err = str(e)
                try:
                    target = factory().first
                    if target.count() if hasattr(target, "count") else True:
                        factory().first.click(force=True, timeout=timeout_ms)
                        return True
                except Exception:
                    pass
                continue
        if optional:
            if last_err:
                self._log(f"DOM 点击跳过(optional): {last_err[:120]}")
            return False
        raise RuntimeError(
            f"找不到可点击控件: {last_err[:200] or '无匹配 locator'}"
        )
