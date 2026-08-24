# -*- coding: utf-8 -*-
"""k4 §14 失败分层（benchmark / 诊断专用）。"""
from __future__ import annotations


def classify_failure_layer(
    *,
    geometry_ok: bool = True,
    crop_ok: bool = True,
    raw_ocr_contains_gold: str = "—",
    extractor_selected_gold: str = "—",
    exact_normalized_match: bool = False,
    ocr_error: str = "",
) -> str:
    if not geometry_ok:
        return "detection_geometry"
    if not crop_ok:
        return "crop"
    if ocr_error:
        return "ocr"
    if exact_normalized_match:
        return "ok"
    if raw_ocr_contains_gold == "yes" and not exact_normalized_match:
        if extractor_selected_gold != "yes":
            return "extractor"
        return "gate_or_postprocess"
    if extractor_selected_gold != "yes" and raw_ocr_contains_gold != "yes":
        return "ocr"
    return "gate_or_postprocess"
