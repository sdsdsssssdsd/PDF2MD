"""Formula Pipeline：Detection / Validation / Recovery / Fallback / ReleaseGate。

硬规则：
- Normalizer NEVER guesses formulas.
- formula-not-decoded 只能来自 RECOVERY_FAILED（且 debug 模式才进 MD）。
- 禁止根据上下文猜写标准公式。
"""
from __future__ import annotations

from app.formula.config import FormulaConfig, formula_config_for_preset, formula_config_for_deepseek_limited_production
from app.formula.pipeline import FormulaPipeline, FormulaPipelineResult
from app.formula.types import FormulaCandidate, FormulaLifecycle, FormulaQAReport

__all__ = [
    "FormulaConfig",
    "FormulaCandidate",
    "FormulaLifecycle",
    "FormulaPipeline",
    "FormulaPipelineResult",
    "FormulaQAReport",
    "formula_config_for_preset",
    "formula_config_for_deepseek_limited_production",
]
