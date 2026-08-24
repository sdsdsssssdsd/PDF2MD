"""登录检测不误报「退出登录」。"""
from __future__ import annotations

from unittest.mock import MagicMock

from app.vision_transcribe.browser.deepseek_web import DeepSeekPlaywrightAdapter


def test_looks_logged_in_when_chat_ui_visible():
    adapter = DeepSeekPlaywrightAdapter(profile_dir=MagicMock())
    page = MagicMock()
    loc = MagicMock()
    loc.count.return_value = 1
    loc.first.is_visible.return_value = True
    page.get_by_text.return_value = loc
    adapter._page = page
    assert adapter._looks_logged_in() is True


def test_needs_user_skipped_when_logged_in():
    adapter = DeepSeekPlaywrightAdapter(profile_dir=MagicMock())
    adapter._page = MagicMock()
    adapter._looks_logged_in = MagicMock(return_value=True)  # type: ignore[method-assign]
    adapter._raise_if_needs_user()  # should not raise
