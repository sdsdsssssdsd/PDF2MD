"""Phase 5E 预留：picture x3 与 Formula Recovery 并行。

当前 Docling `converter.convert()` 同步完成 structure + picture render，
尚无稳定官方 API 把 generate_picture_images 拆到独立阶段。

规划（不默认启用）：
1. structure-only convert（keep_images=False）→ 先出 document model / raw md
2. 并行：
   - FormulaPipeline + DeepSeek
   - 二次 pass 或 AssetPipeline 补渲染 x3 图片并回写路径
3. join 后写 final MD

本模块仅提供开关占位，避免在未验证前改关键路径。
"""
from __future__ import annotations

# 生产默认关闭；验证通过后再接入 ConversionWorker
PARALLEL_PICTURE_EXPORT_ENABLED = False


def parallel_picture_export_supported() -> bool:
    return False
