"""DeepSeek API Unified V4.1：单一模型 + Profile + 迁移。"""
from __future__ import annotations

from pathlib import Path

from app.correction.deepseek_reviewer import TEXT_MODELS
from app.correction.models import CorrectionConfig
from app.correction.vision_verifier import VISION_MODEL_DEFAULT
from app.deepseek_api.client import DeepSeekClient, extract_assistant_text
from app.deepseek_api.config import (
    DEFAULT_MODEL,
    DEFAULT_TEXT_MODEL,
    DEFAULT_VISION_MODEL,
    DeepSeekApiConfig,
    migrate_legacy_model_name,
)
from app.deepseek_api.errors import EmptyContentError, InvalidJsonError
from app.deepseek_api.image_transport import INLINE_RAW_MAX, ensure_api_image
from app.deepseek_api.profiles import (
    CORRECTION_REVIEW,
    DAILY_VISION,
    FORMAT_REPAIR,
    PDF_VISION,
    VISION_VERIFY,
)
from app.format_repair.integrity import format_integrity_ok
from app.vision_api.config import VisionApiConfig


def test_single_production_model():
    assert DEFAULT_MODEL == "deepseek-flash"
    assert DEFAULT_TEXT_MODEL == DEFAULT_MODEL
    assert DEFAULT_VISION_MODEL == DEFAULT_MODEL
    assert VisionApiConfig().model == DEFAULT_MODEL
    assert DeepSeekApiConfig().model == DEFAULT_MODEL
    assert TEXT_MODELS["fast"] == DEFAULT_MODEL
    assert TEXT_MODELS["strict"] == DEFAULT_MODEL
    assert VISION_MODEL_DEFAULT == DEFAULT_MODEL
    assert CorrectionConfig().text_model == DEFAULT_MODEL
    assert CorrectionConfig().strict_model == DEFAULT_MODEL
    assert CorrectionConfig().vision_model == DEFAULT_MODEL


def test_legacy_model_migration():
    assert migrate_legacy_model_name("deepseek-v4-flash") == "deepseek-flash"
    assert migrate_legacy_model_name("deepseek-v4-pro") == "deepseek-flash"
    assert migrate_legacy_model_name("deepseek-v4-flash-vision-exp") == "deepseek-flash"
    assert migrate_legacy_model_name("deepseek-flash") == "deepseek-flash"


def test_config_from_mapping_migrates():
    cfg = DeepSeekApiConfig.from_mapping({"model": "deepseek-v4-flash-vision-exp"})
    assert cfg.model == "deepseek-flash"


def test_config_source_has_no_settings_dialog():
    text = Path("app/deepseek_api/config.py").read_text(encoding="utf-8")
    assert "settings_dialog" not in text
    assert "PySide6" not in text
    assert "QSettings" not in text


def test_profiles_thinking_disabled():
    for p in (DAILY_VISION, PDF_VISION, FORMAT_REPAIR, CORRECTION_REVIEW, VISION_VERIFY):
        assert p.thinking == "disabled"
        assert p.model == "deepseek-flash"
    assert DAILY_VISION.response_format == "json_object"
    assert VISION_VERIFY.response_format == "json_object"
    assert CORRECTION_REVIEW.response_format == "json_object"
    assert PDF_VISION.prefer_files is True
    assert DAILY_VISION.prefer_files is False


def test_extract_assistant_text_content_only():
    assert extract_assistant_text({"content": "ok", "reasoning_content": "no"}) == "ok"
    assert extract_assistant_text({"content": "", "reasoning_content": "no"}) == ""


def test_chat_json_semantic_retry():
    client = DeepSeekClient(config=DeepSeekApiConfig())
    calls = {"n": 0}

    def fake_text(messages, *, profile, max_tokens, **_kwargs):
        from app.deepseek_api.models import TranscribeResult

        calls["n"] += 1
        if calls["n"] == 1:
            raise EmptyContentError("empty")
        if calls["n"] == 2:
            raise InvalidJsonError("bad")
        return TranscribeResult(markdown='{"ok": true}')

    client._complete_text = fake_text  # type: ignore[method-assign]
    data = client.chat_json([{"role": "user", "content": "{}"}])
    assert data["ok"] is True
    assert client.last_semantic_retries == 2
    assert calls["n"] == 3


def test_inline_raw_max_under_32mib():
    assert INLINE_RAW_MAX <= 28 * 1024 * 1024


def test_format_integrity_allows_math_wrap():
    before = "若 (n) 为奇数"
    after = "若 $n$ 为奇数"
    assert format_integrity_ok(before, after)


def test_bmp_rejected_without_pillow_or_converted(tmp_path: Path):
    bmp = tmp_path / "x.bmp"
    bmp.write_bytes(b"BM")
    try:
        out = ensure_api_image(bmp)
    except Exception:
        return
    assert out.suffix.lower() == ".png"


def test_json_mode_and_thinking_in_body():
    client = DeepSeekClient(config=DeepSeekApiConfig())
    body = client._base_body(
        [{"role": "user", "content": "{}"}],
        profile=DAILY_VISION,
        json_mode=True,
    )
    assert body["model"] == "deepseek-flash"
    assert body["thinking"] == {"type": "disabled"}
    assert body["response_format"] == {"type": "json_object"}
    pdf_body = client._base_body(
        [{"role": "user", "content": "md"}],
        profile=PDF_VISION,
    )
    assert pdf_body["model"] == "deepseek-flash"
    assert "response_format" not in pdf_body


def test_production_code_has_no_old_model_defaults():
    allowed = {
        Path("app/deepseek_api/config.py"),
        Path("app/dialogs/settings_dialog.py"),
    }
    old_names = (
        "deepseek-v4-flash",
        "deepseek-v4-pro",
        "deepseek-v4-flash-vision-exp",
    )
    hits: list[str] = []
    for path in Path("app").rglob("*.py"):
        if path.as_posix().replace("\\", "/") in {p.as_posix() for p in allowed}:
            continue
        text = path.read_text(encoding="utf-8")
        for name in old_names:
            if name in text:
                hits.append(f"{path}: {name}")
    assert hits == []
