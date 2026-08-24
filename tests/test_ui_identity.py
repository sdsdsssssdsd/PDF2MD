# -*- coding: utf-8 -*-
from app.ui.identity import (
    CORE_COLUMNS,
    classify_deepseek_state,
    classify_pipeline_stage,
    formula_profile_identity,
    formula_profile_tone,
)
from app.ui.pipeline_classify import STAGE_LABELS


def test_core_columns_count():
    assert CORE_COLUMNS == 9


def test_lean_balanced_identity():
    assert (
        formula_profile_identity(preset="balanced", enrich=False, deepseek=True)
        == "Lean Balanced"
    )


def test_fast_quality_custom_identity():
    assert formula_profile_identity(preset="fast", enrich=False, deepseek=False) == "Fast"
    assert formula_profile_identity(preset="quality", enrich=True, deepseek=False) == "Quality"
    assert formula_profile_identity(preset="balanced", enrich=True, deepseek=True) == "Custom"


def test_classify_pipeline_stage():
    assert classify_pipeline_stage("正在转换：O-018.pdf") == "parse"
    assert classify_pipeline_stage("Asset 提示：ok") == "assets"
    assert classify_pipeline_stage("FormulaPipeline start") == "repair"
    assert classify_pipeline_stage("镜像 timings") == "mirror"
    assert classify_pipeline_stage("空闲") == "idle"


def test_classify_deepseek_state():
    assert classify_deepseek_state("DeepSeek：并行预热 Worker") == "warming"
    assert classify_deepseek_state("DeepSeek：批前加载完成 1.2s") == "warm"
    assert classify_deepseek_state("DeepSeek 预热跳过：x") == "unavailable"


def test_profile_tone_and_stage_labels():
    assert formula_profile_tone("Lean Balanced") == "info"
    assert formula_profile_tone("Quality") == "warning"
    assert STAGE_LABELS["repair"] == "Formula Repair"
