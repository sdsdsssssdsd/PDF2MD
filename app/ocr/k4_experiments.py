# -*- coding: utf-8 -*-
"""k4 公式级 A/B 实验预设（仅 benchmark，不改生产 Lean 默认）。

实验矩阵（DeepSeek 公式 crop，O-018 等 gold corpus）：
  A  640 + document prompt + scale 2.0
  B  768 + document prompt + scale 2.0
  C  768 + formula→LaTeX prompt + scale 2.0
  D  768 + formula→LaTeX prompt + scale 2.5
  E  UniMERNet baseline（专用公式模型对照）
"""
from __future__ import annotations

from dataclasses import dataclass

from app.ocr import PROMPT_DOCUMENT, PROMPT_FORMULA_LATEX
from app.ocr.deepseek_benchmark import DeepSeekBenchmarkConfig


@dataclass(frozen=True)
class K4ExperimentSpec:
    experiment_id: str
    label: str
    prompt: str
    image_size: int
    formula_render_scale: float
    baseline_recognizer: str = "pix2tex"
    run_baseline: bool = False
    run_deepseek_formula: bool = True
    run_deepseek_region: bool = False
    run_deepseek_page: bool = False


K4_EXPERIMENTS: dict[str, K4ExperimentSpec] = {
    "A": K4ExperimentSpec(
        experiment_id="A",
        label="DS-OCR2 640 + document prompt",
        prompt=PROMPT_DOCUMENT,
        image_size=640,
        formula_render_scale=2.0,
    ),
    "B": K4ExperimentSpec(
        experiment_id="B",
        label="DS-OCR2 768 + document prompt",
        prompt=PROMPT_DOCUMENT,
        image_size=768,
        formula_render_scale=2.0,
    ),
    "C": K4ExperimentSpec(
        experiment_id="C",
        label="DS-OCR2 768 + formula→LaTeX prompt",
        prompt=PROMPT_FORMULA_LATEX,
        image_size=768,
        formula_render_scale=2.0,
    ),
    "D": K4ExperimentSpec(
        experiment_id="D",
        label="DS-OCR2 768 + formula→LaTeX + scale 2.5",
        prompt=PROMPT_FORMULA_LATEX,
        image_size=768,
        formula_render_scale=2.5,
    ),
    "E": K4ExperimentSpec(
        experiment_id="E",
        label="UniMERNet formula baseline",
        prompt=PROMPT_DOCUMENT,
        image_size=768,
        formula_render_scale=2.0,
        baseline_recognizer="unimernet",
        run_baseline=True,
        run_deepseek_formula=False,
    ),
}


def benchmark_config_for_experiment(
    spec: K4ExperimentSpec,
    *,
    allow_cpu: bool = False,
) -> DeepSeekBenchmarkConfig:
    return DeepSeekBenchmarkConfig(
        enabled=True,
        experiment_only=True,
        prompt=spec.prompt,
        image_size=spec.image_size,
        formula_render_scale=spec.formula_render_scale,
        baseline_recognizer=spec.baseline_recognizer,
        run_baseline=spec.run_baseline or spec.experiment_id == "E",
        run_deepseek_formula=spec.run_deepseek_formula,
        run_deepseek_region=spec.run_deepseek_region,
        run_deepseek_page=spec.run_deepseek_page,
        allow_cpu=allow_cpu,
    )
