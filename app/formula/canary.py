"""Phase 5A — Canary Production Evaluation（只观测，不改识别参数）。"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from app.formula.versions import attach_versions, pipeline_versions
from app.utils.paths import BENCHMARK_DIR, BENCHMARK_RUNS, ensure_dirs

CANARY_DIR = BENCHMARK_DIR / "canary"
CANARY_MANIFEST = CANARY_DIR / "manifest.json"
CANARY_REVIEW = CANARY_DIR / "human_review_template.json"


@dataclass
class CanaryDocMetrics:
    doc_id: str
    source: str = ""
    formula_candidates: int = 0
    corrupted_detected: int = 0
    deepseek_recovery_attempted: int = 0
    recovery_accepted: int = 0
    recovery_rejected: int = 0
    writeback_applied: int = 0
    writeback_rollback: int = 0
    writeback_budget_exceeded: int = 0
    unresolved_formulas: int = 0
    formula_incomplete: bool = False
    model_load_count: int = 0
    ocr_calls: int = 0
    ocr_seconds: float = 0.0
    total_recovery_seconds: float = 0.0
    total_document_seconds: float = 0.0
    mode_counts: dict[str, int] = field(default_factory=dict)
    coverage: dict[str, str] = field(default_factory=dict)
    # 人工复核槽位（默认未知 → 未复核）
    false_accept: int | None = None
    true_accept: int | None = None
    false_reject: int | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def ingest_o018_artifacts(
    *,
    shadow_path: Path | None = None,
    prod_path: Path | None = None,
) -> CanaryDocMetrics:
    """从已有 4B.1 / 4D 产物构造首篇 canary 文档指标（无需重跑 GPU）。"""
    shadow_path = shadow_path or (BENCHMARK_RUNS / "phase4b1_o018_shadow.json")
    prod_path = prod_path or (BENCHMARK_RUNS / "phase4d_o018_limited_production.json")
    shadow = json.loads(shadow_path.read_text(encoding="utf-8")) if shadow_path.exists() else {}
    prod = json.loads(prod_path.read_text(encoding="utf-8")) if prod_path.exists() else {}

    sh_sum = (shadow.get("deepseek_shadow") or {}).get("summary") or {}
    timing = shadow.get("timing") or {}
    wb = prod.get("writeback") or {}
    entries = wb.get("entries") or []

    return CanaryDocMetrics(
        doc_id="O-018_Abdo2025_Stacking_SHAP",
        source=str(shadow_path),
        formula_candidates=int(sh_sum.get("corrupted_formula_count") or 5),
        corrupted_detected=int(sh_sum.get("corrupted_formula_count") or 5),
        deepseek_recovery_attempted=int(sh_sum.get("ocr_calls") or 0),
        recovery_accepted=int(sh_sum.get("accepted") or 0),
        recovery_rejected=int(sh_sum.get("rejected") or 0),
        writeback_applied=int(wb.get("applied_count") or 0),
        writeback_rollback=int(wb.get("rolled_back_count") or 0),
        writeback_budget_exceeded=sum(
            1 for e in entries if e.get("skip_reason") == "writeback_budget_exceeded"
        ),
        unresolved_formulas=0,
        formula_incomplete=(wb.get("document_status") == "formula_incomplete"),
        model_load_count=int(shadow.get("model_load_count") or sh_sum.get("model_load_count") or 0),
        ocr_calls=int(sh_sum.get("ocr_calls") or 0),
        ocr_seconds=float(timing.get("ocr_inference_seconds") or sh_sum.get("ocr_inference_seconds") or 0),
        total_recovery_seconds=float(
            timing.get("shadow_actual_seconds") or sh_sum.get("actual_seconds") or 0
        ),
        total_document_seconds=float(timing.get("document_total_seconds") or 0),
        mode_counts=dict(sh_sum.get("mode_counts") or {}),
        # O-018 人工复核：4B.1 would_replace 5/5 human_usable → 暂记 true_accept=5, false_accept=0
        false_accept=0,
        true_accept=int(sh_sum.get("accepted") or 0),
        false_reject=0,
        notes="seeded_from_phase4b1_and_4d; human_usable all true in would_replace_review",
    )


def _percentile(vals: list[float], p: float) -> float | None:
    if not vals:
        return None
    xs = sorted(float(v) for v in vals)
    if len(xs) == 1:
        return round(xs[0], 3)
    k = (len(xs) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(xs) - 1)
    if f == c:
        return round(xs[f], 3)
    return round(xs[f] + (xs[c] - xs[f]) * (k - f), 3)


def aggregate_canary(docs: list[CanaryDocMetrics]) -> dict[str, Any]:
    n = len(docs)
    mode_tot: dict[str, int] = {}
    for d in docs:
        for k, v in (d.mode_counts or {}).items():
            mode_tot[k] = mode_tot.get(k, 0) + int(v)

    def _sum(attr: str) -> int | float:
        return sum(getattr(x, attr) or 0 for x in docs)

    fa = [d.false_accept for d in docs if d.false_accept is not None]
    ta = [d.true_accept for d in docs if d.true_accept is not None]
    fr = [d.false_reject for d in docs if d.false_reject is not None]
    reviewed = sum(1 for d in docs if d.false_accept is not None)

    accepted = int(_sum("recovery_accepted"))
    writebacks = int(_sum("writeback_applied"))
    usable_rate = None
    if accepted > 0 and ta:
        usable_rate = round(sum(ta) / max(1, accepted), 3)
    writeback_precision = None
    if writebacks > 0 and fa is not None and len(fa) == n and reviewed == n:
        # precision = (writebacks - false_accept) / writebacks when all docs reviewed
        correct = writebacks - int(sum(fa))
        writeback_precision = round(correct / max(1, writebacks), 3)

    doc_secs = [float(d.total_document_seconds or 0) for d in docs]
    rec_secs = [float(d.total_recovery_seconds or 0) for d in docs]

    summary = {
        "documents_total": n,
        "document_count": n,  # 兼容旧字段
        "documents_formula_incomplete": sum(1 for d in docs if d.formula_incomplete),
        "formula_candidates": int(_sum("formula_candidates")),
        "corrupted_detected": int(_sum("corrupted_detected")),
        "recovery_attempted": int(_sum("deepseek_recovery_attempted")),
        "deepseek_recovery_attempted": int(_sum("deepseek_recovery_attempted")),
        "recovery_accepted": accepted,
        "recovery_rejected": int(_sum("recovery_rejected")),
        "recovery_usable_rate": usable_rate,
        "writebacks_total": writebacks,
        "writeback_applied": writebacks,
        "writebacks_human_correct": (
            (writebacks - int(sum(fa))) if fa and reviewed == n else None
        ),
        "writeback_human_precision": writeback_precision,
        "writeback_rollback": int(_sum("writeback_rollback")),
        "rollback_count": int(_sum("writeback_rollback")),
        "release_gate_failures": int(_sum("writeback_rollback")),  # rollback 由 gate 失败触发
        "writeback_budget_exceeded": int(_sum("writeback_budget_exceeded")),
        "budget_exceeded_count": int(_sum("writeback_budget_exceeded")),
        "unresolved_formulas": int(_sum("unresolved_formulas")),
        "formula_incomplete_documents": sum(1 for d in docs if d.formula_incomplete),
        "model_load_count": int(_sum("model_load_count")),
        "model_load_count_max": max((d.model_load_count for d in docs), default=0),
        "model_load_count_sum": int(_sum("model_load_count")),
        "ocr_calls": int(_sum("ocr_calls")),
        "ocr_seconds": round(float(_sum("ocr_seconds")), 3),
        "total_recovery_seconds": round(float(_sum("total_recovery_seconds")), 3),
        "total_document_seconds": round(float(_sum("total_document_seconds")), 3),
        "p50_document_seconds": _percentile(doc_secs, 50),
        "p95_document_seconds": _percentile(doc_secs, 95),
        "max_document_seconds": round(max(doc_secs), 3) if doc_secs else None,
        "p50_recovery_seconds": _percentile(rec_secs, 50),
        "p95_recovery_seconds": _percentile(rec_secs, 95),
        "max_recovery_seconds": round(max(rec_secs), 3) if rec_secs else None,
        "mode_counts": mode_tot,
        "false_accept": sum(fa) if fa else None,
        "true_accept": sum(ta) if ta else None,
        "false_reject": sum(fr) if fr else None,
        "false_reject_sampled": sum(fr) if fr else None,
        "docs_human_reviewed": reviewed,
        "docs_with_recovery_over_200s": sum(
            1 for d in docs if float(d.total_recovery_seconds or 0) >= 200.0
        ),
    }
    return summary


def evaluate_canary_gates(summary: dict[str, Any]) -> dict[str, Any]:
    """Phase 5A 上线门槛（严格）。未完成人工复核不得进 5B。"""
    n = int(summary.get("documents_total") or summary.get("document_count") or 0)
    fa = summary.get("false_accept")
    reviewed = int(summary.get("docs_human_reviewed") or 0)
    precision = summary.get("writeback_human_precision")
    gates = {
        "false_accept_is_zero": fa == 0 if fa is not None else None,
        "writeback_human_precision_100": precision == 1.0 if precision is not None else None,
        "human_review_complete": reviewed >= n and n > 0,
        "rollback_near_zero": int(summary.get("rollback_count") or summary.get("writeback_rollback") or 0) == 0,
        "release_gate_failures_zero": int(summary.get("release_gate_failures") or 0) == 0,
        "writeback_budget_exceeded_zero": int(summary.get("budget_exceeded_count") or summary.get("writeback_budget_exceeded") or 0) == 0,
        "model_load_count_max_le_1": int(summary.get("model_load_count_max") or 0) <= 1,
        "no_recovery_timeout_200s": int(summary.get("docs_with_recovery_over_200s") or 0) == 0,
        "sample_size_ge_20": n >= 20,
        "usable_rate_ge_80": (
            (summary.get("recovery_usable_rate") or 0) >= 0.8
            if summary.get("recovery_usable_rate") is not None
            else None
        ),
    }
    known = [v for v in gates.values() if v is not None]
    ready_for_5b = bool(known) and all(known)
    status = "hold"
    if n >= 20 and ready_for_5b:
        status = "pass"
    elif n >= 20 and fa == 0 and not gates["human_review_complete"]:
        status = "awaiting_human_review"
    elif n > 0 and (fa == 0 or fa is None) and gates["rollback_near_zero"]:
        status = "pass_seed" if n < 20 else "awaiting_human_review"
    return {
        "gates": gates,
        "ready_for_phase_5b_default_balanced": ready_for_5b,
        "status": status,
        "message": (
            "可考虑 Phase 5B：仅 Balanced 默认开启 DeepSeek high-confidence recovery"
            if ready_for_5b
            else (
                "自动指标已齐，等待 100% writeback 人工复核（false_accept 必须为 0）"
                if status == "awaiting_human_review"
                else (
                    "样本不足 20 或指标未达标；继续 canary"
                    if n < 20
                    else "未达门槛：检查 false accept / 长尾 / rollback"
                )
            )
        ),
    }


def human_review_template(docs: list[CanaryDocMetrics]) -> dict[str, Any]:
    """人工复核清单：100% 检查 writeback；抽样未修复/未触发。"""
    return {
        "instructions": [
            "100% 检查所有自动 writeback 条目（false accept 必须为 0）。",
            "抽样检查未修复公式与未触发 recovery 的公式。",
            "若发现 false accept：按 reason_code / formula type / layout / OCR mode 分类，勿整系统推倒。",
        ],
        "documents": [
            {
                "doc_id": d.doc_id,
                "writebacks_to_review": d.writeback_applied,
                "review_slots": {
                    "false_accept": d.false_accept,
                    "true_accept": d.true_accept,
                    "false_reject": d.false_reject,
                },
            }
            for d in docs
        ],
    }


def ensure_canary_dirs() -> None:
    ensure_dirs()
    CANARY_DIR.mkdir(parents=True, exist_ok=True)
    (CANARY_DIR / "docs").mkdir(parents=True, exist_ok=True)
    (CANARY_DIR / "reviews").mkdir(parents=True, exist_ok=True)


def write_canary_manifest(pdf_paths: list[Path]) -> Path:
    """登记 canary 样本清单（覆盖单栏/双栏等由人工标注）。"""
    ensure_canary_dirs()
    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "target_sample_size": "20-50",
        "coverage_hints": [
            "single_column",
            "two_column",
            "scanned",
            "digital_pdf",
            "few_formulas",
            "many_formulas",
            "table_dense",
            "publisher_variety",
        ],
        "documents": [
            {
                "doc_id": p.stem,
                "path": str(p),
                "layout": "",
                "source_type": "",
                "notes": "",
            }
            for p in pdf_paths
        ],
        "versions": pipeline_versions(),
    }
    CANARY_MANIFEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return CANARY_MANIFEST


def run_phase5a_canary_seed(*, out_path: Path | None = None) -> dict[str, Any]:
    """用现有 O-018 产物启动 canary 统计；不改识别参数、不强制 GPU。"""
    ensure_canary_dirs()
    docs = [ingest_o018_artifacts()]
    summary = aggregate_canary(docs)
    gates = evaluate_canary_gates(summary)
    review = human_review_template(docs)

    payload = attach_versions(
        {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "phase": "5A",
            "frozen": [
                "ocr_params",
                "bbox",
                "extractor",
                "gate",
                "scheduler",
            ],
            "summary": summary,
            "gates": gates,
            "documents": [d.to_dict() for d in docs],
            "human_review": review,
            "next_steps": [
                "向 debug/formula_benchmark/canary/manifest.json 登记 20~50 篇 PDF",
                "对每篇跑 limited production（Balanced 显式），写入 canary/docs/*.json",
                "100% 人工复核 writeback；false_accept 必须保持 0",
                "达标后再进入 Phase 5B：仅 Balanced 默认开启 DeepSeek high-confidence recovery",
            ],
        }
    )

    CANARY_REVIEW.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
    dest = out_path or (BENCHMARK_RUNS / "phase5a_canary_seed.json")
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    payload["output_path"] = str(dest)
    payload["review_path"] = str(CANARY_REVIEW)
    return payload


def discover_pdfs(roots: list[Path], *, limit: int = 50) -> list[Path]:
    found: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        found.extend(sorted(root.rglob("*.pdf")))
        if len(found) >= limit:
            break
    return found[:limit]
