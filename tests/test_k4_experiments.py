# -*- coding: utf-8 -*-
from __future__ import annotations

from app.ocr import PROMPT_DOCUMENT, PROMPT_FORMULA_LATEX
from app.ocr.k4_experiments import K4_EXPERIMENTS, benchmark_config_for_experiment
from app.ocr.k4_failure_taxonomy import classify_failure_layer


def test_k4_experiment_matrix():
    assert set(K4_EXPERIMENTS) == {"A", "B", "C", "D", "E"}
    assert K4_EXPERIMENTS["A"].image_size == 640
    assert K4_EXPERIMENTS["B"].image_size == 768
    assert K4_EXPERIMENTS["C"].prompt == PROMPT_FORMULA_LATEX
    assert K4_EXPERIMENTS["D"].formula_render_scale == 2.5
    assert K4_EXPERIMENTS["E"].baseline_recognizer == "unimernet"
    assert K4_EXPERIMENTS["E"].run_deepseek_formula is False


def test_benchmark_config_for_experiment():
    cfg = benchmark_config_for_experiment(K4_EXPERIMENTS["C"])
    assert cfg.image_size == 768
    assert cfg.prompt == PROMPT_FORMULA_LATEX
    assert cfg.formula_render_scale == 2.0
    assert cfg.experiment_only is True


def test_failure_layer_taxonomy():
    assert classify_failure_layer(exact_normalized_match=True) == "ok"
    assert (
        classify_failure_layer(
            raw_ocr_contains_gold="yes",
            extractor_selected_gold="no",
            exact_normalized_match=False,
        )
        == "extractor"
    )
    assert classify_failure_layer(ocr_error="timeout") == "ocr"


def test_formula_prompt_defined():
    assert "LaTeX only" in PROMPT_FORMULA_LATEX
    assert K4_EXPERIMENTS["A"].prompt == PROMPT_DOCUMENT
