"""DeepSeek Web：复制 / DOM / CaptureBundle。"""
from __future__ import annotations

import time
from pathlib import Path

from app.vision_transcribe.browser.base import AdapterResult, NeedsUserError
from app.vision_transcribe.browser.deepseek_ui import load_ui_config


class DeepSeekCaptureMixin:
    def set_capture_context(self, output_dir: Path, batch_id: int) -> None:
        """Pipeline 注入：保存 CaptureBundle 到 .vision/batches/…/attempts/。"""
        self._capture_output_dir = Path(output_dir)
        self._capture_batch_id = int(batch_id)
    def _scroll_chat_to_bottom(self) -> None:
        """输出完毕后滚到对话底部，便于露出复制按钮。"""
        from app.vision_transcribe.browser.deepseek_ui import scroll_chat_to_bottom

        scroll_chat_to_bottom(self._require_page(), log=self._log)
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
