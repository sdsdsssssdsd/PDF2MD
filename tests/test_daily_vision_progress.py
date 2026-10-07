"""日常识图真实进度：流式接收 + 截断抢救 + 分批重编号。"""
from __future__ import annotations

import base64
import json
from pathlib import Path

from app.daily_vision.batching import merge_batch, renumber_marker, renumber_markdown
from app.daily_vision.models import DailyVisionResult, FigureRegion
from app.deepseek_api import client as client_mod
from app.deepseek_api.config import DeepSeekApiConfig
from app.deepseek_api.json_salvage import repair_truncated_json
from app.utils.progress import stream_percent

_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


class FakeSSE:
    """假的 SSE 响应：可迭代出 data: 行。"""

    def __init__(self, lines: list[str], content_type: str = "text/event-stream") -> None:
        self._lines = [ln.encode("utf-8") for ln in lines]
        self.headers = {"Content-Type": content_type}

    def read(self) -> bytes:
        return b"".join(self._lines)

    def __iter__(self):
        return iter(self._lines)

    def __enter__(self) -> "FakeSSE":
        return self

    def __exit__(self, *exc) -> bool:
        return False


def _chunk(text: str) -> str:
    return "data: " + json.dumps(
        {"choices": [{"index": 0, "delta": {"content": text}}]}, ensure_ascii=False
    )


