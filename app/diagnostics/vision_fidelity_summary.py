# -*- coding: utf-8 -*-
"""高保真视觉：最终文档字数 / DeepSeek 识别字数（任务表展示）。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.vision_transcribe.manifest import batch_dir, vision_dir
from app.vision_transcribe.models import BatchStatus

FIDELITY_STATS_NAME = "fidelity_stats.json"
BATCH_EXTRACT_STATS_NAME = "extract_stats.json"

TOOLTIP_VISION_FIDELITY = (
    "保真字数：最终 Markdown 字数 / 各批次 DeepSeek 识别入库字数之和。"
    "比例偏低通常表示复制截断、批次未全部合并，或清理阶段删除了 PAGE 标记等内容。"
)


def _format_k(n: int | None) -> str:
    if n is None:
        return "—"
    if n < 1000:
        return str(n)
    if n < 10_000:
        return f"{n / 1000:.1f}k"
    return f"{round(n / 1000)}k"


def format_fidelity_label(
    *,
    final_chars: int | None,
    ds_chars: int | None,
) -> str:
    if final_chars is None and ds_chars is None:
        return "—"
    if ds_chars is None or ds_chars <= 0:
        return f"{_format_k(final_chars)}/—"
    if final_chars is None:
        return f"—/{_format_k(ds_chars)}"
    pct = int(round(100.0 * final_chars / ds_chars))
    return f"{_format_k(final_chars)}/{_format_k(ds_chars)} {pct}%"


def write_batch_extract_stats(
    output_dir: Path,
    batch_id: int,
    stats: dict[str, Any],
) -> Path:
    d = batch_dir(output_dir, batch_id)
    d.mkdir(parents=True, exist_ok=True)
    path = d / BATCH_EXTRACT_STATS_NAME
    path.write_text(
        json.dumps(stats, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def load_batch_extract_stats(output_dir: Path, batch_id: int) -> dict[str, Any] | None:
    path = batch_dir(output_dir, batch_id) / BATCH_EXTRACT_STATS_NAME
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def sum_accepted_ds_chars(output_dir: Path) -> tuple[int, list[dict[str, Any]]]:
    """各 accepted 批次 response.raw.md 字数之和。"""
    from app.vision_transcribe.batch_ingest import read_raw_response
    from app.vision_transcribe.manifest import load_manifest

    m = load_manifest(output_dir)
    if m is None:
        return 0, []
    per_batch: list[dict[str, Any]] = []
    total = 0
    for b in m.get_batches():
        if b.status != BatchStatus.ACCEPTED.value:
            continue
        raw = read_raw_response(output_dir, b.id) or ""
        n = len(raw)
        total += n
        per_batch.append(
            {
                "batch_id": b.id,
                "start_page": b.start_page,
                "end_page": b.end_page,
                "chars_raw": n,
            }
        )
    return total, per_batch


def write_fidelity_stats(
    output_dir: Path,
    *,
    final_md: Path | None = None,
) -> dict[str, Any]:
    """合并/写回后刷新 `.vision/fidelity_stats.json`。"""
    vdir = vision_dir(output_dir)
    vdir.mkdir(parents=True, exist_ok=True)

    ds_chars, batches = sum_accepted_ds_chars(output_dir)

    merged_raw = vdir / "document.raw.md"
    cleaned = vdir / "document.cleaned.md"
    merged_raw_chars = (
        len(merged_raw.read_text(encoding="utf-8")) if merged_raw.is_file() else None
    )
    cleaned_chars = (
        len(cleaned.read_text(encoding="utf-8")) if cleaned.is_file() else None
    )

    final_chars: int | None = None
    final_path: str | None = None
    if final_md is not None and final_md.is_file():
        final_chars = len(final_md.read_text(encoding="utf-8"))
        final_path = str(final_md)
    elif cleaned.is_file():
        final_chars = cleaned_chars
        final_path = str(cleaned)

    ratio: float | None = None
    if final_chars is not None and ds_chars > 0:
        ratio = round(final_chars / ds_chars, 4)

    payload: dict[str, Any] = {
        "ds_chars_total": ds_chars,
        "merged_raw_chars": merged_raw_chars,
        "cleaned_chars": cleaned_chars,
        "final_chars": final_chars,
        "final_md": final_path,
        "ratio_final_over_ds": ratio,
        "batches": batches,
    }
    out = vdir / FIDELITY_STATS_NAME
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def load_fidelity_stats(output_dir: Path | None) -> dict[str, Any] | None:
    if output_dir is None:
        return None
    path = vision_dir(output_dir) / FIDELITY_STATS_NAME
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def fidelity_metrics_from_stats(
    stats: dict[str, Any] | None,
) -> tuple[int | None, int | None, float | None]:
    if not stats:
        return None, None, None
    final_c = stats.get("final_chars")
    ds_c = stats.get("ds_chars_total")
    ratio = stats.get("ratio_final_over_ds")
    return (
        int(final_c) if final_c is not None else None,
        int(ds_c) if ds_c is not None else None,
        float(ratio) if ratio is not None else None,
    )


def vision_fidelity_column_label(
    *,
    out_dir: Path | None,
    partial: bool = False,
) -> str:
    stats = load_fidelity_stats(out_dir)
    final_c, ds_c, _ = fidelity_metrics_from_stats(stats)
    if partial and final_c is None and ds_c is not None and ds_c > 0:
        return f"—/{_format_k(ds_c)}"
    return format_fidelity_label(final_chars=final_c, ds_chars=ds_c)
