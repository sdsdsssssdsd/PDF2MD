# -*- coding: utf-8 -*-
"""Phase 7A：本地 Failure Memory（events.jsonl + summary，fingerprint 去重）。"""
from __future__ import annotations

import hashlib
import json
import re
import threading
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.diagnostics.anomaly_detector import assess_anomaly
from app.utils.paths import APP_ROOT

_LOCK = threading.Lock()
SCHEMA_VERSION = 2


def default_failure_memory_root() -> Path:
    return APP_ROOT / "debug" / "failure_memory"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _norm_blob(s: str, *, limit: int = 800) -> str:
    t = (s or "").strip().lower()
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"\\qquad|\\quad", " ", t)
    t = re.sub(r"[（(]\s*[\w.]+\s*[）)]\s*$", "", t)
    return t[:limit]


def fingerprint_parts(
    *,
    failure_class: str,
    gate_reason: str,
    original: str,
    raw_output: str,
    extractor_method: str,
    anomaly_class: str = "",
) -> str:
    payload = "|".join(
        [
            (failure_class or "").strip().lower(),
            _norm_blob(gate_reason, limit=200),
            _norm_blob(original, limit=400),
            _norm_blob(raw_output, limit=600),
            (extractor_method or "").strip().lower(),
            (anomaly_class or "").strip().lower(),
        ]
    )
    digest = hashlib.sha256(payload.encode("utf-8", errors="ignore")).hexdigest()
    return f"sha256:{digest}"


