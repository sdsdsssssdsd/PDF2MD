"""FormulaConfig 分组视图：算法 / runtime / policy 拆开，不改现有扁平字段。"""
from __future__ import annotations

from dataclasses import dataclass

from app.formula.config import FormulaConfig, RecoveryBudget


@dataclass
class DetectionConfig:
    enabled: bool = True
    suspicious_threshold: float = 0.65
    medium_threshold: float = 0.40
    max_quad_ratio: float = 0.12
    max_quad_run: int = 8
    max_formula_chars: int = 2500
    check_brackets: bool = True
    check_environments: bool = True
    corruption_len_threshold: int = 300
    corruption_min_tokens: int = 10
    corruption_semantic_ratio: float = 0.05


@dataclass
class GeometryConfig:
    bbox_padding_x: float = 0.10
    bbox_padding_y: float = 0.12
    crop_render_scale: float = 2.0
    crop_small_height_pt: float = 18.0
    crop_tiny_scale: float = 3.0
    crop_small_scale: float = 2.5


@dataclass
class RecognitionConfig:
    recognizer_primary: str = "unimernet"
    vlm_fallback_enabled: bool = False
    preprocess_variants: bool = False
    formula_backend_mode: str = "legacy_deepseek"
    specialist_primary: str = "pp_formulanet_plus_m"
    specialist_quality: str = "pp_formulanet_plus_l"
    vlm_fallback_backend: str = "paddleocr_vl_1_6"
    specialist_shadow_only: bool = True
    specialist_require_consensus: bool = True
    k5_shadow_only: bool = True  # 兼容旧名
    k5_require_consensus: bool = True


@dataclass
class RoutingConfig:
    recovery_preset: str = "balanced"
    recovery_enabled: bool = True
    deepseek_coverage_first: bool = True
    deepseek_candidate_prioritization: bool = True
    deepseek_sequential_ranking: bool = True
    deepseek_sequential_reorder_every: int = 3
    lean_docling_balanced: bool = False


@dataclass
class BudgetConfig:
    budget: RecoveryBudget | None = None
    max_attempts: int = 1
    deepseek_max_formulas_per_document: int = 10
    deepseek_max_pages_per_document: int = 2
    deepseek_max_total_recovery_seconds: float = 90.0
    deepseek_hard_limit_seconds: float = 300.0


@dataclass
class WritebackConfig:
    normalize_validated: bool = True
    release_gate_enabled: bool = True
    preserve_equation_numbers: bool = True
    fallback_mode: str = "clean"
    deepseek_recovery_writeback_enabled: bool = False
    deepseek_recovery_writeback_dry_run: bool = True
    deepseek_limited_production_enabled: bool = False
    deepseek_max_writebacks_per_document: int = 8
    deepseek_max_writebacks_per_page: int = 4
    deepseek_writeback_require_high_confidence: bool = False


@dataclass
class ModelRuntimeConfig:
    """DeepSeek daemon 生命周期，不属于公式算法。"""

    deepseek_load_timeout_seconds: float = 240.0
    deepseek_formula_timeout_seconds: float = 30.0
    deepseek_parallel_warmup: bool = True
    deepseek_survive_gui_exit: bool = True
    deepseek_idle_unload_minutes: float = 60.0
    deepseek_idle_shutdown_minutes: float = 0.0


@dataclass
class FormulaConfigGroups:
    detection: DetectionConfig
    geometry: GeometryConfig
    recognition: RecognitionConfig
    routing: RoutingConfig
    budget: BudgetConfig
    writeback: WritebackConfig
    runtime: ModelRuntimeConfig


