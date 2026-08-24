"""Vision Web Adapter 抽象（Pipeline 不感知 DOM）。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class NeedsUserError(RuntimeError):
    """登录失效 / 验证码等，需人工处理后继续（a2-1）。"""


@dataclass
class AdapterResult:
    markdown: str
    needs_user: bool = False
    message: str = ""
    extract_stats: dict[str, Any] | None = field(default=None, repr=False)


class VisionWebAdapter(ABC):
    """submit_batch 为高层入口；Playwright 实现可拆成细粒度方法。"""

    @abstractmethod
    def submit_batch(self, images: list[Path], prompt: str) -> AdapterResult:
        ...

    def prepare_manual_batch(
        self,
        images: list[Path],
        prompt: str,
        *,
        bookfigures_dir: Path | None = None,
    ) -> str:
        """半自动：复制 prompt、打开目录；返回提示文案。默认空实现。"""
        return ""

    def close(self) -> None:
        return None
