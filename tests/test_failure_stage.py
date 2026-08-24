# -*- coding: utf-8 -*-
from __future__ import annotations

from app.formula.fallback import infer_failure_stage
from app.formula.types import FormulaCandidate, FormulaLifecycle


def test_infer_failure_stage_geometry_no_bbox():
    c = FormulaCandidate(text="", page=None, bbox=None, issues=["docling_formula_not_decoded"])
    assert infer_failure_stage(c) == "geometry"


def test_infer_failure_stage_crop_prose():
    c = FormulaCandidate(
        text="",
        page=3,
        bbox=(0.0, 0.0, 100.0, 50.0),
        crop_class="likely_prose",
        issues=["docling_formula_not_decoded"],
    )
    assert infer_failure_stage(c) == "crop_prose"


def test_infer_failure_stage_gate_conflict():
    c = FormulaCandidate(
        text="x",
        page=3,
        bbox=(0.0, 0.0, 100.0, 50.0),
        issues=["recovery_failed"],
        recovery_attempts=1,
        status="recovery_failed",
    )
    assert infer_failure_stage(c, gate_reason="ocr_context_conflict") == "gate"


def test_failure_record_includes_stage():
    from app.formula.fallback import failure_record

    c = FormulaCandidate(
        text="",
        page=8,
        bbox=(1.0, 2.0, 3.0, 4.0),
        crop_class="likely_formula",
        geometry_source="printed_eq_anchor_v2",
        context_after="Markov Stability",
        lifecycle=FormulaLifecycle.RECOVERY_FAILED,
        issues=["docling_formula_not_decoded"],
    )
    rec = failure_record(c)
    assert rec["failure_stage"] == "ocr"
    assert rec["context_after"] == "Markov Stability"
    assert rec["geometry_source"] == "printed_eq_anchor_v2"