def groups_from_formula_config(cfg: FormulaConfig) -> FormulaConfigGroups:
    return FormulaConfigGroups(
        detection=DetectionConfig(
            enabled=cfg.detection_enabled,
            suspicious_threshold=cfg.suspicious_threshold,
            medium_threshold=cfg.medium_threshold,
            max_quad_ratio=cfg.max_quad_ratio,
            max_quad_run=cfg.max_quad_run,
            max_formula_chars=cfg.max_formula_chars,
            check_brackets=cfg.check_brackets,
            check_environments=cfg.check_environments,
            corruption_len_threshold=cfg.corruption_len_threshold,
            corruption_min_tokens=cfg.corruption_min_tokens,
            corruption_semantic_ratio=cfg.corruption_semantic_ratio,
        ),
        geometry=GeometryConfig(
            bbox_padding_x=cfg.bbox_padding_x,
            bbox_padding_y=cfg.bbox_padding_y,
            crop_render_scale=cfg.crop_render_scale,
            crop_small_height_pt=cfg.crop_small_height_pt,
            crop_tiny_scale=cfg.crop_tiny_scale,
            crop_small_scale=cfg.crop_small_scale,
        ),
        recognition=RecognitionConfig(
            recognizer_primary=cfg.recognizer_primary,
            vlm_fallback_enabled=cfg.vlm_fallback_enabled,
            preprocess_variants=cfg.preprocess_variants,
            formula_backend_mode=cfg.formula_backend_mode,
            specialist_primary=cfg.specialist_primary,
            specialist_quality=cfg.specialist_quality,
            vlm_fallback_backend=cfg.vlm_fallback_backend,
            specialist_shadow_only=cfg.specialist_shadow_only,
            specialist_require_consensus=cfg.specialist_require_consensus,
            k5_shadow_only=cfg.k5_shadow_only,
            k5_require_consensus=cfg.k5_require_consensus,
        ),
        routing=RoutingConfig(
            recovery_preset=cfg.recovery_preset,
            recovery_enabled=cfg.recovery_enabled,
            deepseek_coverage_first=cfg.deepseek_coverage_first,
            deepseek_candidate_prioritization=cfg.deepseek_candidate_prioritization,
            deepseek_sequential_ranking=cfg.deepseek_sequential_ranking,
            deepseek_sequential_reorder_every=cfg.deepseek_sequential_reorder_every,
            lean_docling_balanced=cfg.lean_docling_balanced,
        ),
        budget=BudgetConfig(
            budget=cfg.budget,
            max_attempts=cfg.max_attempts,
            deepseek_max_formulas_per_document=cfg.deepseek_max_formulas_per_document,
            deepseek_max_pages_per_document=cfg.deepseek_max_pages_per_document,
            deepseek_max_total_recovery_seconds=cfg.deepseek_max_total_recovery_seconds,
            deepseek_hard_limit_seconds=cfg.deepseek_hard_limit_seconds,
        ),
        writeback=WritebackConfig(
            normalize_validated=cfg.normalize_validated,
            release_gate_enabled=cfg.release_gate_enabled,
            preserve_equation_numbers=cfg.preserve_equation_numbers,
            fallback_mode=cfg.fallback_mode,
            deepseek_recovery_writeback_enabled=cfg.deepseek_recovery_writeback_enabled,
            deepseek_recovery_writeback_dry_run=cfg.deepseek_recovery_writeback_dry_run,
            deepseek_limited_production_enabled=cfg.deepseek_limited_production_enabled,
            deepseek_max_writebacks_per_document=cfg.deepseek_max_writebacks_per_document,
            deepseek_max_writebacks_per_page=cfg.deepseek_max_writebacks_per_page,
            deepseek_writeback_require_high_confidence=cfg.deepseek_writeback_require_high_confidence,
        ),
        runtime=ModelRuntimeConfig(
            deepseek_load_timeout_seconds=cfg.deepseek_load_timeout_seconds,
            deepseek_formula_timeout_seconds=cfg.deepseek_formula_timeout_seconds,
            deepseek_parallel_warmup=cfg.deepseek_parallel_warmup,
            deepseek_survive_gui_exit=cfg.deepseek_survive_gui_exit,
            deepseek_idle_unload_minutes=cfg.deepseek_idle_unload_minutes,
            deepseek_idle_shutdown_minutes=cfg.deepseek_idle_shutdown_minutes,
        ),
    )
