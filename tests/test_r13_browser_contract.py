"""R13：Browser SiteAdapter / DOM contract。"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.core.browser import (
    DEEPSEEK_SITE_ADAPTER,
    INCOMPATIBLE_SITE,
    IncompatibleSiteError,
    verify_logged_in_contract,
)
from app.vision_transcribe.browser.contracts.fixtures import (
    adapter_contract_dict,
    fake_deepseek_fixture,
)
from app.vision_transcribe.browser.deepseek_web import DeepSeekPlaywrightAdapter


def test_deepseek_web_is_facade():
    text = Path("app/vision_transcribe/browser/deepseek_web.py").read_text(encoding="utf-8")
    assert "class DeepSeekPlaywrightAdapter" not in text
    assert "from app.vision_transcribe.browser.adapter.deepseek import DeepSeekPlaywrightAdapter" in text
    assert DeepSeekPlaywrightAdapter.site_adapter.adapter_id == "vision.deepseek_web"
    assert DeepSeekPlaywrightAdapter.site_adapter.adapter_version == "1.0"


def test_site_adapter_version_fields():
    ver = DEEPSEEK_SITE_ADAPTER
    assert ver.selector_fingerprint
    assert ver.dom_fingerprint
    assert ver.last_verified
    payload = adapter_contract_dict()
    assert payload["adapter_id"] == "vision.deepseek_web"
    assert fake_deepseek_fixture().is_file()


def test_incompatible_site_when_logged_in_without_landmarks():
    page = MagicMock()
    loc = MagicMock()
    loc.count.return_value = 0
    loc.first.is_visible.return_value = False
    page.get_by_text.return_value = loc
    page.locator.return_value = loc
    with pytest.raises(IncompatibleSiteError) as ei:
        verify_logged_in_contract(page, logged_in=True)
    assert ei.value.code == INCOMPATIBLE_SITE
    assert verify_logged_in_contract(page, logged_in=False) == []


def test_fatal_page_eval_still_on_adapter():
    err = RuntimeError("Target page, context or browser has been closed")
    assert DeepSeekPlaywrightAdapter._is_fatal_page_eval_error(err)
