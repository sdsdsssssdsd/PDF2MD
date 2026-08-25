"""CaptureBundle：多源抽取证据（P0）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CopyRound:
    round_index: int
    copy_api_text: str = ""
    clipboard_text: str = ""
    copy_api_generation: int = 0
    sentinel: str = ""
    copy_fired: bool = False


@dataclass
class CaptureBundle:
    batch_id: int | None = None
    attempt: int = 1
    copy_rounds: list[CopyRound] = field(default_factory=list)
    copy_api_selected: str = ""
    clipboard_selected: str = ""
    dom_markdown: str = ""
    dom_katex: str = ""
    clipboard_html_md: str = ""
    assistant_html: str = ""
    consensus_source: str = ""
    consensus_text: str = ""
    consensus_stable: bool = False
    failure_class: str = ""
    meta: dict[str, Any] = field(default_factory=dict)
