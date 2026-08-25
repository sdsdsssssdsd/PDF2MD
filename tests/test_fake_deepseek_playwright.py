"""假 DeepSeek 页面 Playwright 集成测试（执行3 §四十二）。"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS")),
    reason="needs local Playwright browser (skipped in CI)",
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "fake_deepseek.html"


@pytest.fixture(scope="module")
def playwright_browser():
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


def test_fake_deepseek_copy_and_clipboard_hook(playwright_browser):
    context = playwright_browser.new_context()
    context.grant_permissions(["clipboard-read", "clipboard-write"])
    page = context.new_page()
    page.goto(FIXTURE.as_uri())
    page.click("#copyBtn")
    page.wait_for_timeout(300)
    clip = page.evaluate("() => navigator.clipboard.readText()")
    assert "PDF2MD:PAGE" in clip
    gen = page.evaluate(
        "() => (window.__PDF2MD_COPY_CAPTURE__ || {}).generation || 0"
    )
    assert int(gen) >= 1
    context.close()


def test_fake_deepseek_upload_attachment_count(playwright_browser):
    from app.vision_transcribe.browser.upload_guard import count_composer_attachments

    context = playwright_browser.new_context()
    page = context.new_page()
    page.goto(FIXTURE.as_uri() + "?attach=10")
    page.wait_for_timeout(200)
    n = count_composer_attachments(page)
    assert n >= 8
    context.close()


def test_fake_deepseek_prompt_guard(playwright_browser):
    from app.vision_transcribe.browser.prompt_guard import verify_prompt_exact

    prompt = "本批次为 PAGE 0001 至 PAGE 0010 的测试 Prompt。" * 3
    context = playwright_browser.new_context()
    page = context.new_page()
    page.goto(FIXTURE.as_uri())
    page.fill("#composer", prompt)
    ok, err = verify_prompt_exact(page, prompt)
    assert ok, err
    context.close()
