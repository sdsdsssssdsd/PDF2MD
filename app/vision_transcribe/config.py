"""高保真视觉模式配置。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class VisionConfig:
    render_scale: float = 3.0
    batch_size: int = 10
    label_banner_px: int = 48
    # browser: "clipboard" | "playwright"
    browser_mode: str = "clipboard"
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

    def resolve_profile_dir(self, app_root: Path, output_dir: Path | None = None) -> Path:
        if self.browser_profile_dir is not None:
            return Path(self.browser_profile_dir)
        # 优先全局 profile，便于跨任务复用登录
        return app_root / "data" / "deepseek_profile"
