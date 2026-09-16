"""Site contract fixtures：把假页面升级为契约测试，而不是无限 fallback。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.vision_transcribe.browser.contracts.fingerprint import (
    DEEPSEEK_SITE_ADAPTER,
    landmark_hits,
)

FIXTURE_FAKE_DEEPSEEK = (
    Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "fake_deepseek.html"
)


def fake_deepseek_fixture() -> Path:
    return FIXTURE_FAKE_DEEPSEEK


def required_fixture_landmarks() -> tuple[str, ...]:
    return ("composer", "copy")


def fixture_satisfies_contract(page: Any) -> bool:
    hits = set(landmark_hits(page))
    return "composer" in hits or "textarea" in hits or "contenteditable" in hits


def adapter_contract_dict() -> dict[str, str]:
    return DEEPSEEK_SITE_ADAPTER.to_dict()
