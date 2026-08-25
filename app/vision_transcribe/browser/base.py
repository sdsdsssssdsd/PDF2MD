"""Vision Web Adapter 抽象（Pipeline 不感知 DOM）。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class NeedsUserError(RuntimeError):
    """登录失效 / 验证码等，需人工处理后继续（a2-1）。"""


class ServerBusyCooldownError(RuntimeError):
    """DeepSeek 附件上传账户级限流（缩略图「服务器繁忙」，刷新无效）。"""

    def __init__(self, message: str = "", *, cooldown_seconds: int = 600) -> None:
        super().__init__(message or "DeepSeek 上传限流：服务器繁忙")
        self.cooldown_seconds = max(60, int(cooldown_seconds))


def server_busy_from_response(resp: dict) -> "ServerBusyCooldownError | None":
    """子进程 JSON 响应 → 限流异常（供 Playwright 客户端使用）。"""
    if not isinstance(resp, dict):
        return None
    if resp.get("server_busy"):
        return ServerBusyCooldownError(
            str(resp.get("error") or "DeepSeek 上传限流：服务器繁忙"),
            cooldown_seconds=int(resp.get("cooldown_seconds") or 600),
        )
    err = str(resp.get("error") or "")
    if "ServerBusyCooldownError" in err or err.startswith("SERVER_BUSY:"):
        return ServerBusyCooldownError(
            err.replace("SERVER_BUSY:", "", 1).strip() or err,
            cooldown_seconds=600,
        )
    return None


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
