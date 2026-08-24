"""全文合并后校验。"""
from __future__ import annotations

from app.vision_transcribe.models import PAGE_MARKER_RE, ValidationResult
from app.vision_transcribe.batch_validator import _math_fence_ok


def validate_document(md: str, page_count: int) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    found = [int(m.group(1)) for m in PAGE_MARKER_RE.finditer(md or "")]
    expected = list(range(1, page_count + 1))
    if found != expected:
        missing = [p for p in expected if p not in found]
        extra = [p for p in found if p not in expected]
        if missing:
            errors.append(f"全文缺页: {missing[:20]}{'...' if len(missing) > 20 else ''}")
        if extra:
            errors.append(f"全文多余页: {extra[:20]}")
        if found and sorted(found) != found:
            errors.append("全文 PAGE 标记非升序")
    errors.extend(_math_fence_ok(md or ""))
    return ValidationResult(ok=not errors, errors=errors, warnings=warnings)
