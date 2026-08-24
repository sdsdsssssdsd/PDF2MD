# -*- coding: utf-8 -*-
"""实验结果聚合：从 timings / formula_qa / failure_memory 生成决策表与 Markdown。"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class DocExperimentRow:
    document: str
    timings_path: str = ""
    qa_path: str = ""
    run_id: str = ""
    batch_id: str = ""  # 同一次「开始转换」队列共享
    mtime: float = 0.0
    label: str = ""  # 图表用：document 或 document@run_id

    total_seconds: float | None = None
    docling_seconds: float | None = None
    asset_seconds: float | None = None
    repair_seconds: float | None = None
    batch_cold_start_seconds: float | None = None
    batch_steady_state_seconds: float | None = None
    ocr_inference_seconds: float | None = None
    model_cold_start: float | None = None
    deepseek_load: float | None = None
    deepseek_blocking_load: float | None = None
    deepseek_load_overlap: float | None = None

    attempted: int | None = None
    accepted: int | None = None
    rejected: int | None = None
    accept_rate: float | None = None
    cost_per_recovered_formula: float | None = None
    seconds_per_accept: float | None = None
    ocr_calls_per_accept: float | None = None
    recovery_efficiency: float | None = None
    profile: str = ""
    cold_start_affected: bool = False

    first_accept_attempt: int | None = None
    last_accept_attempt: int | None = None
    accept_positions: list[int] = field(default_factory=list)
    cumulative_accept_curve: list[int] = field(default_factory=list)
    accept_curve_auc: float | None = None

    failure_class_counts: dict[str, int] = field(default_factory=dict)
    wasted_ocr_seconds_by_class: dict[str, float] = field(default_factory=dict)
    cost_breakdown: dict[str, float] = field(default_factory=dict)
    recovery: dict[str, Any] = field(default_factory=dict)
    raw_timings: dict[str, Any] = field(default_factory=dict)
    raw_shadow_summary: dict[str, Any] = field(default_factory=dict)

    def chart_label(self) -> str:
        if self.label:
            return self.label
        if self.run_id:
            return f"{self.document}@{self.run_id[-6:]}"
        return self.document

    def to_dict(self) -> dict[str, Any]:
        return {
            "document": self.document,
            "label": self.chart_label(),
            "run_id": self.run_id,
            "batch_id": self.batch_id,
            "timings_path": self.timings_path,
            "qa_path": self.qa_path,
            "mtime": self.mtime,
            "total_seconds": self.total_seconds,
            "docling_seconds": self.docling_seconds,
            "asset_seconds": self.asset_seconds,
            "repair_seconds": self.repair_seconds,
            "batch_cold_start_seconds": self.batch_cold_start_seconds,
            "batch_steady_state_seconds": self.batch_steady_state_seconds,
            "ocr_inference_seconds": self.ocr_inference_seconds,
            "model_cold_start": self.model_cold_start,
            "deepseek_load": self.deepseek_load,
            "deepseek_blocking_load": self.deepseek_blocking_load,
            "deepseek_load_overlap": self.deepseek_load_overlap,
            "attempted": self.attempted,
            "accepted": self.accepted,
            "rejected": self.rejected,
            "accept_rate": self.accept_rate,
            "cost_per_recovered_formula": self.cost_per_recovered_formula,
            "seconds_per_accept": self.seconds_per_accept,
            "ocr_calls_per_accept": self.ocr_calls_per_accept,
            "recovery_efficiency": self.recovery_efficiency,
            "profile": self.profile,
            "cold_start_affected": self.cold_start_affected,
            "first_accept_attempt": self.first_accept_attempt,
            "last_accept_attempt": self.last_accept_attempt,
            "accept_positions": list(self.accept_positions),
            "cumulative_accept_curve": list(self.cumulative_accept_curve),
            "accept_curve_auc": self.accept_curve_auc,
            "failure_class_counts": dict(self.failure_class_counts),
            "wasted_ocr_seconds_by_class": dict(self.wasted_ocr_seconds_by_class),
            "cost_breakdown": dict(self.cost_breakdown),
            "recovery": dict(self.recovery),
            "raw_timings": dict(self.raw_timings),
            "raw_shadow_summary": dict(self.raw_shadow_summary),
        }


@dataclass
class ExperimentBatch:
    roots: list[str] = field(default_factory=list)
    collected_at: str = ""
    rows: list[DocExperimentRow] = field(default_factory=list)
    failure_memory_summary: dict[str, Any] = field(default_factory=dict)

    @property
    def batch_cold_start_seconds(self) -> float:
        return float(
            sum(float(r.batch_cold_start_seconds or r.model_cold_start or 0.0) for r in self.rows)
        )

    @property
    def batch_steady_state_seconds(self) -> float:
        return float(
            sum(
                float(
                    r.batch_steady_state_seconds
                    if r.batch_steady_state_seconds is not None
                    else max(0.0, float(r.total_seconds or 0.0) - float(r.batch_cold_start_seconds or r.model_cold_start or 0.0))
                )
                for r in self.rows
            )
        )


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _safe_int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _iter_timings(roots: list[Path]) -> list[Path]:
    found: list[Path] = []
    for root in roots:
        if not root or not root.exists():
            continue
        # 扁平 + 子目录 + 再下一层（独立文件夹 / 批量子目录）
        found.extend(root.glob("timings_*.json"))
        found.extend(root.glob("*/timings_*.json"))
        found.extend(root.glob("*/*/timings_*.json"))
    uniq: dict[str, Path] = {}
    for p in found:
        uniq[str(p.resolve())] = p
    return list(uniq.values())


def _iter_formula_qa(roots: list[Path]) -> list[Path]:
    found: list[Path] = []
    for root in roots:
        if not root or not root.exists():
            continue
        found.extend(root.glob("*.formula_qa.json"))
        found.extend(root.glob("*/*.formula_qa.json"))
        found.extend(root.glob("*/*/*.formula_qa.json"))
    uniq: dict[str, Path] = {}
    for p in found:
        uniq[str(p.resolve())] = p
    return list(uniq.values())


def _stem_from_timings(data: dict[str, Any], path: Path) -> str:
    pdf = data.get("pdf") or ""
    if pdf:
        return Path(str(pdf)).stem
    # 同目录找 md / qa
    parent = path.parent
    for qa in parent.glob("*.formula_qa.json"):
        return qa.name.replace(".formula_qa.json", "")
    return path.stem.replace("timings_", "")


def _merge_shadow(row: DocExperimentRow, shadow: dict[str, Any] | None) -> None:
    if not isinstance(shadow, dict):
        return
    sm = shadow.get("summary") if isinstance(shadow.get("summary"), dict) else shadow
    if not isinstance(sm, dict):
        return
    row.attempted = _safe_int(sm.get("attempted", sm.get("ocr_calls")))
    row.accepted = _safe_int(sm.get("accepted"))
    row.rejected = _safe_int(sm.get("rejected"))
    row.accept_rate = _safe_float(sm.get("accept_rate"))
    if row.accept_rate is None and row.attempted and row.accepted is not None and row.attempted:
        row.accept_rate = row.accepted / row.attempted
    row.ocr_inference_seconds = _safe_float(sm.get("ocr_inference_seconds"))
    row.cost_per_recovered_formula = _safe_float(sm.get("cost_per_recovered_formula"))
    row.seconds_per_accept = _safe_float(sm.get("seconds_per_accept"))
    row.first_accept_attempt = _safe_int(sm.get("first_accept_attempt"))
    row.last_accept_attempt = _safe_int(sm.get("last_accept_attempt"))
    row.accept_curve_auc = _safe_float(sm.get("accept_curve_auc"))
    pos = sm.get("accept_positions")
    if isinstance(pos, list):
        row.accept_positions = [int(x) for x in pos if str(x).isdigit() or isinstance(x, int)]
    curve = sm.get("cumulative_accept_curve")
    if isinstance(curve, list):
        row.cumulative_accept_curve = [int(x) for x in curve]
    fcc = sm.get("failure_class_counts")
    if isinstance(fcc, dict):
        row.failure_class_counts = {str(k): int(v) for k, v in fcc.items()}
    cb = sm.get("cost_breakdown")
    if isinstance(cb, dict):
        row.cost_breakdown = {
            str(k): float(v) for k, v in cb.items() if isinstance(v, (int, float))
        }
    row.cold_start_affected = bool(sm.get("cold_start_affected"))
    prof = sm.get("document_recovery_profile")
    if isinstance(prof, dict):
        row.profile = str(prof.get("profile") or row.profile or "")
        if not row.wasted_ocr_seconds_by_class:
            w = prof.get("wasted_ocr_seconds_by_class")
            if isinstance(w, dict):
                row.wasted_ocr_seconds_by_class = {
                    str(k): float(v) for k, v in w.items() if isinstance(v, (int, float))
                }
        if row.first_accept_attempt is None:
            row.first_accept_attempt = _safe_int(prof.get("first_accept_attempt"))
        if row.last_accept_attempt is None:
            row.last_accept_attempt = _safe_int(prof.get("last_accept_attempt"))
        if not row.accept_positions and isinstance(prof.get("accept_positions"), list):
            row.accept_positions = [int(x) for x in prof["accept_positions"]]
        if not row.cumulative_accept_curve and isinstance(
            prof.get("cumulative_accept_curve"), list
        ):
            row.cumulative_accept_curve = [int(x) for x in prof["cumulative_accept_curve"]]
        if row.accept_curve_auc is None:
            row.accept_curve_auc = _safe_float(prof.get("accept_curve_auc"))
        if row.cost_per_recovered_formula is None:
            row.cost_per_recovered_formula = _safe_float(
                prof.get("cost_per_recovered_formula")
            )
        if row.seconds_per_accept is None:
            row.seconds_per_accept = _safe_float(prof.get("seconds_per_accept"))
        if row.ocr_calls_per_accept is None:
            row.ocr_calls_per_accept = _safe_float(prof.get("ocr_calls_per_accept"))
        if row.recovery_efficiency is None:
            row.recovery_efficiency = _safe_float(prof.get("recovery_efficiency"))
        if not row.profile:
            row.profile = str(prof.get("profile") or "")


def _row_from_timings(tp: Path, data: dict[str, Any]) -> DocExperimentRow:
    stem = _stem_from_timings(data, tp)
    t = data.get("timings") if isinstance(data.get("timings"), dict) else {}
    run_id = str(data.get("run_id") or tp.stem.replace("timings_", ""))
    batch_id = str(data.get("batch_id") or t.get("batch_id") or "")
    row = DocExperimentRow(
        document=stem,
        timings_path=str(tp),
        run_id=run_id,
        batch_id=batch_id,
        mtime=tp.stat().st_mtime,
        label=f"{stem}@{run_id[-8:]}" if run_id else stem,
        total_seconds=_safe_float(t.get("total")),
        docling_seconds=_safe_float(t.get("docling")),
        asset_seconds=_safe_float(t.get("asset")),
        repair_seconds=_safe_float(t.get("repair_total")),
        batch_cold_start_seconds=_safe_float(t.get("batch_cold_start_seconds")),
        batch_steady_state_seconds=_safe_float(t.get("batch_steady_state_seconds")),
        model_cold_start=_safe_float(t.get("model_cold_start")),
        deepseek_load=_safe_float(t.get("deepseek_load")),
        deepseek_blocking_load=_safe_float(t.get("deepseek_blocking_load")),
        deepseek_load_overlap=_safe_float(t.get("deepseek_load_overlap")),
        ocr_inference_seconds=_safe_float(t.get("ocr_inference_seconds")),
        raw_timings=dict(t),
    )
    if row.model_cold_start is None:
        row.model_cold_start = _safe_float(t.get("deepseek_load"))
    rec = t.get("recovery") if isinstance(t.get("recovery"), dict) else {}
    if rec:
        row.recovery = dict(rec)
        row.attempted = _safe_int(rec.get("attempted"))
        row.accepted = _safe_int(rec.get("accepted"))
        row.rejected = _safe_int(rec.get("rejected"))
        row.accept_rate = _safe_float(rec.get("accept_rate"))
        row.cost_per_recovered_formula = _safe_float(
            rec.get("cost_per_recovered_formula")
        )
        row.seconds_per_accept = _safe_float(rec.get("seconds_per_accept"))
        row.profile = str(rec.get("profile") or "")
    if isinstance(t.get("document_recovery_profile"), dict):
        _merge_shadow(
            row, {"summary": {"document_recovery_profile": t["document_recovery_profile"]}}
        )
    if isinstance(t.get("recovery_cost_breakdown"), dict):
        row.cost_breakdown = {
            str(k): float(v)
            for k, v in t["recovery_cost_breakdown"].items()
            if isinstance(v, (int, float))
        }

    qa = tp.parent / f"{stem}.formula_qa.json"
    if not qa.is_file():
        cands = list(tp.parent.glob(f"{stem}*.formula_qa.json"))
        qa = cands[0] if cands else qa
    if qa.is_file():
        row.qa_path = str(qa)
        qa_data = _load_json(qa) or {}
        shadow = qa_data.get("deepseek_shadow")
        _merge_shadow(row, shadow)
        if isinstance(shadow, dict) and isinstance(shadow.get("summary"), dict):
            row.raw_shadow_summary = dict(shadow["summary"])
    return row


def collect_experiment_results(
    roots: list[Path | str],
    *,
    prefer_latest_per_doc: bool = False,
    max_docs: int | None = None,
) -> ExperimentBatch:
    """扫描导出目录，默认收集**全部** timings 与孤立 formula_qa（不按 recovery 过滤）。

    prefer_latest_per_doc=True 时每篇只保留最新一轮；默认 False = 全量 runs。
    """
    root_paths = [Path(r) for r in roots if r]
    batch = ExperimentBatch(
        roots=[str(p) for p in root_paths],
        collected_at=datetime.now().astimezone().isoformat(timespec="seconds"),
    )

    try:
        from app.diagnostics.failure_memory import default_failure_memory_root

        fm_sum = default_failure_memory_root() / "summary.json"
        if fm_sum.is_file():
            data = _load_json(fm_sum)
            if data:
                batch.failure_memory_summary = data
            # 也挂上 events 计数
            ev = default_failure_memory_root() / "events.jsonl"
            if ev.is_file():
                try:
                    n = sum(1 for ln in ev.read_text(encoding="utf-8").splitlines() if ln.strip())
                    batch.failure_memory_summary = dict(batch.failure_memory_summary)
                    batch.failure_memory_summary["events_count"] = n
                except Exception:
                    pass
    except Exception:
        pass

    timing_paths = _iter_timings(root_paths)
    if prefer_latest_per_doc:
        by_stem: dict[str, tuple[float, Path, dict[str, Any]]] = {}
        for tp in timing_paths:
            data = _load_json(tp)
            if not data:
                continue
            stem = _stem_from_timings(data, tp)
            mtime = tp.stat().st_mtime
            prev = by_stem.get(stem)
            if prev and prev[0] >= mtime:
                continue
            by_stem[stem] = (mtime, tp, data)
        timing_items = [(p, d) for _, p, d in by_stem.values()]
    else:
        timing_items = []
        for tp in timing_paths:
            data = _load_json(tp)
            if data:
                timing_items.append((tp, data))

    rows: list[DocExperimentRow] = []
    seen_qa: set[str] = set()
    for tp, data in timing_items:
        row = _row_from_timings(tp, data)
        if row.qa_path:
            seen_qa.add(str(Path(row.qa_path).resolve()))
        rows.append(row)

    # 孤立 formula_qa（无对应 timings 的也收进来）
    for qa in _iter_formula_qa(root_paths):
        key = str(qa.resolve())
        if key in seen_qa:
            continue
        stem = qa.name.replace(".formula_qa.json", "")
        qa_data = _load_json(qa) or {}
        row = DocExperimentRow(
            document=stem,
            qa_path=str(qa),
            run_id="",
            mtime=qa.stat().st_mtime,
            label=stem,
        )
        shadow = qa_data.get("deepseek_shadow")
        _merge_shadow(row, shadow)
        if isinstance(shadow, dict) and isinstance(shadow.get("summary"), dict):
            row.raw_shadow_summary = dict(shadow["summary"])
        # 顶层 QA 计数也保留
        for k in (
            "corrupted_formula_count",
            "recovery_attempted_count",
            "recovery_success_count",
            "recovery_failed_count",
        ):
            if k in qa_data and row.attempted is None and k == "recovery_attempted_count":
                row.attempted = _safe_int(qa_data.get(k))
            if k == "recovery_success_count" and row.accepted is None:
                row.accepted = _safe_int(qa_data.get(k))
            if k == "recovery_failed_count" and row.rejected is None:
                row.rejected = _safe_int(qa_data.get(k))
        if row.accept_rate is None and row.attempted and row.accepted is not None:
            row.accept_rate = row.accepted / row.attempted
        rows.append(row)

    rows.sort(key=lambda r: (r.mtime, r.document, r.run_id))
    if max_docs is not None and max_docs > 0:
        rows = rows[-max_docs:]
    batch.rows = rows
    return batch


SESSION_GAP_SECONDS = 2 * 3600  # 无 batch_id 的旧数据回退用


def rows_for_latest_batch(
    rows: list[DocExperimentRow],
    *,
    gap_seconds: float = SESSION_GAP_SECONDS,
) -> list[DocExperimentRow]:
    """返回最近一次「开始转换」同批跑完的记录（共享 batch_id）。

    新数据：同一次队列转换写入相同 batch_id。
    旧数据无 batch_id 时，回退为按 mtime 间隙近似切分（不保证等同同批）。
    """
    if not rows:
        return []
    with_batch = [r for r in rows if r.batch_id]
    if with_batch:
        by_batch: dict[str, list[DocExperimentRow]] = {}
        for r in with_batch:
            by_batch.setdefault(r.batch_id, []).append(r)
        latest_id = max(
            by_batch,
            key=lambda bid: max(x.mtime for x in by_batch[bid]),
        )
        latest = by_batch[latest_id]
        return sorted(latest, key=lambda r: (r.mtime, r.document, r.run_id))

    # legacy：无 batch_id
    ordered = sorted(rows, key=lambda r: (r.mtime, r.document, r.run_id))
    sessions: list[list[DocExperimentRow]] = []
    current: list[DocExperimentRow] = [ordered[0]]
    for prev, row in zip(ordered, ordered[1:]):
        if row.mtime - prev.mtime > gap_seconds:
            sessions.append(current)
            current = [row]
        else:
            current.append(row)
    sessions.append(current)
    latest = sessions[-1]
    return sorted(latest, key=lambda r: (r.mtime, r.document, r.run_id))


# 兼容旧名
rows_for_latest_run = rows_for_latest_batch


def format_experiment_markdown(batch: ExperimentBatch) -> str:
    """决策表 Markdown（仅表格，不含曲线/Failure Memory/全量 JSON）。"""
    lines: list[str] = []
    lines.append(
        "| Document | attempted | accepted | rejected | accept_rate | "
        "cost/accept | profile | first→last | curve_auc | total | cold | repair |"
    )
    lines.append(
        "|---|---:|---:|---:|---:|---:|---|---|---:|---:|---:|---:|"
    )
    for r in batch.rows:
        ar = f"{r.accept_rate:.2%}" if r.accept_rate is not None else "—"
        cpa = (
            f"{r.cost_per_recovered_formula:.1f}"
            if r.cost_per_recovered_formula is not None
            else "—"
        )
        auc = f"{r.accept_curve_auc:.3f}" if r.accept_curve_auc is not None else "—"
        fl = "—"
        if r.first_accept_attempt is not None:
            fl = f"{r.first_accept_attempt}→{r.last_accept_attempt or r.first_accept_attempt}"
        cold = r.batch_cold_start_seconds
        if cold is None:
            cold = r.model_cold_start
        lines.append(
            "| {doc} | {att} | {acc} | {rej} | {ar} | {cpa} | {prof} | {fl} | {auc} | "
            "{tot} | {cold} | {rep} |".format(
                doc=r.document[:40],
                att=r.attempted if r.attempted is not None else "—",
                acc=r.accepted if r.accepted is not None else "—",
                rej=r.rejected if r.rejected is not None else "—",
                ar=ar,
                cpa=cpa,
                prof=r.profile or "—",
                fl=fl,
                auc=auc,
                tot=f"{r.total_seconds:.1f}" if r.total_seconds is not None else "—",
                cold=f"{cold:.1f}" if cold is not None else "—",
                rep=f"{r.repair_seconds:.1f}" if r.repair_seconds is not None else "—",
            )
        )
    lines.append("")
    return "\n".join(lines)
