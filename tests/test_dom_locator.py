"""DOM 定位描述与录制回放单元测试。"""
from __future__ import annotations

from app.vision_transcribe.browser.deepseek_ui import has_recorded_workflow
from app.vision_transcribe.browser.dom_replay import workflow_enabled


def test_workflow_enabled_empty():
    assert not workflow_enabled({})
    assert not workflow_enabled({"recorded_workflow": {"enabled": False, "steps": []}})


def test_workflow_enabled_with_steps():
    cfg = {
        "recorded_workflow": {
            "enabled": True,
            "steps": [{"id": "vision_mode", "action": "click", "locators": []}],
        }
    }
    assert workflow_enabled(cfg)
    assert has_recorded_workflow(cfg)


def test_default_config_has_recorded_workflow():
    from app.vision_transcribe.browser.deepseek_ui import _default_config

    d = _default_config()
    assert "recorded_workflow" in d
    assert d["recorded_workflow"]["enabled"] is False


def test_capture_click_descriptor_uses_set_default_timeout_not_kwarg():
    from unittest.mock import MagicMock

    from app.vision_transcribe.browser.dom_locator import capture_click_descriptor

    page = MagicMock()
    page.evaluate.return_value = {"strategies": [{"strategy": "text", "text": "识图模式"}]}
    hit = capture_click_descriptor(page, timeout_ms=12_000)
    assert hit["strategies"]
    page.set_default_timeout.assert_any_call(12_000)
    page.set_default_timeout.assert_any_call(30_000)
    _args, kwargs = page.evaluate.call_args
    assert "timeout" not in kwargs


def test_record_guide_steps_cover_batch_flow():
    from app.vision_transcribe.browser.dom_locator import RECORD_GUIDE_STEPS

    ids = [s[0] for s in RECORD_GUIDE_STEPS]
    assert ids == ["new_chat", "vision_mode", "prompt"]
    actions = {s[0]: s[1] for s in RECORD_GUIDE_STEPS}
    assert actions["prompt"] == "click"
    assert "send" not in ids


def test_replay_order_inserts_auto_steps():
    from app.vision_transcribe.browser.dom_locator import RUNTIME_AUTO_STEPS

    assert [s[0] for s in RUNTIME_AUTO_STEPS] == [
        "auto_fill_prompt",
        "auto_upload",
        "auto_send",
    ]


def test_fill_prompt_fallback_order():
    from unittest.mock import MagicMock

    from app.vision_transcribe.browser.dom_locator import fill_prompt_fallback

    page = MagicMock()
    ph = MagicMock()
    ph.count.return_value = 1
    ph.first.is_visible.return_value = True
    ph.first.input_value.return_value = "hello world"
    page.get_by_placeholder.side_effect = lambda p: (
        ph if p == "给 DeepSeek 发送消息" else MagicMock(count=MagicMock(return_value=0))
    )
    assert fill_prompt_fallback(page, "hello world")
    ph.first.fill.assert_called_once()


def test_is_ai_generating_uses_stop_template():
    from unittest.mock import MagicMock

    from app.vision_transcribe.browser.dom_locator import is_ai_generating

    page = MagicMock()
    page.evaluate.return_value = True
    assert is_ai_generating(page)


def test_stop_image_confirmed_beats_send():
    from unittest.mock import MagicMock, patch

    import numpy as np

    from app.vision_transcribe.browser.deepseek_ui import is_stop_image_confirmed_at

    page = MagicMock()
    screen = np.zeros((400, 400, 3), dtype=np.uint8)

    def _match(_screen, _cfg, key):
        if key == "stop":
            return (0.82, 100, 200)
        if key == "send":
            return (0.70, 102, 198)
        return None

    with patch(
        "app.vision_transcribe.browser.deepseek_ui._match_template_key_on_screen",
        side_effect=_match,
    ):
        assert is_stop_image_confirmed_at(page, 100, 200, screen=screen)

    with patch(
        "app.vision_transcribe.browser.deepseek_ui._match_template_key_on_screen",
        side_effect=lambda _s, _c, key: (
            (0.80, 100, 200) if key == "stop" else (0.79, 100, 200)
        ),
    ):
        assert not is_stop_image_confirmed_at(page, 100, 200, screen=screen)


def test_stop_button_near():
    from unittest.mock import MagicMock, patch

    import numpy as np

    from app.vision_transcribe.browser.deepseek_ui import is_stop_button_near

    page = MagicMock()
    screen = np.zeros((400, 400, 3), dtype=np.uint8)

    def _match(_screen, _cfg, key):
        if key == "stop":
            return (0.90, 100, 200)
        return None

    with patch(
        "app.vision_transcribe.browser.deepseek_ui._match_template_key_on_screen",
        side_effect=_match,
    ):
        assert is_stop_button_near(page, 110, 210, radius=20, screen=screen)
        assert not is_stop_button_near(page, 10, 10, radius=20, screen=screen)


def test_send_target_skips_while_generating():
    from unittest.mock import MagicMock

    from app.vision_transcribe.browser.dom_locator import (
        is_send_button_ready,
    )

    page = MagicMock()
    page.evaluate.return_value = True
    assert not is_send_button_ready(page)


def test_fill_batch_prompt_skips_while_generating():
    from unittest.mock import MagicMock

    from app.vision_transcribe.browser.dom_locator import fill_batch_prompt

    page = MagicMock()
    page.evaluate.return_value = True
    page.get_by_placeholder.return_value = MagicMock(count=MagicMock(return_value=0))
    assert fill_batch_prompt(page, "PDF2MD PAGE 0001 test prompt here", log=MagicMock())
    page.keyboard.insert_text.assert_not_called()


