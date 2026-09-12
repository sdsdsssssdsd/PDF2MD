"""第五模式：读取 → 分块 → DeepSeek 全文修格式 → 拼接保存。"""
from __future__ import annotations

from pathlib import Path

from app.format_repair.chunker import split_markdown_chunks, unwrap_markdown_fence
from app.format_repair.file_io import FileSnapshot, save_repaired_sibling, save_report_sibling
from app.format_repair.models import FormatRepairResult, RepairConfig, RepairEdit
from app.format_repair.prompts import build_repair_messages
from app.vision_api.key_store import api_key_configured


def _repair_model(config: RepairConfig) -> str:
    if config.review_model == "strict":
        return "deepseek-v4-pro"
    try:
        from app.dialogs.settings_dialog import settings

        return str(
            settings().value("correction_text_model", "deepseek-v4-flash")
            or "deepseek-v4-flash"
        )
    except Exception:
        return "deepseek-v4-flash"


def _call_deepseek(markdown: str, *, model: str, part: int, total: int) -> str:
    from app.deepseek_api.client import DeepSeekClient

    client = DeepSeekClient()
    messages = build_repair_messages(markdown, part=part, total=total)
    return unwrap_markdown_fence(client.chat_text(messages, model=model, max_tokens=8192))


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

    model = _repair_model(cfg)
    chunks = split_markdown_chunks(original)
    outputs: list[str] = []
    errors: list[str] = []
    warnings: list[str] = []
    caller = chat_fn or (lambda md, part, total: _call_deepseek(md, model=model, part=part, total=total))
    for idx, chunk in enumerate(chunks, start=1):
        try:
            outputs.append(caller(chunk, idx, len(chunks)))
        except Exception as exc:
            errors.append(f"第 {idx}/{len(chunks)} 段失败：{exc}")
            outputs.append(chunk)

    output = "".join(outputs)
    if not output.endswith("\n"):
        output += "\n"

    edits = [
        RepairEdit(
            "deepseek_full_repair",
            original[:80],
            output[:80],
            f"chunks={len(chunks)} model={model}",
            source="deepseek",
        )
    ]
    saved_path: Path | None = None
    stats = {
        "chunks": len(chunks),
        "model": model,
        "accepted": 0 if errors else 1,
        "integrity": 100,
    }
    if source_path is not None and snapshot is not None and not errors:
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
        integrity_ok=not errors,
        snapshot=snapshot or FileSnapshot(),
        report=stats,
    )
    if saved_path is not None:
        result.report["saved_path"] = str(saved_path)
    return result
