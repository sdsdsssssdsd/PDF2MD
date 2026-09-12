"""日常识图结果轻量校验。"""
from __future__ import annotations

from app.daily_vision.models import DailyVisionResult


def validate_daily_result(result: DailyVisionResult) -> list[str]:
    errors: list[str] = []
    md = (result.markdown or "").strip()
    if not md:
        errors.append("识别结果为空")
        return errors
    if len(md) < 2:
        errors.append("识别结果过短")
    for reg in result.regions:
        if reg.bbox and len(reg.bbox) == 4:
            x0, y0, x1, y1 = reg.bbox
            if not (0 <= x0 <= 1.05 and 0 <= y0 <= 1.05 and 0 <= x1 <= 1.05 and 0 <= y1 <= 1.05):
                errors.append(f"区域 {reg.marker} bbox 超出范围")
            if x1 <= x0 or y1 <= y0:
                errors.append(f"区域 {reg.marker} bbox 无效")
    return errors
