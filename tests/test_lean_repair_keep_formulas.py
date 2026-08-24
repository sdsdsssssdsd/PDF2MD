# -*- coding: utf-8 -*-
"""Lean Balanced：UI enrich OFF 时仍须跑 FormulaPipeline，且 Docling 解析导出 LaTeX 种子。"""
from __future__ import annotations

from pathlib import Path

from app.workers.docling_worker import ConversionWorker


def _worker(**kw):
    base = dict(
        output_root=Path("."),
        per_folder=False,
        ocr_mode="auto",
        formula_recovery_preset="balanced",
    )
    base.update(kw)
    return ConversionWorker([], **base)


def test_lean_repair_keeps_formulas_when_docling_enrich_off():
    w = _worker(
        keep_formulas=False,  # GUI Lean：enrich OFF
        deepseek_limited_production=True,
    )
    assert w._docling_formula_enrich is False
    assert w._repair_keep_formulas is True
    assert w._parse_keep_formulas() is True


def test_no_ds_and_enrich_off_skips_formula_pipeline():
    w = _worker(
        keep_formulas=False,
        deepseek_limited_production=False,
    )
    assert w._docling_formula_enrich is False
    assert w._repair_keep_formulas is False
    assert w._parse_keep_formulas() is False


def test_enrich_on_without_ds_still_repairs():
    w = _worker(
        keep_formulas=True,
        deepseek_limited_production=False,
    )
    assert w._docling_formula_enrich is True
    assert w._repair_keep_formulas is True
