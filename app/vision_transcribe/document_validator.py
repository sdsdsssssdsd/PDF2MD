"""全文合并后校验。"""
from __future__ import annotations

from pathlib import Path

from app.vision_transcribe.models import PAGE_MARKER_RE, ValidationResult
from app.vision_transcribe.batch_validator import _math_fence_ok


def validate_document(
    md: str,
    page_count: int,
    *,
    output_dir: Path | None = None,
    prompt_version: str = "",
) -> ValidationResult:
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
    try:
        from app.vision_transcribe.transcript_quality import model_degeneration_errors

        errors.extend(model_degeneration_errors(md or ""))
    except Exception:
        pass
    if page_count > 0:
        try:
            from app.vision_transcribe.integrity.page_guard import validate_page_integrity

            pg_errs, pg_warns, _slices = validate_page_integrity(
                md or "",
                start_page=1,
                end_page=page_count,
                batch_id=0,
                output_dir=output_dir,
                prompt_version=prompt_version,
            )
            errors.extend(pg_errs)
            warnings.extend(pg_warns)
        except Exception:
            pass
    return ValidationResult(ok=not errors, errors=errors, warnings=warnings)
