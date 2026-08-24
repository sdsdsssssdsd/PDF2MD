# -*- coding: utf-8 -*-
"""7.2C-read post-OCR audit 单测。"""
from __future__ import annotations

from app.diagnostics.post_ocr_audit import audit_post_ocr_rows


def test_audit_flags_zero_missed_when_raw_not_mathy():
    rows = [
        {
            "gate_accepted": False,
            "failure_class": "extraction_failure",
            "gate_reason": "no_equation_blocks",
            "error": "ocr_result_bad:no_equation_blocks",
            "eq_number": "11",
            "raw_output": "using Markov Stability (MS). Time warping similarity (1)",
            "selected_latex": "",
            "salvage_used": False,
            "timing": {"ocr_seconds": 2.0},
        },
        {
            "gate_accepted": True,
            "failure_class": "accepted",
            "gate_reason": "gain_accept",
            "eq_number": "12",
            "raw_output": r"\[ K=\frac{a}{b} \quad (12) \]",
            "selected_latex": r"K=\frac{a}{b}",
            "salvage_used": True,
            "timing": {"ocr_seconds": 2.5},
        },
    ]
    out = audit_post_ocr_rows(rows, document_id="t")
    assert out["extractor_missed_share_of_wasted"] == 0.0
    assert out["recommendation"] in {
        "sequential_ranking_72d",
        "sequential_ranking_or_crop_quality",
    }


def test_audit_counts_missed_valid_raw():
    rows = [
        {
            "gate_accepted": False,
            "failure_class": "extraction_failure",
            "gate_reason": "no_equation_blocks",
            "eq_number": "3",
            "raw_output": r"text then \frac{a}{b} + \sum x_i still no block",
            "selected_latex": "",
            "salvage_used": False,
            "extractor_method": "none",
            "timing": {"ocr_seconds": 5.0},
        }
    ]
    out = audit_post_ocr_rows(rows, document_id="t")
    assert out["extractor_missed_valid_raw_seconds"] == 5.0
    assert out["recommendation"] == "narrow_extractor_fix"
