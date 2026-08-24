# -*- coding: utf-8 -*-
"""从 worker 自由文本推断只读阶段。无 Qt 依赖，供 ConversionWorker 与单测共用。"""
from __future__ import annotations


def classify_pipeline_stage(msg: str) -> str:
    """推断 parse|assets|repair|mirror|idle。不改变算法。"""
    t = msg or ""
    low = t.lower()
    if "空闲" in t:
        return "idle"
    if "镜像" in t or "experiment" in low:
        return "mirror"
    if any(k in t for k in ("Repair", "公式恢复", "FormulaPipeline", "formula_qa")):
        return "repair"
    if any(k in t for k in ("Asset", "图片", "插图", "caption", "subfigure")):
        return "assets"
    if any(k in t for k in ("解析", "Docling", "MinerU", "正在转换")):
        return "parse"
    return ""


def classify_deepseek_state(msg: str) -> str:
    t = msg or ""
    if "预热跳过" in t or "加载跳过" in t:
        return "unavailable"
    if any(k in t for k in ("预热", "加载模型", "等待并行")):
        return "warming"
    if "加载完成" in t:
        return "warm"
    return ""


STAGE_LABELS = {
    "parse": "Parsing",
    "assets": "Assets",
    "repair": "Formula Repair",
    "mirror": "Mirror",
    "idle": "Done",
    "render": "Render",
    "transcribe": "Transcribe",
    "validate": "Validate",
    "merge": "Merge",
    "figures": "Figures",
}
