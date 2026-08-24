# -*- coding: utf-8 -*-
"""k5：公式识别 backend 名称（与具体模型解耦，配置决定实现）。"""
from __future__ import annotations

# 生产默认仍是 legacy DeepSeek；k5_specialist 仅 shadow / 显式配置后启用
BACKEND_MODE_LEGACY_DEEPSEEK = "legacy_deepseek"
BACKEND_MODE_K5_SPECIALIST = "k5_specialist"

SPECIALIST_PP_M = "pp_formulanet_plus_m"
SPECIALIST_PP_L = "pp_formulanet_plus_l"
SPECIALIST_UNIMERNET = "unimernet"
SPECIALIST_NULL = "null"

VLM_PADDLE_VL_16 = "paddleocr_vl_1_6"
VLM_DEEPSEEK_OCR2 = "deepseek_ocr2"
VLM_OVISOCR2 = "ovisocr2"

PP_FORMULANET_ALIASES = {
    "pp_formulanet_plus_m": "PP-FormulaNet_plus-M",
    "pp-formulanet-plus-m": "PP-FormulaNet_plus-M",
    "ppformulanet-m": "PP-FormulaNet_plus-M",
    "pp_formulanet_plus_l": "PP-FormulaNet_plus-L",
    "pp-formulanet-plus-l": "PP-FormulaNet_plus-L",
    "ppformulanet-l": "PP-FormulaNet_plus-L",
}

PADDLE_VL_ALIASES = {
    "paddleocr_vl_1_6",
    "paddleocr-vl-1.6",
    "paddlevl16",
    "paddleocr_vl",
}


def paddle_model_name(backend: str) -> str:
    key = (backend or "").strip().lower().replace(" ", "_")
    if key in PP_FORMULANET_ALIASES:
        return PP_FORMULANET_ALIASES[key]
    if key in PADDLE_VL_ALIASES:
        return "PaddleOCR-VL-1.6"
    return backend


def is_pp_formulanet(backend: str) -> bool:
    key = (backend or "").strip().lower().replace(" ", "_")
    return key in PP_FORMULANET_ALIASES


def is_paddle_vl(backend: str) -> bool:
    return (backend or "").strip().lower().replace(" ", "_") in PADDLE_VL_ALIASES


def uses_deepseek_pending(backend_mode: str, vlm_fallback_backend: str) -> bool:
    """VLM 槽是否仍走现有 DeepSeek %dsid: pending（legacy 或显式 deepseek）。"""
    mode = (backend_mode or BACKEND_MODE_LEGACY_DEEPSEEK).strip().lower()
    if mode != BACKEND_MODE_K5_SPECIALIST:
        return True
    vlm = (vlm_fallback_backend or "").strip().lower().replace("-", "_")
    return vlm.startswith("deepseek")
