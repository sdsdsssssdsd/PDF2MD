"""Phase 4D — Balanced 有限生产写回（观测 + 可撤回，不扩 OCR）。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.formula.config import formula_config_for_deepseek_limited_production
from app.formula.writeback import (
    FormulaWritebackManager,
    RecoveryWritebackItem,
    build_display_block,
    register_display_formulas_by_order,
)
from app.utils.paths import BENCHMARK_RUNS, ensure_dirs

# O-018 稳定 candidate_id（与 shadow would_replace 对齐用）
O018_IDS = [
    "page6_eq1",
    "page6_eq4",
    "page6_eq5",
    "page7_eq6",
    "page7_eq7",
]


def build_corrupted_markdown_from_ids(candidate_ids: list[str]) -> str:
    parts = ["# O-018 limited production fixture\n"]
    for cid in candidate_ids:
        parts.append(f"\nContext {cid}\n\n$$\\quad\\quad\\quad garbage$$\n")
    return "".join(parts)


def items_from_shadow_review(rows: list[dict[str, Any]]) -> list[RecoveryWritebackItem]:
    items: list[RecoveryWritebackItem] = []
    for i, row in enumerate(rows):
        eq = str(row.get("eq_number") or "")
        page = row.get("page")
        if page is None:
            # 1,4,5 → page6; 6,7 → page7
            page = 6 if eq in {"1", "4", "5"} else 7 if eq in {"6", "7"} else None
        cid = str(row.get("candidate_id") or "")
        if not cid or cid.startswith("p"):
            # 规范化为稳定 ID
            if eq:
                cid = f"page{page}_eq{eq}"
        items.append(
            RecoveryWritebackItem(
                candidate_id=cid if cid in O018_IDS else (O018_IDS[i] if i < len(O018_IDS) else cid),
                recovered_latex=str(row.get("recovered") or ""),
                gate_accepted=bool(row.get("gate_accepted")),
                would_replace=bool(row.get("would_replace")),
                gate_reason=str(row.get("gate_reason") or "gain_accept"),
                original=str(row.get("original") or ""),
                scheduler_mode=str(row.get("scheduler_mode") or "formula_batch"),
                page=int(page) if page is not None else None,
            )
        )
    return items


def expected_markdown_from_items(
    candidate_ids: list[str], items: list[RecoveryWritebackItem]
) -> str:
    from app.formula.writeback import build_display_block, latex_with_optional_tag

    by_id = {it.candidate_id: it for it in items}
    parts = ["# O-018 limited production fixture\n"]
    for cid in candidate_ids:
        it = by_id[cid]
        body = latex_with_optional_tag(
            it.recovered_latex,
            candidate_id=cid,
            eq_number=it.eq_number,
            preserve=True,
        )
        parts.append(f"\nContext {cid}\n\n{build_display_block(body)}\n")
    return "".join(parts)


def run_o018_limited_production_from_shadow(
    *,
    shadow_json: Path | None = None,
    out_path: Path | None = None,
) -> dict[str, Any]:
    """用 4B.1 shadow 产物做有限生产写回（可不重跑 GPU）。"""
    ensure_dirs()
    src = shadow_json or (BENCHMARK_RUNS / "phase4b1_o018_shadow.json")
    if not src.exists():
        raise FileNotFoundError(str(src))

    shadow = json.loads(src.read_text(encoding="utf-8"))
    rows = shadow.get("would_replace_review") or []
    if len(rows) < 5:
        raise RuntimeError("shadow_would_replace_incomplete")

    # 按 O018_IDS 顺序对齐
    by_eq = {str(r.get("eq_number")): r for r in rows}
    ordered_rows = []
    for cid in O018_IDS:
        eq = cid.split("_eq")[-1]
        if eq not in by_eq:
            raise RuntimeError(f"missing_eq_in_shadow:{eq}")
        ordered_rows.append(by_eq[eq])

    items = items_from_shadow_review(ordered_rows)
    # 强制稳定 ID
    for cid, it in zip(O018_IDS, items, strict=True):
        it.candidate_id = cid

    md_before = build_corrupted_markdown_from_ids(O018_IDS)
    expected = expected_markdown_from_items(O018_IDS, items)
    reg = register_display_formulas_by_order(md_before, O018_IDS)

    cfg = formula_config_for_deepseek_limited_production()
    wb = FormulaWritebackManager(cfg)
    report = wb.apply(md_before, items, reg, unresolved_formula_count=0)

    matches_shadow = report.markdown_after == expected
    only_targets_changed = (
        report.applied_count == 5
        and "garbage" not in report.markdown_after
        and md_before.count("Context") == report.markdown_after.count("Context")
    )

    acceptance = {
        "applied_eq_5": report.applied_count == 5,
        "matches_would_replace": matches_shadow,
        "no_extra_diff_markers": only_targets_changed,
        "release_gate_ok": bool((report.release_gate or {}).get("publishable", True)),
        "document_status_ok": report.document_status == "ok",
        "rolled_back": report.rolled_back_count == 0,
    }
    acceptance["passed"] = all(acceptance.values())

    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "phase": "4D",
        "mode": "limited_production_balanced",
        "source_shadow": str(src),
        "writeback": report.to_dict(),
        "acceptance": acceptance,
        "policy": {
            "preset": "balanced",
            "max_writebacks_per_document": cfg.deepseek_max_writebacks_per_document,
            "max_writebacks_per_page": cfg.deepseek_max_writebacks_per_page,
            "require_high_confidence": cfg.deepseek_writeback_require_high_confidence,
            "default_for_all_documents": False,
        },
        "notes": [
            "DeepSeek recovery 是高置信修复增强层，不是全公式正确性承诺。",
            "全站默认启用留给 Phase 5；本阶段仅 limited production。",
        ],
    }

    # 写出最终 MD 副本供人工 diff（不碰用户生产目录）
    md_out = BENCHMARK_RUNS / "O018_phase4d_writeback.md"
    md_out.write_text(report.markdown_after, encoding="utf-8")
    qa = {
        "phase": "4D_limited_production",
        "writeback": report.to_dict(),
        "acceptance": acceptance,
        "document_status": report.document_status,
    }
    qa_path = BENCHMARK_RUNS / "O018_phase4d.formula_qa.json"
    qa_path.write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf-8")

    dest = out_path or (BENCHMARK_RUNS / "phase4d_o018_limited_production.json")
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    payload["output_path"] = str(dest)
    payload["markdown_path"] = str(md_out)
    payload["qa_path"] = str(qa_path)
    return payload
