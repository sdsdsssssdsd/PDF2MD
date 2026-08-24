# -*- coding: utf-8 -*-
"""实验结果聚合单测。"""
from __future__ import annotations

import json
from pathlib import Path

from app.diagnostics.experiment_report import (
    ExperimentBatch,
    collect_experiment_results,
    format_experiment_markdown,
    rows_for_latest_batch,
)


def test_collect_and_markdown(tmp_path: Path):
    stem = "O-018_Abdo2025_Stacking_SHAP"
    timings = {
        "run_id": "20260822_test",
        "batch_id": "20260822_120000",
        "pdf": str(tmp_path / f"{stem}.pdf"),
        "timings": {
            "batch_id": "20260822_120000",
            "docling": 8.0,
            "repair_total": 40.0,
            "total": 49.0,
            "batch_cold_start_seconds": 0.0,
            "batch_steady_state_seconds": 49.0,
            "ocr_inference_seconds": 39.0,
            "recovery": {
                "attempted": 7,
                "accepted": 7,
                "rejected": 0,
                "accept_rate": 1.0,
                "cost_per_recovered_formula": 7.0,
                "profile": "healthy",
            },
        },
    }
    (tmp_path / "timings_20260822_test.json").write_text(
        json.dumps(timings), encoding="utf-8"
    )
    qa = {
        "deepseek_shadow": {
            "summary": {
                "attempted": 7,
                "accepted": 7,
                "rejected": 0,
                "accept_rate": 1.0,
                "ocr_calls": 7,
                "cost_per_recovered_formula": 7.0,
                "seconds_per_accept": 5.6,
                "first_accept_attempt": 1,
                "last_accept_attempt": 7,
                "accept_positions": [1, 2, 3, 4, 5, 6, 7],
                "cumulative_accept_curve": [1, 2, 3, 4, 5, 6, 7],
                "accept_curve_auc": 0.57,
                "document_recovery_profile": {"profile": "healthy"},
            }
        }
    }
    (tmp_path / f"{stem}.formula_qa.json").write_text(
        json.dumps(qa), encoding="utf-8"
    )

    batch = collect_experiment_results([tmp_path])
    assert len(batch.rows) == 1
    r = batch.rows[0]
    assert r.document == stem
    assert r.batch_id == "20260822_120000"
    assert r.attempted == 7 and r.accepted == 7 and r.rejected == 0
    assert r.profile == "healthy"
    assert r.first_accept_attempt == 1

    md = format_experiment_markdown(batch)
    assert "O-018" in md
    assert "attempted" in md
    assert "| 7 | 7 | 0 |" in md or "| 7 | 7 |" in md
    assert "```json" not in md
    assert "全量记录" not in md
    assert "Accept curves" not in md
    assert md.strip().startswith("| Document |")


def _write_timings(
    tmp_path: Path,
    stem: str,
    run_id: str,
    *,
    batch_id: str = "",
) -> None:
    path = tmp_path / f"timings_{run_id}.json"
    path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "batch_id": batch_id,
                "pdf": str(tmp_path / f"{stem}.pdf"),
                "timings": {
                    "batch_id": batch_id,
                    "total": 10.0,
                    "repair_total": 5.0,
                    "recovery": {
                        "attempted": 1,
                        "accepted": 1,
                        "rejected": 0,
                        "accept_rate": 1.0,
                        "profile": "healthy",
                    },
                },
            }
        ),
        encoding="utf-8",
    )


def test_rows_for_latest_batch_by_shared_batch_id(tmp_path: Path):
    _write_timings(tmp_path, "O-003", "old_a", batch_id="batch_old")
    _write_timings(tmp_path, "O-018", "new_a", batch_id="batch_new")
    _write_timings(tmp_path, "O-019", "new_b", batch_id="batch_new")

    batch = collect_experiment_results([tmp_path])
    assert len(batch.rows) == 3

    latest = rows_for_latest_batch(batch.rows)
    assert len(latest) == 2
    assert {r.document for r in latest} == {"O-018", "O-019"}
    assert all(r.batch_id == "batch_new" for r in latest)

    md = format_experiment_markdown(ExperimentBatch(rows=latest))
    assert "O-018" in md
    assert "O-019" in md
    assert "O-003" not in md
