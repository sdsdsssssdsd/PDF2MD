# -*- coding: utf-8 -*-
"""k5 第一轮模型矩阵（仅 benchmark / shadow，不改生产 Lean 默认）。

L0 Docling 原公式
L1 UniMERNet legacy specialist
L2 DeepSeek-OCR-2 current（legacy baseline）
L3 DeepSeek 768 + formula prompt（最后一次公平诊断）
P1 PP-FormulaNet_plus-M
P2 PP-FormulaNet_plus-L
P3 PaddleOCR-VL-1.6 crop
"""
from __future__ import annotations

from dataclasses import dataclass

from app.formula.backends import (
    SPECIALIST_PP_L,
    SPECIALIST_PP_M,
    SPECIALIST_UNIMERNET,
    VLM_DEEPSEEK_OCR2,
    VLM_PADDLE_VL_16,
)
from app.ocr import PROMPT_DOCUMENT, PROMPT_FORMULA_LATEX


@dataclass(frozen=True)
class K5ExperimentSpec:
    experiment_id: str
    label: str
    backend: str
    prompt: str = ""
    image_size: int = 0
    formula_render_scale: float = 2.0
    role: str = "challenger"


K5_EXPERIMENTS: dict[str, K5ExperimentSpec] = {
    "L0": K5ExperimentSpec(
        experiment_id="L0",
        label="Docling original latex",
        backend="docling",
        role="parser_baseline",
    ),
    "L1": K5ExperimentSpec(
        experiment_id="L1",
        label="UniMERNet legacy specialist",
        backend=SPECIALIST_UNIMERNET,
        role="legacy_specialist",
    ),
    "L2": K5ExperimentSpec(
        experiment_id="L2",
        label="DeepSeek-OCR-2 current 640 + document prompt",
        backend=VLM_DEEPSEEK_OCR2,
        prompt=PROMPT_DOCUMENT,
        image_size=640,
        role="legacy_baseline",
    ),
    "L3": K5ExperimentSpec(
        experiment_id="L3",
        label="DeepSeek 768 + formula→LaTeX prompt",
        backend=VLM_DEEPSEEK_OCR2,
        prompt=PROMPT_FORMULA_LATEX,
        image_size=768,
        role="legacy_fairness",
    ),
    "P1": K5ExperimentSpec(
        experiment_id="P1",
        label="PP-FormulaNet_plus-M",
        backend=SPECIALIST_PP_M,
        role="primary_candidate",
    ),
    "P2": K5ExperimentSpec(
        experiment_id="P2",
        label="PP-FormulaNet_plus-L",
        backend=SPECIALIST_PP_L,
        role="quality_candidate",
    ),
    "P3": K5ExperimentSpec(
        experiment_id="P3",
        label="PaddleOCR-VL-1.6 crop",
        backend=VLM_PADDLE_VL_16,
        role="vlm_fallback",
    ),
}


K5_RECOGNITION_ONLY = ("L1", "L2", "L3", "P1", "P2", "P3")
K5_PRODUCTION_PIPELINE = ("L0", "L2", "P1", "P3")
