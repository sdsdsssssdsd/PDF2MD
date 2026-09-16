"""DeepSeek Web：继续生成 / 重试 / 等待完成。"""
from __future__ import annotations

import time


class DeepSeekRetryMixin:
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
    def _is_generating(self) -> bool:
        from app.vision_transcribe.browser.dom_locator import is_ai_generating

        return is_ai_generating(self._page)
