"""旧产物 → 现行 sidecar 的兼容适配。不删旧文件。"""
from app.core.compat.vision_manifest import (
    VISION_MANIFEST_REL,
    ensure_vision_run_compat,
    load_legacy_vision_manifest,
    vision_manifest_path,
)

__all__ = [
    "VISION_MANIFEST_REL",
    "ensure_vision_run_compat",
    "load_legacy_vision_manifest",
    "vision_manifest_path",
]
