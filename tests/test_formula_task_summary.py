# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path


def _load_qa(name: str) -> dict:
    p = Path(__file__).resolve().parents[1] / "logs" / "experiment" / name / f"{name}.formula_qa.json"
    return json.loads(p.read_text(encoding="utf-8"))


def test_o003_metrics_after_k3_style():
    from app.diagnostics.formula_task_summary import formula_metrics_from_qa, format_formula_fraction

    qa = _load_qa("O-003_Peach2019_DataDrivenClustering")
    rec, post, total = formula_metrics_from_qa(qa)
    assert total == 15
    assert rec == 15
    assert post == 15
    assert format_formula_fraction(rec, total) == "15/15"
    assert format_formula_fraction(post, total) == "15/15"


def test_shadow_accept_without_writeback_shows_gap():
    from app.diagnostics.formula_task_summary import formula_metrics_from_qa

    qa = {
        "formula_count": 15,
        "recovery_attempted_count": 9,
        "recovery_success_count": 7,
        "writeback": {"applied_count": 0},
    }
    rec, post, total = formula_metrics_from_qa(qa)
    assert total == 15
    assert rec == 13  # 6 untouched + 7 recognized
    assert post == 6  # 6 untouched + 0 written back


def test_no_recovery_uses_validated():
    from app.diagnostics.formula_task_summary import formula_metrics_from_qa

    qa = {"formula_count": 10, "validated": 10, "recovery_attempted_count": 0}
    assert formula_metrics_from_qa(qa) == (10, 10, 10)


def test_empty_qa():
    from app.diagnostics.formula_task_summary import (
        formula_column_labels,
        formula_metrics_from_qa,
        format_formula_fraction,
    )

    assert formula_metrics_from_qa(None) == (None, None, None)
    assert format_formula_fraction(None, None) == "—"
    assert formula_column_labels(None) == ("—", "—")


def test_load_formula_qa_prefers_newer_mtime(tmp_path: Path):
    from app.diagnostics.formula_task_summary import load_formula_qa_for_task

    out = tmp_path / "out"
    exp = tmp_path / "exp"
    out.mkdir()
    exp.mkdir()
    old = out / "paper.formula_qa.json"
    new = exp / "paper.formula_qa.json"
    old.write_text('{"formula_count": 1, "validated": 0}', encoding="utf-8")
    new.write_text('{"formula_count": 9, "validated": 9}', encoding="utf-8")
    import os
    import time

    os.utime(old, (time.time() - 100, time.time() - 100))
    os.utime(new, (time.time(), time.time()))
    qa = load_formula_qa_for_task(
        pdf_stem="paper", out_dir=out, experiment_dir=exp
    )
    assert qa is not None
    assert qa["formula_count"] == 9

