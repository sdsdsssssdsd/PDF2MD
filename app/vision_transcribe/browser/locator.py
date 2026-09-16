"""DeepSeek Web：locator 容错点击。"""
from __future__ import annotations


class DeepSeekLocatorMixin:
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
