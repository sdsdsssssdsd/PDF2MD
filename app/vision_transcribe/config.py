"""高保真视觉模式配置。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class VisionConfig:
    render_scale: float = 3.0
    batch_size: int = 10
    label_banner_px: int = 48
    # backend: playwright | clipboard | api（vision_backend 优先）
    vision_backend: str = ""
    browser_mode: str = "clipboard"
    api_batch_size: int = 6
    api_precision: str = "standard"  # standard | precise | extreme
    deepseek_url: str = "https://chat.deepseek.com/"
    # persistent profile（相对项目根或绝对路径）
    browser_profile_dir: Path | None = None
    headless: bool = False  # a2-1：必须有头浏览器
    response_stable_ms: int = 2500
    response_timeout_ms: int = 300_000
    force_rerender: bool = False
    # 显式重跑：重置全部批次并清旧回答（右键「重试」或已完成后再跑）
    force_rerun: bool = False
    # 与快速自动一致：Docling 出图质量 / Markdown 图片路径
    images_scale: float = 2.0
    image_path_mode: str = "relative"  # relative | absolute
    # DeepSeek 上传「服务器繁忙」账户级冷却（秒）
    server_busy_cooldown_seconds: int = 600

    def effective_backend(self) -> str:
        backend = (self.vision_backend or self.browser_mode or "clipboard").lower()
        if backend in ("api", "vision_api", "deepseek_api"):
            return "api"
        return backend

    def effective_batch_size(self) -> int:
        if self.effective_backend() == "api":
            prec = (self.api_precision or "standard").lower()
            if prec == "extreme":
                return 1
            if prec == "precise":
                return 2
            return max(1, int(self.api_batch_size or 6))
        return max(1, int(self.batch_size or 10))

    def resolve_profile_dir(self, app_root: Path, output_dir: Path | None = None) -> Path:
        if self.browser_profile_dir is not None:
            return Path(self.browser_profile_dir)
        # 优先全局 profile，便于跨任务复用登录
        return app_root / "data" / "deepseek_profile"