def test_send_target_prefers_svg_arrow():
    from unittest.mock import MagicMock, patch

    from app.vision_transcribe.browser.dom_locator import (
        _click_composer_send_target,
        _get_composer_send_target,
    )

    page = MagicMock()
    page.evaluate.side_effect = lambda js, *args: (
        {
            "x": 900.0,
            "y": 800.0,
            "ready": True,
            "opacity": 1.0,
            "sendish": True,
        }
        if "data-pdf2md-send" in js or "best.el.setAttribute" in js
        else False
    )
    hit = _get_composer_send_target(page)
    assert hit and hit["ready"]
    with patch(
        "app.vision_transcribe.browser.dom_locator.is_confirmed_stop_at",
        return_value=False,
    ):
        assert _click_composer_send_target(page, hit)
    page.mouse.click.assert_called()
    args, kwargs = page.mouse.click.call_args
    assert args[0] == 900.0 and args[1] == 800.0


def test_send_state_gray_vs_blue():
    import cv2
    import numpy as np
    from pathlib import Path

    from app.vision_transcribe.browser.deepseek_ui import (
        _patch_looks_like_enabled_send,
        _patch_looks_like_gray_send,
        _patch_send_state,
        _send_template_match_scores,
        load_ui_config,
    )

    # DeepSeek 禁用发送键：淡紫蓝（高 B，但 B-R/B-G 差小）
    tpl_gray_path = Path("data/deepseek_templates/send_gray.png")
    tpl_blue_path = Path("data/deepseek_templates/send.png")
    tpl_gray = cv2.imread(str(tpl_gray_path))
    tpl_blue = cv2.imread(str(tpl_blue_path))
    assert tpl_gray is not None and tpl_blue is not None

    gh, gw = tpl_gray.shape[:2]
    assert _patch_send_state(tpl_gray, gw // 2, gh // 2, gw, gh) == "gray"
    assert _patch_looks_like_gray_send(tpl_gray, gw // 2, gh // 2, gw, gh) is True
    assert _patch_looks_like_enabled_send(tpl_gray, gw // 2, gh // 2, gw, gh) is False

    bh, bw = tpl_blue.shape[:2]
    assert _patch_send_state(tpl_blue, bw // 2, bh // 2, bw, bh) == "blue"
    assert _patch_looks_like_gray_send(tpl_blue, bw // 2, bh // 2, bw, bh) is False
    assert _patch_looks_like_enabled_send(tpl_blue, bw // 2, bh // 2, bw, bh) is True

    # 模拟视口：发送键在右下角 ROI（与 deepseek_ui.json search_roi 一致）
    for tpl in (tpl_gray, tpl_blue):
        viewport = np.full((900, 1400, 3), (245, 245, 248), dtype=np.uint8)
        th, tw = tpl.shape[:2]
        ox, oy = 1220, 780
        viewport[oy : oy + th, ox : ox + tw] = tpl
        gray_score, blue_score, _ = _send_template_match_scores(viewport, load_ui_config())
        if tpl is tpl_gray:
            assert gray_score > blue_score, (gray_score, blue_score)
        else:
            assert blue_score > gray_score, (gray_score, blue_score)


def test_looks_like_vision_response_rejects_sidebar_snippet():
    from app.vision_transcribe.browser.deepseek_ui import looks_like_vision_response

    sidebar = "高SES学生克服早期困难\n" * 20  # ~300 字，无 PAGE 标记
    assert not looks_like_vision_response(sidebar)
    assert looks_like_vision_response("<!-- PDF2MD:PAGE:0001 -->\n# Title\n" + "x" * 200)
    assert looks_like_vision_response("x" * 2000)


def test_extract_via_copy_skips_when_continue_visible():
    from unittest.mock import MagicMock, patch

    from app.vision_transcribe.browser.deepseek_ui import extract_via_copy_button

    page = MagicMock()
    with patch(
        "app.vision_transcribe.browser.deepseek_ui.is_continue_generate_visible",
        return_value=True,
    ):
        assert extract_via_copy_button(page, read_clipboard=lambda: "x") == ""


def test_click_continue_generate_dom():
    from unittest.mock import MagicMock

    from app.vision_transcribe.browser.deepseek_ui import (
        click_continue_generate_if_visible,
    )

    page = MagicMock()
    btn = MagicMock()
    btn.count.return_value = 1
    btn.first.is_visible.return_value = True
    page.get_by_text.return_value = btn
    assert click_continue_generate_if_visible(page, log=MagicMock())
    btn.first.click.assert_called_once()


def test_fill_batch_prompt_uses_vision_mode_placeholder():
    from unittest.mock import MagicMock

    from app.vision_transcribe.browser.dom_locator import fill_batch_prompt

    page = MagicMock()
    default_ph = MagicMock(count=MagicMock(return_value=0))
    vision_ph = MagicMock()
    vision_ph.count.return_value = 1
    vision_ph.first.is_visible.return_value = True
    vision_ph.first.input_value.return_value = "请转录以下页面"

    def _placeholder(p):
        if p == "使用识图模式开始对话":
            return vision_ph
        return default_ph

    page.get_by_placeholder.side_effect = _placeholder
    assert fill_batch_prompt(page, "请转录以下页面，保持公式与表格")
    vision_ph.first.fill.assert_called_once()
