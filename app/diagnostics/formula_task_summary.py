# -*- coding: utf-8 -*-
"""主窗口任务表：从 formula_qa 提取「恢复覆盖 / 成功写回」展示用分数。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# k5：生产无 GT，任务表只能报覆盖/写回，Accuracy 只出现在 Benchmark
TOOLTIP_FORMULA_RECOGNITION = (
    "恢复覆盖：无需恢复的合法公式 + Gate 通过数 / 公式槽总数。"
    "不是 Equation Exact Accuracy；公式级准确率只在 Benchmark（match_eval_v2）。"
)
TOOLTIP_FORMULA_POSTCHECK = (
    "成功写回：无需恢复的合法公式 + 实际写回正文数 / 公式槽总数。"
    "不等于 LaTeX 语义正确率。自动写回精度目标见 k5 Release Gate（≥99%）。"
)


def formula_metrics_from_qa(qa: dict[str, Any] | None) -> tuple[int | None, int | None, int | None]:
    """返回 (recognized, post_ok, total)。

    - **恢复覆盖**：无需恢复的合法公式 + 恢复 Gate 通过数
    - **成功写回**：无需恢复的合法公式 + 实际写回正文数
    """
    if not qa:
        return None, None, None
    total = int(qa.get("formula_count") or 0)
    if total <= 0:
        return 0, 0, 0

    attempted = int(qa.get("recovery_attempted_count") or 0)
    recovery_success = int(qa.get("recovery_success_count") or 0)
    validated = int(qa.get("validated") or 0)
    wb = qa.get("writeback") if isinstance(qa.get("writeback"), dict) else {}
    applied = int(wb.get("applied_count") or 0)

    if attempted > 0:
        untouched = max(0, total - attempted)
        recognized = min(total, untouched + recovery_success)
        post_ok = min(total, untouched + applied)
    else:
        recognized = min(total, validated)
        post_ok = recognized

    return recognized, post_ok, total


def load_formula_qa_for_task(
    *,
    pdf_stem: str,
    out_dir: Path | None,
    experiment_dir: Path | None = None,
) -> dict[str, Any] | None:
    """优先论文目录 QA，其次 logs/experiment 镜像。"""
    from app.utils.paths import experiment_doc_dir

    name = f"{pdf_stem}.formula_qa.json"
    candidates: list[Path] = []
    if out_dir is not None:
        candidates.append(out_dir / name)
    exp = experiment_dir or experiment_doc_dir(pdf_stem)
    candidates.append(exp / name)
    best: Path | None = None
    best_mtime = -1.0
    for path in candidates:
        if not path.is_file():
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime > best_mtime:
            best_mtime = mtime
            best = path
    if best is not None:
        try:
            return json.loads(best.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return None


def format_formula_fraction(num: int | None, den: int | None, *, no_formula: bool = False) -> str:
    if num is None or den is None:
        return "—"
    if den <= 0:
        return "无公式" if no_formula else "—"
    return f"{num}/{den}"


def formula_column_labels(
    qa: dict[str, Any] | None,
) -> tuple[str, str]:
    if qa is None:
        return "—", "—"
    total = int(qa.get("formula_count") or 0)
    if total <= 0:
        return "无公式", "无公式"
    rec, post, total = formula_metrics_from_qa(qa)
    return (
        format_formula_fraction(rec, total),
        format_formula_fraction(post, total),
    )