def _split(payload: str, parts: int = 3) -> list[str]:
    size = max(1, len(payload) // parts)
    return [payload[i : i + size] for i in range(0, len(payload), size)]


def _sse_lines(chunks: list[str]) -> list[str]:
    lines = [": keep-alive", ""]
    lines += [_chunk(c) for c in chunks]
    lines += ['data: {"choices":[{"delta":{},"finish_reason":"stop"}]}', "", "data: [DONE]"]
    return lines


def test_stream_percent_is_monotonic_and_bounded():
    values = [stream_percent(0, 15, c) for c in (0, 10, 100, 1_000, 10_000, 10**6)]
    assert values == sorted(values)
    assert values[0] == 0
    assert values[-1] < 15  # 永远不越过本批区间，交给「已完成」阶段收口


def test_repair_truncated_json_closes_string_and_brackets():
    text = '{"markdown": "# 标题\\n正文", "regions": [{"marker": "i00'
    data = repair_truncated_json(text)
    assert data is not None
    assert data["markdown"] == "# 标题\n正文"


def test_repair_truncated_json_backs_off_dangling_key():
    data = repair_truncated_json('{"markdown": "abc", "regi')
    assert data == {"markdown": "abc"}


def test_repair_truncated_json_handles_trailing_backslash():
    data = repair_truncated_json('{"markdown": "abc\\')
    assert data is not None and data["markdown"] == "abc\\"


def test_repair_truncated_json_rejects_non_json():
    assert repair_truncated_json("完全不是 JSON") is None


def test_renumber_marker_and_merge_batch():
    assert renumber_marker("i0001:f01", 6) == "i0007:f01"
    assert renumber_marker("i0001:f01", 0) == "i0001:f01"
    assert (
        renumber_markdown("正文 <!-- PDF2MD:IMAGE:i0002:f03 --> 尾", 6)
        == "正文 <!-- PDF2MD:IMAGE:i0008:f03 --> 尾"
    )

    merged = DailyVisionResult(markdown="第一批")
    batch = DailyVisionResult(
        markdown="<!-- PDF2MD:IMAGE:i0001:f01 -->",
        regions=[FigureRegion(marker="i0001:f01", source_image=1, bbox=[0.1, 0.2, 0.3, 0.4])],
    )
    merge_batch(merged, batch, offset=6)
    assert merged.markdown == "第一批\n\n<!-- PDF2MD:IMAGE:i0007:f01 -->"
    assert merged.regions[0].marker == "i0007:f01"
    assert merged.regions[0].source_image == 7


def test_client_vision_json_streams_deltas(monkeypatch, tmp_path: Path):
    img = tmp_path / "a.png"
    img.write_bytes(_TINY_PNG)
    payload = json.dumps({"markdown": "# 你好世界", "regions": []}, ensure_ascii=False)
    chunks = _split(payload)
    seen_request: dict = {}

    def fake_urlopen(req, timeout=None):
        seen_request["body"] = json.loads(req.data.decode("utf-8"))
        seen_request["headers"] = {k.lower(): v for k, v in dict(req.headers).items()}
        return FakeSSE(_sse_lines(chunks))

    monkeypatch.setattr(client_mod.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(client_mod, "get_api_key", lambda: "test-key")

    deltas: list[int] = []
    client = client_mod.DeepSeekClient(config=DeepSeekApiConfig(auto_retry=False))
    data = client.vision_json([img], "转录", on_delta=deltas.append)

    assert data["markdown"] == "# 你好世界"
    assert seen_request["body"]["stream"] is True  # 只有显式要求进度时才流式
    assert "text/event-stream" in seen_request["headers"]["accept"]
    assert len(deltas) == len(chunks)  # 每段增量回调一次
    expected = 0
    for delta, chunk in zip(deltas, chunks):
        expected += len(chunk)
        assert delta == expected  # 回调的是累计已接收字数
    assert deltas[-1] == len(payload)


def test_client_vision_json_without_on_delta_is_not_streaming(monkeypatch, tmp_path: Path):
    img = tmp_path / "a.png"
    img.write_bytes(_TINY_PNG)
    body = {
        "choices": [
            {"message": {"role": "assistant", "content": '{"markdown": "# 好", "regions": []}'}}
        ]
    }
    seen_request: dict = {}

    def fake_urlopen(req, timeout=None):
        seen_request["body"] = json.loads(req.data.decode("utf-8"))
        return FakeSSE([json.dumps(body, ensure_ascii=False)], content_type="application/json")

    monkeypatch.setattr(client_mod.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(client_mod, "get_api_key", lambda: "test-key")

    client = client_mod.DeepSeekClient(config=DeepSeekApiConfig(auto_retry=False))
    data = client.vision_json([img], "转录")
    assert data["markdown"] == "# 好"
    assert seen_request["body"]["stream"] is False


def test_client_falls_back_when_gateway_ignores_stream(monkeypatch, tmp_path: Path):
    img = tmp_path / "a.png"
    img.write_bytes(_TINY_PNG)
    body = {
        "choices": [
            {"message": {"role": "assistant", "content": '{"markdown": "# 回退", "regions": []}'}}
        ]
    }
    monkeypatch.setattr(
        client_mod.urllib.request,
        "urlopen",
        lambda req, timeout=None: FakeSSE(
            [json.dumps(body, ensure_ascii=False)], content_type="application/json"
        ),
    )
    monkeypatch.setattr(client_mod, "get_api_key", lambda: "test-key")

    deltas: list[int] = []
    client = client_mod.DeepSeekClient(config=DeepSeekApiConfig(auto_retry=False))
    data = client.vision_json([img], "转录", on_delta=deltas.append)

    assert data["markdown"] == "# 回退"
    assert deltas == []  # 网关没流式：不编造进度


def test_client_salvages_truncated_response(monkeypatch, tmp_path: Path):
    from app.deepseek_api.models import TranscribeResult

    img = tmp_path / "a.png"
    img.write_bytes(_TINY_PNG)
    monkeypatch.setattr(client_mod, "get_api_key", lambda: "test-key")
    client = client_mod.DeepSeekClient(config=DeepSeekApiConfig(auto_retry=False))
    truncated = '{"markdown": "# 2010 年竞赛决赛\\n\\n(1) 求极限", "regions": [{"marker": "i00'
    client._vision_call = lambda *a, **k: TranscribeResult(markdown=truncated)  # type: ignore[method-assign]

    strict_failed = False
    try:
        client.vision_json([img], "转录")
    except Exception:
        strict_failed = True
    assert strict_failed  # 默认严格：截断就是错误

    salvaged = client.vision_json([img], "转录", salvage_truncated=True)
    assert salvaged["_salvaged"] is True
    assert salvaged["markdown"].startswith("# 2010 年竞赛决赛")


def test_client_retries_without_stream_when_stream_has_no_content(monkeypatch, tmp_path: Path):
    """网关声称流式却只发心跳：必须退回非流式，识别本身不能因进度功能失败。"""
    img = tmp_path / "a.png"
    img.write_bytes(_TINY_PNG)
    body = {
        "choices": [
            {"message": {"role": "assistant", "content": '{"markdown": "# 非流式", "regions": []}'}}
        ]
    }
    streams: list[bool] = []

    def fake_urlopen(req, timeout=None):
        payload = json.loads(req.data.decode("utf-8"))
        streams.append(bool(payload.get("stream")))
        if payload.get("stream"):
            return FakeSSE([": keep-alive", "", "data: [DONE]"])
        return FakeSSE([json.dumps(body, ensure_ascii=False)], content_type="application/json")

    monkeypatch.setattr(client_mod.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(client_mod, "get_api_key", lambda: "test-key")

    client = client_mod.DeepSeekClient(config=DeepSeekApiConfig(auto_retry=False))
    data = client.vision_json([img], "转录", on_delta=lambda _n: None)

    assert data["markdown"] == "# 非流式"
    assert streams == [True, False]  # 先流式，无内容后回退
