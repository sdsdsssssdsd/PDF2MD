"""DeepSeek Web：Prompt/侧栏污染与模型退化策略。"""
from __future__ import annotations

import time


class DeepSeekContaminationMixin:
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
