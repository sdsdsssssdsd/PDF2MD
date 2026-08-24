"""Phase 5F：DeepSeek Formula / Page 两套独立 profile。"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class DeepSeekOCRProfile:
    name: str
    base_size: int
    image_size: int
    crop_mode: bool
    max_new_tokens: int
    save_results: bool
    eval_mode: bool  # True → 内存返回，无 TextStreamer / 无磁盘 result.mmd
    prompt: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# 公式：已有精准 bbox；小图 crop_mode=True 时官方也不走 dynamic tile（≤768）。
# 注意：官方 crop_mode=False 路径在部分版本会 UnboundLocalError，故保持 True。
# Fast path 关键：eval_mode 内存返回、save_results=False、截断 max_new_tokens。
DEEPSEEK_FORMULA_PROFILE = DeepSeekOCRProfile(
    name="formula_fast",
    base_size=1024,
    image_size=640,
    crop_mode=True,
    max_new_tokens=512,
    save_results=False,
    eval_mode=True,
    prompt=None,
)

# 整页：保留 grounding / dynamic crop / 大 token
DEEPSEEK_PAGE_PROFILE = DeepSeekOCRProfile(
    name="page_document",
    base_size=1024,
    image_size=640,
    crop_mode=True,
    max_new_tokens=4096,
    save_results=False,
    eval_mode=True,
    prompt=None,
)


def profile_for_mode(mode: str) -> DeepSeekOCRProfile:
    m = (mode or "").lower().strip()
    if m in {"formula", "formulas"}:
        return DEEPSEEK_FORMULA_PROFILE
    return DEEPSEEK_PAGE_PROFILE
