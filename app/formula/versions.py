"""Pipeline 组件版本号 — Phase 5A QA metadata（冻结识别逻辑时仍随代码小幅递增）。"""
from __future__ import annotations

from typing import Any

# 语义版本：大改识别链路才升 major；本阶段只做观测，minor/patch 记录接线版本
PIPELINE_VERSION = "5.0.0-canary"
DEEPSEEK_MODEL_ID = "DeepSeek-OCR-2"
EXTRACTOR_VERSION = "3A.1"
GATE_VERSION = "3B.1"
SCHEDULER_VERSION = "4A.1"
WRITEBACK_VERSION = "4D.1"
COST_MODEL_VERSION = "4B.1"


def pipeline_versions(*, deepseek_model: str | None = None) -> dict[str, str]:
    return {
        "pipeline_version": PIPELINE_VERSION,
        "deepseek_model": deepseek_model or DEEPSEEK_MODEL_ID,
        "extractor_version": EXTRACTOR_VERSION,
        "gate_version": GATE_VERSION,
        "scheduler_version": SCHEDULER_VERSION,
        "writeback_version": WRITEBACK_VERSION,
        "cost_model_version": COST_MODEL_VERSION,
    }


def attach_versions(payload: dict[str, Any], *, deepseek_model: str | None = None) -> dict[str, Any]:
    out = dict(payload)
    out["versions"] = pipeline_versions(deepseek_model=deepseek_model)
    return out
