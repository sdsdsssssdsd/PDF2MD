"""DeepSeek Web SiteAdapter：编排 session / upload / wait / capture。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.vision_transcribe.browser.base import (
    AdapterResult,
    NeedsUserError,
    VisionWebAdapter,
)
from app.vision_transcribe.browser.capture import DeepSeekCaptureMixin
from app.vision_transcribe.browser.contracts.fingerprint import (
    DEEPSEEK_SITE_ADAPTER,
    IncompatibleSiteError,
    verify_logged_in_contract,
)
from app.vision_transcribe.browser.deepseek_ui import (
    has_recorded_workflow,
    load_ui_config,
)
from app.vision_transcribe.browser.dom_replay import replay_submit_steps
from app.vision_transcribe.browser.locator import DeepSeekLocatorMixin
from app.vision_transcribe.browser.policies.contamination import DeepSeekContaminationMixin
from app.vision_transcribe.browser.policies.retry import DeepSeekRetryMixin
from app.vision_transcribe.browser.session import DeepSeekSessionMixin
from app.vision_transcribe.browser.uploader import DeepSeekUploaderMixin


class DeepSeekPlaywrightAdapter(
    DeepSeekSessionMixin,
    DeepSeekLocatorMixin,
    DeepSeekUploaderMixin,
    DeepSeekCaptureMixin,
    DeepSeekRetryMixin,
    DeepSeekContaminationMixin,
    VisionWebAdapter,
):
    site_adapter = DEEPSEEK_SITE_ADAPTER

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
            verify_logged_in_contract(self._page, logged_in=self._looks_logged_in())
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
        except IncompatibleSiteError as e:
            self._pw_step(str(e))
            raise
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

