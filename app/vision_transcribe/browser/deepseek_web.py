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

    def _batch_transcript_complete(self, text: str | None = None) -> bool:
        from app.vision_transcribe.transcript_quality import batch_transcript_complete

        t = self._assistant_text() if text is None else text
        return batch_transcript_complete(
            t or "",
            start_page=self._batch_start_page,
            end_page=self._batch_end_page,
        )

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

    def set_vision_mode(self) -> None:
        """识图模式 = 三按钮最右。L1 DOM → L2 截图 → L3 人工。"""
        page = self._require_page()
        dom = [
            lambda: page.get_by_role("button", name="识图模式"),
            lambda: page.get_by_text("识图模式", exact=True),
            lambda: page.locator("button", has_text="识图模式"),
            lambda: page.get_by_role("button", name="识图"),
        ]

        def _dom_click(fs, optional: bool) -> bool:
            if self._click_mode_trio_rightmost(page):
                return True
            return self._click_first(fs, timeout_ms=10000, optional=optional)

        if smart_click(
            page,
            "vision_mode",
            dom_factories=dom,
            config=self._ui_cfg,
            log=self._log,
            dom_click_fn=_dom_click,
        ):
            time.sleep(0.6)
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

        resume=True：复制阶段续跑「继续生成」后调用，避免 saw_generating 未置位而空转。
        """
        from app.vision_transcribe.browser.deepseek_ui import (
            click_continue_generate_if_visible,
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
        max_continue = 24
        saw_generating = bool(resume)
        loop_start = time.monotonic()
        last_log = 0.0

        while time.monotonic() < deadline:
            self._raise_if_needs_user()

            # 生成中也可能出现「继续生成」——不滚底误点；仅点可见的继续生成
            if click_continue_generate_if_visible(
                page, config=self._ui_cfg, log=None
            ):
                continue_clicks += 1
                if continue_clicks > max_continue:
                    raise RuntimeError("「继续生成」点击次数过多，请检查页面状态")
                self._log(f"[PW] 已点击「继续生成」（{continue_clicks}）")
                stable_since = None
                last_text = ""
                saw_generating = True
                time.sleep(0.35)
                continue

            generating = self._is_generating()
            if generating:
                saw_generating = True
                stable_since = None
                now = time.monotonic()
                if now - last_log > 8.0:
                    self._log("[PW] 生成中…")
                    last_log = now
                time.sleep(0.45)
                continue

            if not saw_generating:
                now = time.monotonic()
                if resume or (now - loop_start) > 12.0:
                    saw_generating = True
                elif now - last_log > 6.0:
                    self._log("[PW] 等待生成状态…")
                    last_log = now
                time.sleep(0.35)
                continue

            # —— 结束：先滚到底，再在底部看结束特征 ——
            scroll_chat_to_bottom(page, log=None)
            now = time.monotonic()
            send_gray = is_send_composer_gray(page, config=self._ui_cfg)
            has_continue = is_continue_generate_visible(page, config=self._ui_cfg)
            toolbar = match_action_toolbar_on_page(page, config=self._ui_cfg)
            if now - last_log > 5.0:
                self._log(
                    "[PW] 收尾检查：滚到底后 "
                    f"发送灰={'是' if send_gray else '否'}，"
                    f"继续生成={'有' if has_continue else '无'}，"
                    f"操作栏={'有' if toolbar else '无'}"
                )
                last_log = now

            if has_continue:
                if click_continue_generate_if_visible(
                    page, config=self._ui_cfg, log=self._log
                ):
                    continue_clicks += 1
                    stable_since = None
                    last_text = ""
                    time.sleep(0.4)
                    continue
                stable_since = None
                time.sleep(0.35)
                continue

            # 结束判定细节紧跟周期状态日志，避免刷屏
            detail_log = self._log if (now - last_log) < 0.05 else None
            if is_generation_fully_done(
                page,
                config=self._ui_cfg,
                scroll_first=False,
                log=detail_log,
            ):
                text = self._assistant_text()
                if self._batch_transcript_complete(text):
                    self._log(
                        "[PW] 生成完毕（已滚到底：发送灰 + 无继续生成 + 操作栏/复制）"
                    )
                    return
                self._log(
                    f"[PW] 结束特征已满足但转录不完整（{len(text or '')} 字），"
                    "继续等待或尝试「继续生成」…"
                )
                if click_continue_generate_if_visible(
                    page, config=self._ui_cfg, log=self._log
                ):
                    continue_clicks += 1
                    stable_since = None
                    last_text = ""
                    saw_generating = True
                    time.sleep(0.4)
                    continue
                stable_since = None
                time.sleep(0.6)
                continue

            text = self._assistant_text()
            if text:
                self._peak_dom_katex_chars = max(
                    self._peak_dom_katex_chars, len(text)
                )
            content_ok = looks_like_vision_response(text) or (
                bool(text.strip()) and len(text.strip()) >= 200
            )

            # 弱条件兜底：滚到底后发送已灰、无继续生成、内容稳定
            if send_gray and content_ok and not has_continue:
                if text == last_text and text.strip():
                    if stable_since is None:
                        stable_since = time.monotonic()
                    elif (time.monotonic() - stable_since) * 1000 >= self.response_stable_ms:
                        if self._batch_transcript_complete(text):
                            self._log(
                                "[PW] 生成完毕（滚到底+发送灰+内容稳定"
                                + ("+操作栏" if toolbar else "·操作栏未识别")
                                + "）"
                            )
                            return
                        self._log(
                            f"[PW] 内容已稳定但转录不完整（{len(text)} 字），继续等待…"
                        )
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
        """读剪贴板：优先保留 Markdown 结构的 plain/HTML。"""
        page = self._require_page()
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
        """仅复制最后一条 assistant 回答（禁止 Ctrl+A 全页）。"""
        page = self._require_page()
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
            self._log(f"[PW] assistant  scoped 复制失败: {e}")
        return ""

    def _copy_assistant_via_ctrl_c(self) -> bool:
        """兼容旧名：改为 scoped 复制，不再 Ctrl+A 全页。"""
        text = self._copy_assistant_scoped()
        if text.strip():
            return True
        self._log("[PW] scoped 复制未拿到内容")
        return False

    def _extract_via_copy(self) -> str:
        from app.vision_transcribe.browser.deepseek_ui import extract_via_copy_button

        self._log("[PW] 复制阶段：滚到底并确认无「继续生成」")
        self._scroll_chat_to_bottom()
        page = self._require_page()
        # 再确认一次没有「继续生成」
        from app.vision_transcribe.browser.deepseek_ui import (
            click_continue_generate_if_visible,
            is_continue_generate_visible,
            is_generation_fully_done,
        )

        for attempt in range(3):
            if not is_continue_generate_visible(page, config=self._ui_cfg):
                break
            page.wait_for_timeout(600 if attempt == 0 else 400)
            self._scroll_chat_to_bottom()
            page.wait_for_timeout(350)
            if not is_continue_generate_visible(page, config=self._ui_cfg):
                break
            if is_generation_fully_done(
                page,
                config=self._ui_cfg,
                scroll_first=False,
                log=self._log,
            ):
                self._log(
                    "[PW] 复制阶段：结束特征已满足，跳过误报的「继续生成」"
                )
                break
            self._log("[PW] 复制前仍有「继续生成」，先点击…")
            if click_continue_generate_if_visible(
                page, config=self._ui_cfg, log=self._log
            ):
                self.wait_response(resume=True)
                self._scroll_chat_to_bottom()
            else:
                break

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
        from app.vision_transcribe.browser.deepseek_ui import (
            _read_clipboard_when_stable,
        )
        from app.vision_transcribe.browser.html_to_markdown import html_fragment_to_markdown
        from app.vision_transcribe.browser.clipboard_html import read_system_clipboard_html
        from app.vision_transcribe.clipboard_sanitize import sanitize_vision_clipboard
        from app.vision_transcribe.transcript_quality import (
            looks_truncated_transcript,
            pick_best_transcript,
            transcript_rank,
        )
        from app.vision_transcribe.formula_integrity import formula_integrity_errors

        sp, ep = self._batch_start_page, self._batch_end_page

        clip = self._extract_via_copy()
        clip_s = (clip or "").strip()

        dom_md = self._assistant_markdown_from_dom()
        dom_md_s = (dom_md or "").strip()

        dom_katex = (self._assistant_text() or "").strip()
        dom_katex_chars = len(dom_katex)

        html_md = ""
        try:
            html_md = html_fragment_to_markdown(read_system_clipboard_html())
        except Exception:
            html_md = ""
        html_md_s = (html_md or "").strip()

        source, best = pick_best_transcript(
            ("clipboard", clip_s),
            ("dom-md", dom_md_s),
            ("dom-katex", dom_katex),
            ("clipboard-html", html_md_s),
        )

        if transcript_rank(best) < 0:
            raise RuntimeError(
                "未能获取完整 DeepSeek 转录（复制截断或结构丢失）。"
                f"剪贴板 {len(clip_s)} 字，DOM {len(dom_md_s)} 字，"
                f"KaTeX {dom_katex_chars} 字"
                f"（批次 PAGE {sp or '?'}-{ep or '?'}）。"
                "请确认回答已生成完毕并重试。"
            )

        integrity_errs = formula_integrity_errors(best)
        if integrity_errs:
            raise RuntimeError(
                "公式完整性校验失败（禁止静默丢式）："
                + "; ".join(integrity_errs)
                + f"。剪贴板 {len(clip_s)} 字，DOM {len(dom_md_s)} 字，"
                f"KaTeX {dom_katex_chars} 字。请重试并确保复制按钮成功。"
            )

        if looks_truncated_transcript(
            best, start_page=sp, end_page=ep
        ):
            raise RuntimeError(
                "未能获取完整 DeepSeek 转录（复制截断或结构丢失）。"
                f"剪贴板 {len(clip_s)} 字，DOM {len(dom_md_s)} 字，"
                f"KaTeX {dom_katex_chars} 字"
                f"（批次 PAGE {sp or '?'}-{ep or '?'}）。"
                "请确认回答已生成完毕并重试。"
            )

        if source != "clipboard" and len(clip_s) > 500:
            self._log(
                f"[PW] 弃用剪贴板 {len(clip_s)} 字，采用 {source}（{len(best)} 字）"
            )
        else:
            self._log(f"[PW] 使用 {source}（{len(best)} 字）")

        sanitized = sanitize_vision_clipboard(best)
        self.last_extract_stats = {
            "source": source,
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
            wait_for_upload_settled(self._page, len(images), log=self._log)
            if not prompt_present_in_composer(page, prompt):
                self._pw_step("步骤5b 上传后补填 Prompt")
                if not fill_batch_prompt(page, prompt, log=self._log):
                    raise RuntimeError("上传后补填 Prompt 失败")
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
      const selectors = [
        '[data-message-author-role="assistant"]',
        '.ds-message',
        '.markdown-body',
        '.assistant',
      ];
      let root = null;
      for (const sel of selectors) {
        const nodes = document.querySelectorAll(sel);
        if (nodes.length) root = nodes[nodes.length - 1];
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
      const selectors = [
        '[data-message-author-role="assistant"]',
        '.ds-message',
        '.markdown-body',
        '.assistant',
      ];
      let root = null;
      for (const sel of selectors) {
        const nodes = document.querySelectorAll(sel);
        if (nodes.length) root = nodes[nodes.length - 1];
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
        if (node.nodeType === 3) return node.textContent || '';
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
            self._log(f"[PW] DOM 结构化抽取失败: {e}")
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
            self._log(f"[PW] KaTeX annotation 抽取失败: {e}")

        selectors = [
            '[data-message-author-role="assistant"]',
            ".ds-message",
            ".markdown-body",
            ".assistant",
            "div[class*='message']",
        ]
        for sel in selectors:
            try:
                locs = page.locator(sel)
                n = locs.count()
                if n <= 0:
                    continue
                raw = locs.nth(n - 1).inner_text(timeout=2000)
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
