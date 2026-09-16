"""第五模式：保护区域 → DeepSeek 修格式 → 完整性门 → 校验；通过后才落盘。"""
from __future__ import annotations

from pathlib import Path

from app.deepseek_api.config import DEFAULT_MODEL
from app.deepseek_api.key_store import api_key_configured
from app.deepseek_api.profiles import FORMAT_REPAIR
from app.format_repair.chunker import split_markdown_chunks, unwrap_markdown_fence
from app.format_repair.file_io import FileSnapshot, save_repaired_sibling, save_report_sibling
from app.format_repair.integrity import format_integrity_ok, projection_diff
from app.format_repair.models import FormatRepairResult, RepairConfig, RepairEdit
from app.format_repair.prompts import build_repair_messages
from app.format_repair.scanner import extract_protected_regions, restore_protected_regions
from app.format_repair.validator import validate_repaired_markdown


def _strict_pipeline(config: RepairConfig) -> bool:
    return str(config.review_model or "fast").lower() == "strict"


def _call_deepseek(markdown: str, *, part: int, total: int) -> str:
    from app.deepseek_api.client import DeepSeekClient

    client = DeepSeekClient()
    messages = build_repair_messages(markdown, part=part, total=total)
    return unwrap_markdown_fence(
        client.chat_text(messages, profile=FORMAT_REPAIR, max_tokens=FORMAT_REPAIR.max_tokens)
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

    if strict:
        try:
            tighter = caller(
                masked + "\n\n约束：不得改动数字、URL、变量名、图片路径；只修 Markdown 格式。",
                part,
                total,
            )
            restored2 = restore_protected_regions(tighter, regions)
            if format_integrity_ok(chunk, restored2):
                warnings.append(f"第 {part}/{total} 段二次复检后通过完整性门")
                warnings.extend(validate_repaired_markdown(restored2))
                return restored2, warnings, True
        except Exception as exc:
            warnings.append(f"第 {part}/{total} 段二次复检失败：{exc}")

    diff = projection_diff(chunk, restored)
    warnings.append(f"第 {part}/{total} 段内容漂移已回滚（{diff or 'projection mismatch'}）")
    return chunk, warnings, False


def repair_text(
    text: str,
    *,
    config: RepairConfig | None = None,
    source_path: Path | None = None,
    snapshot: FileSnapshot | None = None,
    chat_fn=None,
) -> FormatRepairResult:
    cfg = config or RepairConfig()
    original = text or ""
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
    caller = chat_fn or (lambda md, part, total: _call_deepseek(md, part=part, total=total))
    for idx, chunk in enumerate(chunks, start=1):
        restored, chunk_warnings, ok = _repair_chunk(
            chunk, part=idx, total=len(chunks), caller=caller, strict=strict
        )
        warnings.extend(chunk_warnings)
        outputs.append(restored)
        if ok:
            accepted += 1
        else:
            rolled_back += 1
            errors.extend(
                [w for w in chunk_warnings if w.startswith(f"第 {idx}/{len(chunks)} 段失败")]
            )

    output = "".join(outputs)
    if not output.endswith("\n"):
        output += "\n"

    gate_ok = rolled_back == 0 and format_integrity_ok(original, output)
    if not gate_ok:
        if rolled_back:
            errors.append("存在未通过完整性门的段落，未写入修复版文件")
        else:
            errors.append("全文完整性门失败，未写入修复版文件")
        if not format_integrity_ok(original, output):
            output = original if original.endswith("\n") else original + "\n"

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
        "integrity": 100 if gate_ok else 0,
        "strict_pipeline": strict,
    }
    if source_path is not None and snapshot is not None and gate_ok and not errors:
        saved_path = save_repaired_sibling(source_path, output, snapshot)
        if cfg.generate_report:
            report_path = save_report_sibling(
                source_path,
                {"chunks": len(chunks), "model": model, "warnings": warnings, "errors": errors},
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
