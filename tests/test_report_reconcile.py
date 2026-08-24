# -*- coding: utf-8 -*-
from __future__ import annotations

from app.formula.config import FormulaConfig
from app.formula.report_reconcile import reconcile_report_after_deepseek
from app.formula.types import FormulaQAReport


def _sample_report() -> FormulaQAReport:
    report = FormulaQAReport(
        corrupted_formula_count=2,
        recovery_attempted_count=2,
        recovery_success_count=0,
        recovery_failed_count=2,
        fallback=2,
        formula_failures=[
            {
                "candidate_id": "page8_eqi8",
                "raw": r"p _ { t + 1 } = p _ { t } Q",
                "lifecycle": "recovery_failed",
                "failure_stage": "ocr",
            },
            {
                "candidate_id": "page8_eqi3",
                "raw": r"VI ( H , H ^ { \prime } )",
                "lifecycle": "recovery_failed",
                "failure_stage": "geometry",
            },
        ],
        details=[
            {
                "status": "recovery_failed",
                "lifecycle": "recovery_failed",
                "preview": r"p _ { t + 1 } = p _ { t } Q",
            },
            {
                "status": "recovery_failed",
                "lifecycle": "recovery_failed",
                "preview": r"VI ( H , H ^ { \prime } )",
            },
        ],
    )
    report.deepseek_shadow = {
        "summary": {"accepted": 2, "rejected": 0, "attempted": 2},
        "pages": [
            {
                "execution": {
                    "candidates": [
                        {
                            "candidate_id": "page8_eqi8",
                            "original": r"p _ { t + 1 } = p _ { t } Q",
                            "gate_accepted": True,
                            "would_replace": True,
                        },
                        {
                            "candidate_id": "page8_eqi3",
                            "original": r"VI ( H , H ^ { \prime } )",
                            "gate_accepted": True,
                            "would_replace": True,
                        },
                    ]
                }
            }
        ],
    }
    report.writeback = {
        "applied_count": 1,
        "skipped_count": 1,
        "entries": [
            {
                "candidate_id": "page8_eqi8",
                "accepted": True,
                "writeback_applied": False,
                "skip_reason": "multi_formula_alignment_ambiguous",
                "original": r"p _ { t + 1 } = p _ { t } Q",
            },
            {
                "candidate_id": "page8_eqi3",
                "accepted": True,
                "writeback_applied": True,
                "original": r"VI ( H , H ^ { \prime } )",
            },
        ],
    }
    return report


def test_reconcile_syncs_recovery_counts_with_shadow():
    report = _sample_report()
    reconcile_report_after_deepseek(report, "$$\nVI=1\n$$", FormulaConfig())

    assert report.recovery_success_count == 2
    assert report.recovery_failed_count == 0
    assert all(f["lifecycle"] == "recovery_success" for f in report.formula_failures)
    assert report.formula_failures[0]["writeback_skip_reason"]


def test_reconcile_updates_details_lifecycle():
    report = _sample_report()
    reconcile_report_after_deepseek(report, "$$\nVI=1\n$$", FormulaConfig())

    assert all(d["lifecycle"] == "recovery_success" for d in report.details)


def test_document_quality_matches_writeback_skips():
    report = _sample_report()
    reconcile_report_after_deepseek(report, "$$\nVI=1\n$$", FormulaConfig())

    assert report.document_quality is not None
    assert report.document_quality.formula_failures == 1
    assert "writeback_skipped" in report.document_quality.reasons
    assert not report.document_quality.publishable
