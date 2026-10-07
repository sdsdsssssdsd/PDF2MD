"""第五模式：保护区域 → DeepSeek 修格式 → 完整性门 → 校验；通过后才落盘。"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from app.deepseek_api.config import DEFAULT_MODEL
from app.deepseek_api.key_store import api_key_configured
from app.deepseek_api.profiles import FORMAT_REPAIR
from app.format_repair.chunker import split_markdown_chunks, unwrap_markdown_fence
from app.format_repair.delimiters import (
    count_latex_delimiters,
    normalize_math_delimiters,
)
from app.format_repair.file_io import FileSnapshot, save_repaired_sibling, save_report_sibling
from app.format_repair.integrity import (
    content_projection,
    format_integrity_ok,
    projection_diff,
)
from app.format_repair.models import FormatRepairResult, RepairConfig, RepairEdit
from app.format_repair.prompts import build_repair_messages
from app.format_repair.scanner import extract_protected_regions, restore_protected_regions
from app.format_repair.validator import validate_repaired_markdown
from app.utils.progress import MODEL_PERCENT, PipelineCancelled, ProgressFn, StreamProgress


def _strict_pipeline(config: RepairConfig) -> bool:
    return str(config.review_model or "fast").lower() == "strict"


def _call_deepseek(
    markdown: str,
    *,
    part: int,
    total: int,
    on_delta: Callable[[int], None] | None = None,
) -> str:
    from app.deepseek_api.client import DeepSeekClient

    client = DeepSeekClient()
    messages = build_repair_messages(markdown, part=part, total=total)
    return unwrap_markdown_fence(
        client.chat_text(
            messages,
            profile=FORMAT_REPAIR,
            max_tokens=FORMAT_REPAIR.max_tokens,
            on_delta=on_delta,
        )
    )


_TIGHTEN_HINT = (
    "\n\n【只修格式】不得增删或改写任何字符：数字、标点、变量名、URL、图片路径"
    "一律原样保留；只允许调整 Markdown / LaTeX 的定界符与排版。"
)


def _repair_chunk(
    chunk: str,
    *,
    part: int,
    total: int,
    caller,
    strict: bool,
) -> tuple[str, list[str], bool]:
    warnings: list[str] = []
    masked, regions = extract_protected_regions(chunk)
    try:
        repaired = caller(masked, part, total)
    except Exception as exc:
        return chunk, [f"第 {part}/{total} 段失败：{exc}"], False
    restored = restore_protected_regions(repaired, regions)
    if format_integrity_ok(chunk, restored):
        warnings.extend(validate_repaired_markdown(restored))
        return restored, warnings, True

    # 内容漂移：先按「只修格式」再要一次，避免整段白跑（回滚 = 该段什么都没修）
    try:
        tighter = caller(masked + _TIGHTEN_HINT, part, total)
        restored2 = restore_protected_regions(tighter, regions)
        if format_integrity_ok(chunk, restored2):
            warnings.append(f"第 {part}/{total} 段二次复检后通过完整性门")
            warnings.extend(validate_repaired_markdown(restored2))
            return restored2, warnings, True
        warnings.append(
            f"第 {part}/{total} 段二次复检仍漂移"
            f"（{projection_diff(chunk, restored2) or 'projection mismatch'}）"
        )
    except Exception as exc:
        warnings.append(f"第 {part}/{total} 段二次复检失败：{exc}")

    diff = projection_diff(chunk, restored)
    warnings.append(
        f"第 {part}/{total} 段内容漂移已回滚（{diff or 'projection mismatch'}）；"
        "该段正文保持原样"
    )
    return chunk, warnings, False


def repair_text(
    text: str,
    *,
    config: RepairConfig | None = None,
    source_path: Path | None = None,
    snapshot: FileSnapshot | None = None,
    chat_fn=None,
    progress: ProgressFn | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> FormatRepairResult:
    cfg = config or RepairConfig()
    original = text or ""
    emit = progress or (lambda _text, _percent: None)
    is_cancelled = cancelled or (lambda: False)
    if not original.strip():
        return FormatRepairResult(
            input_text=original,
            output_text=original,
            errors=["没有可修正的内容"],
            integrity_ok=False,
        )
    if chat_fn is None and not api_key_configured():
        return FormatRepairResult(
            input_text=original,
            output_text=original,
            errors=["未配置 DeepSeek API Key，格式修正模式需要调用 API"],
            integrity_ok=True,
        )

    model = DEFAULT_MODEL
    strict = _strict_pipeline(cfg)
    chunks = split_markdown_chunks(original)
    outputs: list[str] = []
    errors: list[str] = []
    warnings: list[str] = []
    accepted = 0
    rolled_back = 0
    fixed = 0
    total_chars = sum(len(c) for c in chunks) or 1
    emit(f"准备：{len(chunks)} 段 · 共 {len(original):,} 字", 0)

    reporters: list[StreamProgress] = []

    def on_delta_for(part: int) -> Callable[[int], None]:
        reporter = reporters[part - 1]

        def _feed(total: int) -> None:
            if is_cancelled():  # 流式每段都是取消检查点
                raise PipelineCancelled("已取消")
            reporter.feed(total)

        return _feed

    def _default_caller(md: str, part: int, total: int) -> str:
        return _call_deepseek(md, part=part, total=total, on_delta=on_delta_for(part))

    caller = chat_fn or _default_caller
    done_chars = 0
    for idx, chunk in enumerate(chunks, start=1):
        if is_cancelled():
            raise PipelineCancelled("已取消")
        base = MODEL_PERCENT * done_chars / total_chars
        reporters.append(
            StreamProgress(
                emit,
                base=base,
                span=MODEL_PERCENT * len(chunk) / total_chars,
                label=f"第 {idx}/{len(chunks)} 段",
            )
        )
        emit(f"第 {idx}/{len(chunks)} 段：DeepSeek 修正中…", int(base))
        restored, chunk_warnings, ok = _repair_chunk(
            chunk, part=idx, total=len(chunks), caller=caller, strict=strict
        )
        # 定界符归一：纯改写 \( \) \[ \]，投影不变，模型回滚也照样生效
        normalized = normalize_math_delimiters(restored)
        if normalized != restored:
            if content_projection(normalized) != content_projection(restored):
                chunk_warnings.append(
                    f"第 {idx}/{len(chunks)} 段定界符归一被跳过（投影不一致，保险起见不改）"
                )
            else:
                fixed += count_latex_delimiters(restored)
                restored = normalized
        warnings.extend(chunk_warnings)
        outputs.append(restored)
        if ok:
            accepted += 1
        else:
            rolled_back += 1
            errors.extend(
                [w for w in chunk_warnings if w.startswith(f"第 {idx}/{len(chunks)} 段失败")]
            )
        done_chars += len(chunk)
        emit(
            f"已完成 {idx}/{len(chunks)} 段",
            int(MODEL_PERCENT * done_chars / total_chars),
        )
    emit("完整性门校验…", MODEL_PERCENT)

    output = "".join(outputs)
    original_norm = original if original.endswith("\n") else original + "\n"
    if not output.endswith("\n"):
        output += "\n"

    # 部分回滚不再等于整篇失败：回滚段的正文与原文逐字一致（已过投影门），
    # 其余段各自过门，全文投影再核一次，安全就落盘并如实告知。
    same_text = output.replace("\r\n", "\n").strip() == original.replace("\r\n", "\n").strip()
    gate_ok = format_integrity_ok(original, output)
    if not gate_ok:
        errors.append("全文完整性门失败，未写入修复版文件")
        output = original_norm
    elif rolled_back and same_text:
        errors.append(
            "所有段落的内容漂移都未通过完整性门，正文没有任何可安全落盘的改动"
        )
        output = original_norm
    elif rolled_back:
        warnings.append(
            f"{rolled_back}/{len(chunks)} 段因内容漂移未改写（正文保持原样），"
            "其余段落已修正"
        )

    edits = [
        RepairEdit(
            "deepseek_full_repair",
            original[:80],
            output[:80],
            f"chunks={len(chunks)} model={model} profile={FORMAT_REPAIR.name} strict={strict}",
            source="deepseek",
        )
    ]
    saved_path: Path | None = None
    stats = {
        "chunks": len(chunks),
        "model": model,
        "model_family": "DeepSeek-V4.1-Flash",
        "task_profile": FORMAT_REPAIR.name,
        "thinking": "disabled",
        "accepted": accepted,
        "rolled_back": rolled_back,
        "delimiters_normalized": fixed,
        "integrity": 0 if errors else 100,
        "strict_pipeline": strict,
    }
    if source_path is not None and snapshot is not None and gate_ok and not errors:
        saved_path = save_repaired_sibling(source_path, output, snapshot)
        if cfg.generate_report:
            report_path = save_report_sibling(
                source_path,
                {
                    "chunks": len(chunks),
                    "model": model,
                    "accepted": accepted,
                    "rolled_back": rolled_back,
                    "delimiters_normalized": fixed,
                    "warnings": warnings,
                    "errors": errors,
                },
            )
            stats["report_path"] = str(report_path)

    result = FormatRepairResult(
        input_text=original,
        output_text=output,
        edits=edits,
        warnings=warnings,
        errors=errors,
        integrity_ok=gate_ok and not errors,
        snapshot=snapshot or FileSnapshot(),
        report=stats,
    )
    if saved_path is not None:
        result.report["saved_path"] = str(saved_path)
    return result
