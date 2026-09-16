"""DeepSeek Web：图片上传与 Prompt 发送。"""
from __future__ import annotations

from pathlib import Path

from app.vision_transcribe.browser.deepseek_ui import smart_click


class DeepSeekUploaderMixin:
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
