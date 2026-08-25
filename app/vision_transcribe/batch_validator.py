"""单批完整性校验。"""
from __future__ import annotations

import json
import re
from pathlib import Path

from app.vision_transcribe.manifest import batch_dir
from app.vision_transcribe.models import PAGE_MARKER_RE, ValidationResult

_OMISSION_PATTERNS = [
    re.compile(r"以下内容省略"),
    re.compile(r"其余类似"),
    re.compile(r"内容如图"),
    re.compile(r"同上[。.]?$"),
    re.compile(r"\.\.\.\s*$", re.M),
]


def _math_fence_ok(md: str) -> list[str]:
    errors: list[str] = []
    # display $$ 计数（忽略行内偶发）
    dollars = re.findall(r"\$\$", md)
    if len(dollars) % 2 != 0:
        errors.append("行间公式 $$ 围栏不成对")
    # 粗略：奇数个未转义 $（排除 $$）
    tmp = re.sub(r"\$\$", "", md)
    singles = len(re.findall(r"(?<!\\)\$", tmp))
    if singles % 2 != 0:
        errors.append("行内公式 $ 围栏可能不成对")
    try:
        from app.vision_transcribe.browser.katex_scrap import has_dom_katex_scrap

        if has_dom_katex_scrap(md or ""):
            errors.append(
                "检测到 KaTeX 竖排 Unicode 公式碎片（非 LaTeX），"
                "请用 DeepSeek 复制按钮/系统剪贴板重新获取"
            )
    except Exception:
        pass
    try:
        from app.vision_transcribe.clipboard_sanitize import has_clipboard_contamination

        if has_clipboard_contamination(md or ""):
            errors.append(
                "剪贴板含侧栏会话列表或 Prompt 回声（Ctrl+A 全页复制污染），"
                "请仅复制 assistant 回答"
            )
    except Exception:
        pass
    return errors


def validate_batch_markdown(
    md: str,
    *,
    start_page: int,
    end_page: int,
    batch_id: int = 0,
    output_dir: Path | None = None,
    prompt_version: str = "",
) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    found = [int(m.group(1)) for m in PAGE_MARKER_RE.finditer(md or "")]
    expected = list(range(start_page, end_page + 1))

    if not found:
        errors.append("未找到任何 PDF2MD:PAGE 标记")
    else:
        if found != expected:
            if sorted(found) != found:
                errors.append(f"PAGE 标记顺序错误: {found}")
            missing = [p for p in expected if p not in found]
            extra = [p for p in found if p not in expected]
            dup = sorted({p for p in found if found.count(p) > 1})
            if missing:
                errors.append(f"缺页标记: {missing}")
            if extra:
                errors.append(f"多余页标记: {extra}")
            if dup:
                errors.append(f"重复页标记: {dup}")
            if not missing and not extra and not dup and found != expected:
                errors.append(f"PAGE 标记与期望不符: got={found} expected={expected}")

    errors.extend(_math_fence_ok(md or ""))

    try:
        from app.vision_transcribe.transcript_quality import model_degeneration_errors

        errors.extend(model_degeneration_errors(md or ""))
    except Exception:
        pass

    try:
        from app.vision_transcribe.formula_integrity import formula_integrity_errors

        errors.extend(formula_integrity_errors(md or ""))
    except Exception:
        pass

    try:
        from app.vision_transcribe.integrity.page_guard import validate_page_integrity
        from app.vision_transcribe.transcript_quality import (
            is_references_heavy,
            looks_truncated_transcript,
        )
        from app.vision_transcribe.vision_structure_repair import markdown_lacks_structure

        pg_errs, pg_warns, _slices = validate_page_integrity(
            md or "",
            start_page=start_page,
            end_page=end_page,
            batch_id=batch_id,
            output_dir=output_dir,
            prompt_version=prompt_version,
        )
        errors.extend(pg_errs)
        warnings.extend(pg_warns)

        n_pages = end_page - start_page + 1
        if looks_truncated_transcript(
            md or "", start_page=start_page, end_page=end_page
        ):
            if not any("过短" in e or "SourceGuard" in e for e in errors):
                errors.append("内容与页数不匹配或复制截断")
        elif (
            n_pages == 1
            and markdown_lacks_structure(md or "")
            and not is_references_heavy(md or "")
        ):
            from app.vision_transcribe.capture.page_split import split_pages
            from app.vision_transcribe.integrity.page_guard import (
                is_figure_heavy_page,
                is_reference_page_body,
                min_chars_for_single_page,
            )

            slices = split_pages(md or "")
            sl = slices.get(start_page)
            body = sl.body if sl else (md or "")
            if not (
                is_figure_heavy_page(body)
                or is_reference_page_body(body)
                or is_references_heavy(body)
            ):
                min_len = min_chars_for_single_page(start_page, body=body)
                if len((md or "").strip()) < min_len * 2:
                    errors.append(
                        "Markdown 结构缺失（复制压平：无 # 标题 / | 表格 |），"
                        "须完整保留 DeepSeek 回答"
                    )
    except Exception:
        pass

    for pat in _OMISSION_PATTERNS:
        if pat.search(md or ""):
            warnings.append(f"疑似省略措辞: {pat.pattern}")

    try:
        from app.vision_transcribe.vision_structure_repair import (
            has_deepseek_placeholder_images,
        )

        if has_deepseek_placeholder_images(md or ""):
            errors.append(
                "仍含 example.com 虚构图片 URL（未转成 FIGURE 占位符），"
                "Docling 无法自动裁图"
            )
    except Exception:
        pass

    # 空页嫌疑：某页标记后几乎无内容
    parts = PAGE_MARKER_RE.split(md or "")
    # split: [pre, page, body, page, body, ...]
    if len(parts) >= 3:
        for i in range(1, len(parts), 2):
            page_s = parts[i]
            body = parts[i + 1] if i + 1 < len(parts) else ""
            body_stripped = PAGE_MARKER_RE.sub("", body)
            # 去掉下一个 page 之前
            if len(body_stripped.strip()) < 8:
                warnings.append(f"PAGE {page_s} 输出过短，疑似截断")

    ok = not errors
    return ValidationResult(ok=ok, errors=errors, warnings=warnings)


def validate_and_write(
    output_dir: Path,
    batch_id: int,
    md: str,
    *,
    start_page: int,
    end_page: int,
    prompt_version: str = "",
) -> ValidationResult:
    from app.vision_transcribe.prompts import PROMPT_VERSION

    pv = prompt_version or PROMPT_VERSION
    result = validate_batch_markdown(
        md,
        start_page=start_page,
        end_page=end_page,
        batch_id=batch_id,
        output_dir=output_dir,
        prompt_version=pv,
    )
    d = batch_dir(output_dir, batch_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "validation.json").write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return result