class FailureMemory:
    """本地持久化：events.jsonl（事实）+ summary.json（聚合）。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else default_failure_memory_root()
        self.events_path = self.root / "events.jsonl"
        self.summary_path = self.root / "summary.json"
        self.cases_dir = self.root / "cases"
        self.index_path = self.root / "fingerprint_index.json"

    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.cases_dir.mkdir(parents=True, exist_ok=True)
        for name in (
            "extraction_failure",
            "validation_failure",
            "identity_failure",
            "alignment_failure",
            "context_strong_conflict",
            "recognition_failure",
            "unknown",
            "other",
        ):
            (self.cases_dir / name).mkdir(parents=True, exist_ok=True)
        if not self.events_path.is_file():
            self.events_path.write_text("", encoding="utf-8")
        if not self.index_path.is_file():
            self.index_path.write_text("{}", encoding="utf-8")

    def _load_index(self) -> dict[str, Any]:
        self.ensure()
        try:
            return json.loads(self.index_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_index(self, idx: dict[str, Any]) -> None:
        self.index_path.write_text(
            json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def record_event(self, event: dict[str, Any]) -> dict[str, Any]:
        """写入/合并一条异常事件。返回最终 event（含 occurrence_count）。"""
        with _LOCK:
            self.ensure()
            idx = self._load_index()
            fp = str(event.get("fingerprint") or "")
            now = _now_iso()
            if fp and fp in idx:
                meta = idx[fp]
                meta["occurrence_count"] = int(meta.get("occurrence_count") or 1) + 1
                meta["last_seen"] = now
                runs = list(meta.get("runs_seen") or [])
                rid = str(event.get("run_id") or "")
                if rid and rid not in runs:
                    runs.append(rid)
                    if len(runs) > 50:
                        runs = runs[-50:]
                meta["runs_seen"] = runs
                docs = list(meta.get("documents") or [])
                did = str(event.get("document_id") or "")
                if did and did not in docs:
                    docs.append(did)
                meta["documents"] = docs
                meta["total_ocr_seconds"] = float(meta.get("total_ocr_seconds") or 0.0) + float(
                    event.get("ocr_seconds") or 0.0
                )
                meta["total_recovery_seconds"] = float(
                    meta.get("total_recovery_seconds") or 0.0
                ) + float(event.get("recovery_seconds") or 0.0)
                meta["total_cold_start_seconds"] = float(
                    meta.get("total_cold_start_seconds") or 0.0
                ) + float(event.get("cold_start_seconds") or 0.0)
                idx[fp] = meta
                event = dict(event)
                event["occurrence_count"] = meta["occurrence_count"]
                event["first_seen"] = meta.get("first_seen") or now
                event["last_seen"] = now
                event["deduped"] = True
            else:
                event = dict(event)
                event["occurrence_count"] = 1
                event["first_seen"] = now
                event["last_seen"] = now
                event["deduped"] = False
                if fp:
                    idx[fp] = {
                        "occurrence_count": 1,
                        "first_seen": now,
                        "last_seen": now,
                        "runs_seen": [str(event.get("run_id") or "")],
                        "documents": [str(event.get("document_id") or "")],
                        "failure_class": event.get("failure_class"),
                        "anomaly_class": event.get("anomaly_class"),
                        "actionability": event.get("actionability"),
                        "total_ocr_seconds": float(event.get("ocr_seconds") or 0.0),
                        "total_recovery_seconds": float(
                            event.get("recovery_seconds") or 0.0
                        ),
                        "total_cold_start_seconds": float(
                            event.get("cold_start_seconds") or 0.0
                        ),
                    }
                # 样例落地 cases/
                self._write_case_sample(event)

            with self.events_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
            self._save_index(idx)
            return event

    def _write_case_sample(self, event: dict[str, Any]) -> None:
        fc = str(event.get("failure_class") or "unknown")
        folder = self.cases_dir / (fc if (self.cases_dir / fc).is_dir() else "other")
        folder.mkdir(parents=True, exist_ok=True)
        fp = str(event.get("fingerprint") or "nofp")[-16:]
        path = folder / f"{fp}.json"
        if path.is_file():
            return
        slim = {
            k: event.get(k)
            for k in (
                "schema_version",
                "timestamp",
                "run_id",
                "document_id",
                "page",
                "candidate_id",
                "eq_number",
                "failure_class",
                "anomaly_class",
                "actionability",
                "gate_reason",
                "extractor_method",
                "salvage_used",
                "original",
                "raw_output",
                "selected_latex",
                "fingerprint",
            )
        }
        path.write_text(json.dumps(slim, ensure_ascii=False, indent=2), encoding="utf-8")

    def rebuild_summary(self) -> dict[str, Any]:
        self.ensure()
        idx = self._load_index()
        by_fc: Counter[str] = Counter()
        by_ac: Counter[str] = Counter()
        by_act: Counter[str] = Counter()
        wasted_ocr_by_fc: Counter[str] = Counter()
        wasted_calls_by_fc: Counter[str] = Counter()
        high: list[dict[str, Any]] = []
        costly: list[dict[str, Any]] = []
        for fp, meta in idx.items():
            fc = str(meta.get("failure_class") or "unknown")
            ac = str(meta.get("anomaly_class") or "")
            act = str(meta.get("actionability") or "low")
            occ = int(meta.get("occurrence_count") or 1)
            ocr_cost = float(meta.get("total_ocr_seconds") or 0.0)
            by_fc[fc] += occ
            wasted_ocr_by_fc[fc] += ocr_cost
            wasted_calls_by_fc[fc] += occ
            if ac:
                by_ac[ac] += occ
            by_act[act] += occ
            entry = {
                "fingerprint": fp,
                "occurrences": occ,
                "failure_class": fc,
                "anomaly_class": ac,
                "actionability": act,
                "documents": meta.get("documents") or [],
                "last_seen": meta.get("last_seen"),
                "total_ocr_seconds": round(ocr_cost, 3),
                "total_recovery_seconds": round(
                    float(meta.get("total_recovery_seconds") or 0.0), 3
                ),
            }
            if act == "high":
                high.append(entry)
            costly.append(entry)
        high.sort(key=lambda x: (-float(x["total_ocr_seconds"]), -int(x["occurrences"])))
        costly.sort(key=lambda x: (-float(x["total_ocr_seconds"]), -int(x["occurrences"])))
        repeated = sum(1 for m in idx.values() if int(m.get("occurrence_count") or 1) > 1)
        summary = {
            "schema_version": SCHEMA_VERSION,
            "updated_at": _now_iso(),
            "unique_fingerprints": len(idx),
            "repeated_anomalies": repeated,
            "new_anomalies_note": "see events with deduped=false",
            "failure_class_totals": dict(by_fc.most_common()),
            "anomaly_class_totals": dict(by_ac.most_common()),
            "actionability_totals": dict(by_act),
            "top_high_actionability": high[:20],
            "top_costly_failures": costly[:20],
            "wasted_ocr_seconds_by_class": {
                k: round(v, 3) for k, v in wasted_ocr_by_fc.most_common()
            },
            "wasted_ocr_calls_by_class": dict(wasted_calls_by_fc.most_common()),
            "top_failure_classes": by_fc.most_common(10),
        }
        self.summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return summary


def record_shadow_failures(
    rows: list[dict[str, Any]],
    *,
    run_id: str = "",
    document_id: str = "",
    pdf_path: str | Path | None = None,
    memory: FailureMemory | None = None,
    source: str = "shadow",
    document_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """从 shadow would_replace 行写入 Failure Memory。返回本批统计。"""
    mem = memory or FailureMemory()
    mem.ensure()
    doc_id = document_id or (
        Path(pdf_path).stem if pdf_path else ""
    )
    recorded = 0
    high = 0
    skipped = 0
    for row in rows or []:
        if bool(row.get("gate_accepted")):
            skipped += 1
            continue
        assessment = assess_anomaly(row)
        if not assessment.is_anomaly:
            skipped += 1
            continue
        fc = str(row.get("failure_class") or "unknown")
        timing = row.get("timing") if isinstance(row.get("timing"), dict) else {}
        ocr_s = float(
            row.get("ocr_seconds")
            or timing.get("ocr_seconds")
            or timing.get("worker_inference_seconds")
            or 0.0
        )
        rec_s = float(
            row.get("recovery_seconds")
            or timing.get("recovery_seconds")
            or ocr_s
        )
        cold_s = float(
            row.get("cold_start_seconds")
            or timing.get("cold_start_seconds")
            or 0.0
        )
        fp = fingerprint_parts(
            failure_class=fc,
            gate_reason=str(row.get("gate_reason") or ""),
            original=str(row.get("original") or ""),
            raw_output=str(row.get("raw_output") or ""),
            extractor_method=str(row.get("extractor_method") or ""),
            anomaly_class=assessment.anomaly_class,
        )
        event = {
            "schema_version": SCHEMA_VERSION,
            "timestamp": _now_iso(),
            "run_id": run_id or "",
            "document_id": doc_id,
            "page": row.get("page"),
            "candidate_id": row.get("candidate_id") or "",
            "eq_number": row.get("eq_number") or "",
            "failure_class": fc,
            "anomaly_class": assessment.anomaly_class,
            "actionability": assessment.actionability,
            "anomaly_reason": assessment.reason,
            "gate_reason": row.get("gate_reason") or "",
            "extractor_method": row.get("extractor_method") or "",
            "salvage_used": bool(row.get("salvage_used")),
            "original": (row.get("original") or "")[:1500],
            "raw_output": (row.get("raw_output") or "")[:2000],
            "selected_latex": (row.get("selected_latex") or row.get("recovered") or "")[
                :1500
            ],
            "ocr_calls": 1,
            "ocr_seconds": round(ocr_s, 4),
            "recovery_seconds": round(rec_s, 4),
            "cold_start_seconds": round(cold_s, 4),
            "accepted": False,
            "fingerprint": fp,
            "source": source,
            "resolved": False,
            "stage": row.get("stage") or "",
        }
        out = mem.record_event(event)
        recorded += 1
        if assessment.actionability == "high":
            high += 1
        _ = out
    summary = mem.rebuild_summary()
    out: dict[str, Any] = {
        "recorded": recorded,
        "skipped": skipped,
        "high_actionability": high,
        "summary_path": str(mem.summary_path),
        "unique_fingerprints": summary.get("unique_fingerprints"),
        "top_high_actionability": summary.get("top_high_actionability") or [],
        "top_costly_failures": summary.get("top_costly_failures") or [],
        "wasted_ocr_seconds_by_class": summary.get("wasted_ocr_seconds_by_class") or {},
        "wasted_ocr_calls_by_class": summary.get("wasted_ocr_calls_by_class") or {},
    }
    if document_profile:
        out["document_recovery_profile"] = document_profile
        out["seconds_per_accept"] = document_profile.get("seconds_per_accept")
        out["cost_per_recovered_formula"] = document_profile.get(
            "cost_per_recovered_formula"
        )
    return out
