"""Vision API 与四模式框架单元测试。"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.daily_vision.exporter import parse_daily_response
from app.daily_vision.models import DailyVisionResult, FigureRegion
from app.daily_vision.validator import validate_daily_result
from app.task_model import (
    WorkflowChoice,
    is_vision_api_workflow,
    is_vision_web_workflow,
    is_vision_workflow,
    normalize_workflow,
)
from app.utils.paths import resolve_vision_output_dir, vision_api_task_output_dir
from app.vision_api.client import (
    DeepSeekVisionClient,
    build_message_content,
    extract_assistant_text,
    normalize_detail,
)
from app.vision_api.config import VisionApiConfig
from app.vision_api.models import ImagePayload
from app.vision_api.deepseek_adapter import DeepSeekApiVisionAdapter
from app.vision_api.file_cache import cache_path, lookup, sha256_file, store
from app.vision_transcribe.config import VisionConfig
from app.workers.vision_worker import VisionConversionWorker


def test_vision_api_output_dir():
    root = Path("D:/out")
    pdf = Path("D:/papers/foo.pdf")
    assert vision_api_task_output_dir(root, pdf) == Path("D:/out/foo_API视觉")


def test_resolve_vision_output_dir_routing():
    root = Path("D:/out")
    pdf = Path("D:/papers/foo.pdf")
    assert resolve_vision_output_dir(root, pdf, WorkflowChoice.VISION_WEB.value).name.endswith("_高保真")
    assert resolve_vision_output_dir(root, pdf, WorkflowChoice.VISION_API.value).name.endswith("_API视觉")


def test_normalize_workflow_legacy():
    assert normalize_workflow("vision") == WorkflowChoice.VISION_WEB.value
    assert normalize_workflow(WorkflowChoice.VISION.value) == WorkflowChoice.VISION_WEB.value


def test_is_vision_workflow_helpers():
    assert is_vision_workflow(WorkflowChoice.VISION_API.value)
    assert is_vision_workflow(WorkflowChoice.VISION_WEB.value)
    assert is_vision_api_workflow(WorkflowChoice.VISION_API.value)
    assert is_vision_web_workflow(WorkflowChoice.VISION_WEB.value)
    assert not is_vision_workflow(WorkflowChoice.STRUCTURED.value)


def test_vision_config_effective_batch_size():
    cfg = VisionConfig(vision_backend="api", api_precision="standard", api_batch_size=4)
    assert cfg.effective_backend() == "api"
    assert cfg.effective_batch_size() == 4
    cfg_default = VisionConfig(vision_backend="api", api_precision="standard")
    assert cfg_default.effective_batch_size() == 10
    cfg2 = VisionConfig(vision_backend="api", api_precision="extreme")
    assert cfg2.effective_batch_size() == 1


def test_parse_daily_response_json():
    payload = {
        "markdown": "hello\n<!-- PDF2MD:IMAGE:i0001:f01 -->",
        "regions": [{"marker": "i0001:f01", "source_image": 1, "bbox": [0, 0, 1, 1]}],
    }
    result = parse_daily_response(json.dumps(payload))
    assert "hello" in result.markdown
    assert result.regions[0].marker == "i0001:f01"


def test_deepseek_adapter_delegates_to_client(tmp_path: Path):
    img = tmp_path / "a.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    adapter = DeepSeekApiVisionAdapter(config=VisionApiConfig())
    mock_result = MagicMock(markdown="# ok", request_id="r1", input_tokens=1, output_tokens=2, latency_ms=10)
    with patch.object(adapter._client, "transcribe", return_value=mock_result):
        out = adapter.submit_batch([img], "prompt")
    assert out.markdown == "# ok"
    assert out.extract_stats and out.extract_stats.get("backend") == "deepseek_api"


def test_build_message_content_file_block():
    payloads = [
        ImagePayload(path=Path("a.png"), mime="image/png", file_id="file-api-abc"),
    ]
    blocks = build_message_content("hi", payloads, "original")
    assert blocks[0]["type"] == "text"
    assert blocks[1] == {"type": "file", "file_id": "file-api-abc"}
    assert "image_url" not in blocks[1]


def test_build_message_content_base64_block():
    payloads = [
        ImagePayload(
            path=Path("a.png"),
            mime="image/png",
            data_url="data:image/png;base64,AAA",
        ),
    ]
    blocks = build_message_content("hi", payloads, "Original")
    assert blocks[1]["type"] == "image_url"
    assert blocks[1]["image_url"]["detail"] == "original"


def test_normalize_detail():
    assert normalize_detail("Original") == "original"
    assert normalize_detail("bogus") == "original"


def test_chat_completion_urls():
    cfg = VisionApiConfig(api_base="https://api.deepseek.com")
    assert cfg.chat_completion_urls()[0].endswith("/v1/chat/completions")
    assert cfg.chat_completion_urls()[1].endswith("/chat/completions")


def test_extract_assistant_text_reasoning_fallback():
    msg = {"content": "", "reasoning_content": "OK reasoning"}
    assert extract_assistant_text(msg) == "OK reasoning"


def test_parse_response_allow_empty_for_test():
    client = DeepSeekVisionClient(config=VisionApiConfig())
    data = {
        "id": "x",
        "choices": [{"message": {"content": ""}, "finish_reason": "length"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 0},
    }
    r = client._parse_response(data, allow_empty_if_ok=True)
    assert r.markdown == "OK"


def test_client_parse_response():
    client = DeepSeekVisionClient(config=VisionApiConfig())
    data = {
        "id": "req-1",
        "choices": [{"message": {"content": "PAGE 1 text"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20},
        "_latency_ms": 100,
    }
    result = client._parse_response(data)
    assert result.markdown == "PAGE 1 text"
    assert result.request_id == "req-1"


def test_file_cache_roundtrip(tmp_path: Path):
    f = tmp_path / "page.png"
    f.write_bytes(b"fake png")
    cache = cache_path(tmp_path / "out")
    store(f, cache_file=cache, file_id="file-abc")
    hit = lookup(f, cache_file=cache)
    assert hit and hit["file_id"] == "file-abc"
    assert sha256_file(f)


def test_daily_validator_bbox():
    ok = DailyVisionResult(markdown="hello", regions=[])
    assert not validate_daily_result(ok)
    bad = DailyVisionResult(
        markdown="x",
        regions=[FigureRegion(marker="i0001:f01", source_image=1, bbox=[0.9, 0.9, 0.1, 0.1])],
    )
    assert validate_daily_result(bad)


def test_vision_worker_api_mode_flag():
    worker = VisionConversionWorker([], output_root=Path("."), per_folder=True)
    worker._config = VisionConfig(vision_backend="api")
    assert worker._is_api_mode()
    worker._config = VisionConfig(browser_mode="playwright")
    assert not worker._is_api_mode()
