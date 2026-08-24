"""Formula 配置：Cost-aware Recovery（debug6）+ fallback 模式。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RecoveryBudget:
    """OCR 是昂贵 optional operation，用预算而不是重试次数硬跑。"""

    max_ocr_calls_per_formula: int = 1
    # 0 = 不限制全文次数（只按「每个坏公式」预算）
    max_ocr_calls_per_document: int = 0
    # GPU UniMERNet 推理很快；首次加载模型可能几十秒，故放宽秒级预算
    max_recovery_seconds_per_formula: float = 45.0
    # 0 = 不限制全文秒数
    max_recovery_seconds_per_document: float = 0.0


# Fast / Balanced / Quality —— 只暴露三个 preset，不暴露二十个旋钮
RECOVERY_PRESETS: dict[str, dict[str, Any]] = {
    "fast": {
        "crop_render_scale": 2.0,
        "preprocess_variants": False,
        "recovery_enabled": True,
        "budget": RecoveryBudget(
            max_ocr_calls_per_formula=0,
            max_ocr_calls_per_document=0,
            max_recovery_seconds_per_formula=0.0,
            max_recovery_seconds_per_document=0.0,
        ),
    },
    "balanced": {
        "crop_render_scale": 2.0,
        "preprocess_variants": False,
        "recovery_enabled": True,
        "budget": RecoveryBudget(
            max_ocr_calls_per_formula=1,
            max_ocr_calls_per_document=0,
            max_recovery_seconds_per_formula=45.0,
            max_recovery_seconds_per_document=0.0,
        ),
    },
    "quality": {
        "crop_render_scale": 2.5,
        "preprocess_variants": False,
        "recovery_enabled": True,
        "budget": RecoveryBudget(
            max_ocr_calls_per_formula=2,
            max_ocr_calls_per_document=0,
            max_recovery_seconds_per_formula=60.0,
            max_recovery_seconds_per_document=0.0,
        ),
    },
}

PRESET_LABELS = {
    "fast": "快速",
    "balanced": "均衡（推荐）",
    "quality": "精细",
}


def normalize_preset(name: str | None) -> str:
    raw = (name or "balanced").strip().lower()
    aliases = {
        "fast": "fast",
        "快速": "fast",
        "balanced": "balanced",
        "均衡": "balanced",
        "均衡（推荐）": "balanced",
        "quality": "quality",
        "精细": "quality",
        "high": "quality",
    }
    return aliases.get(raw, "balanced")


@dataclass
class FormulaConfig:
    enabled: bool = True

    detection_enabled: bool = True
    suspicious_threshold: float = 0.65
    medium_threshold: float = 0.40

    max_quad_ratio: float = 0.12
    max_quad_run: int = 8
    max_formula_chars: int = 2500
    check_brackets: bool = True
    check_environments: bool = True

    # corruption
    corruption_len_threshold: int = 300
    corruption_min_tokens: int = 10
    corruption_semantic_ratio: float = 0.05

    # recovery preset：fast | balanced | quality（默认 Balanced）
    recovery_preset: str = "balanced"
    recovery_enabled: bool = True
    # 兼容旧字段：不再作为默认重试策略；OCR 次数以 budget 为准
    max_attempts: int = 1
    bbox_padding_x: float = 0.10
    bbox_padding_y: float = 0.12
    # Balanced 默认 2x；很小的 bbox 才自适应提到 2.5/3
    crop_render_scale: float = 2.0
    crop_small_height_pt: float = 18.0
    crop_tiny_scale: float = 3.0
    crop_small_scale: float = 2.5
    # 禁止根据上下文猜写标准公式（硬规则）
    forbid_context_formula_invention: bool = True
    budget: RecoveryBudget = field(default_factory=RecoveryBudget)

    # fallback: debug | clean | strict
    fallback_mode: str = "clean"
    fallback_marker: str = "<!-- formula-not-decoded -->"
    clean_placeholder: str = (
        "*[公式未能可靠提取 / Formula extraction failed — `{reason}`. "
        "详见同目录 `*.formula_qa.json`]*"
    )
    annotate_suspects: bool = False

    normalize_validated: bool = True
    release_gate_enabled: bool = True

    # 专用公式 OCR（不接 VLM 主链路）
    recognizer_primary: str = "unimernet"  # unimernet | pix2tex | null | pp_formulanet_plus_m
    vlm_fallback_enabled: bool = False
    preprocess_variants: bool = False

    # k5：语义 backend（生产默认 legacy_deepseek，禁止未做 A/B 就切主力）
    formula_backend_mode: str = "legacy_deepseek"  # legacy_deepseek | k5_specialist
    specialist_primary: str = "pp_formulanet_plus_m"
    specialist_quality: str = "pp_formulanet_plus_l"
    vlm_fallback_backend: str = "paddleocr_vl_1_6"
    k5_shadow_only: bool = True
    k5_require_consensus: bool = True

    # DeepSeek-OCR 2：实验开关（默认关闭，不进生产 Markdown）
    deepseek_recovery_enabled: bool = False
    deepseek_experiment_only: bool = True
    # Phase 4A：cost-aware Scheduler（默认关；开启也不改 Gate/Extractor）
    deepseek_scheduler_enabled: bool = False
    deepseek_page_safety_factor: float = 1.2
    deepseek_min_page_formula_count: int = 8
    deepseek_max_formulas_per_document: int = 10
    deepseek_max_pages_per_document: int = 2
    deepseek_max_total_recovery_seconds: float = 90.0
    # Phase 5B-Perf：soft/hard + coverage + timeout
    deepseek_hard_limit_seconds: float = 300.0
    deepseek_coverage_first: bool = True
    # Phase 7.2B0：候选重排（只改顺序；禁止 early-stop / 禁止用最终 profile）
    deepseek_candidate_prioritization: bool = True
    # Phase 7.2D：运行中每 N 次 attempt 重排剩余（只 reorder，不 stop）
    deepseek_sequential_ranking: bool = True
    deepseek_sequential_reorder_every: int = 3
    # Phase 5G：单式 hard timeout（~max(30, p95×2)）；禁 90s 长尾
    deepseek_formula_timeout_seconds: float = 30.0
    deepseek_slow_call_threshold_seconds: float = 20.0
    deepseek_slow_call_restart_count: int = 2
    deepseek_timeout_deferred_retry: bool = True
    deepseek_load_timeout_seconds: float = 240.0  # 模型加载
    deepseek_parallel_warmup: bool = True  # 与 Docling 重叠预热
    # Phase 5I：Worker 与 GUI 解耦
    deepseek_survive_gui_exit: bool = True
    deepseek_idle_unload_minutes: float = 60.0  # 0=永不 unload
    deepseek_idle_shutdown_minutes: float = 0.0  # 0=永不因 idle 杀进程
    # Phase 4B：Shadow 执行（默认关；只写 QA，不改 Markdown）
    deepseek_shadow_enabled: bool = False
    deepseek_outlier_multiplier: float = 3.0
    # Phase 4C：受控写回（默认关 + dry-run）
    deepseek_recovery_writeback_enabled: bool = False
    deepseek_recovery_writeback_dry_run: bool = True
    # Phase 4D：有限生产（默认关；仅 Balanced 显式打开）
    deepseek_limited_production_enabled: bool = False
    deepseek_max_writebacks_per_document: int = 8
    deepseek_max_writebacks_per_page: int = 4
    # 有限生产默认要求高置信；通用 4C dry-run 可不强制
    deepseek_writeback_require_high_confidence: bool = False
    # Limited Production：严重损坏跳过 UniMERNet，直接 DeepSeek
    deepseek_primary_for_severe: bool = True
    # Phase 5E：Lean Balanced — Docling enrich OFF，公式由 DeepSeek 主修；
    # recognizer_primary=null 时不 import/预热 UniMERNet
    lean_docling_balanced: bool = False
    # Phase 5H：写回 display 公式时插入 \tag{n}（还原 PDF 印刷编号）
    preserve_equation_numbers: bool = True

    extra: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.recovery_preset = normalize_preset(self.recovery_preset)
        if not isinstance(self.budget, RecoveryBudget):
            self.budget = RecoveryBudget()
        spec = RECOVERY_PRESETS[self.recovery_preset]
        default_bal = RecoveryBudget()
        budget_is_balanced_default = (
            self.budget.max_ocr_calls_per_formula == default_bal.max_ocr_calls_per_formula
            and self.budget.max_ocr_calls_per_document == default_bal.max_ocr_calls_per_document
        )
        if self.recovery_preset != "balanced" and budget_is_balanced_default:
            b = spec["budget"]
            self.budget = RecoveryBudget(
                max_ocr_calls_per_formula=b.max_ocr_calls_per_formula,
                max_ocr_calls_per_document=b.max_ocr_calls_per_document,
                max_recovery_seconds_per_formula=b.max_recovery_seconds_per_formula,
                max_recovery_seconds_per_document=b.max_recovery_seconds_per_document,
            )
            self.crop_render_scale = spec["crop_render_scale"]
            self.preprocess_variants = spec["preprocess_variants"]
            self.max_attempts = max(1, b.max_ocr_calls_per_formula)


def formula_config_for_preset(name: str | None = None, **overrides: Any) -> FormulaConfig:
    """按 Fast / Balanced / Quality 生成配置。overrides 后盖。"""
    preset = normalize_preset(name)
    spec = RECOVERY_PRESETS[preset]
    data = {
        "recovery_preset": preset,
        "crop_render_scale": spec["crop_render_scale"],
        "preprocess_variants": spec["preprocess_variants"],
        "recovery_enabled": spec["recovery_enabled"],
        "budget": RecoveryBudget(
            max_ocr_calls_per_formula=spec["budget"].max_ocr_calls_per_formula,
            max_ocr_calls_per_document=spec["budget"].max_ocr_calls_per_document,
            max_recovery_seconds_per_formula=spec["budget"].max_recovery_seconds_per_formula,
            max_recovery_seconds_per_document=spec["budget"].max_recovery_seconds_per_document,
        ),
        "max_attempts": max(1, spec["budget"].max_ocr_calls_per_formula),
    }
    data.update(overrides)
    return FormulaConfig(**data)


def formula_config_for_deepseek_limited_production(**overrides: Any) -> FormulaConfig:
    """Phase 5E：Balanced Lean = Docling 导出损坏 LaTeX 种子 + DeepSeek 主修公式。

    - recognizer_primary=null：不 import / 不预热 UniMERNet
    - lean_docling_balanced：Route 一律 DeepSeek direct（有 DeepSeek 时）
    """
    data: dict[str, Any] = {
        "recovery_preset": "balanced",
        "deepseek_limited_production_enabled": True,
        "lean_docling_balanced": True,
        "recognizer_primary": "null",
        "preserve_equation_numbers": True,
        "deepseek_shadow_enabled": True,
        "deepseek_scheduler_enabled": True,
        "deepseek_recovery_writeback_enabled": True,
        "deepseek_recovery_writeback_dry_run": False,
        # 0 = 不限制写回条数（Lean 热路径已够快，按高置信全量写回）
        "deepseek_max_writebacks_per_document": 0,
        "deepseek_max_writebacks_per_page": 0,
        "deepseek_writeback_require_high_confidence": True,
        "deepseek_experiment_only": True,
        "deepseek_recovery_enabled": False,
        "deepseek_coverage_first": True,
        "deepseek_candidate_prioritization": True,
        "deepseek_sequential_ranking": True,
        "deepseek_sequential_reorder_every": 3,
        "deepseek_hard_limit_seconds": 300.0,
        "deepseek_formula_timeout_seconds": 30.0,
        "deepseek_slow_call_threshold_seconds": 20.0,
        "deepseek_slow_call_restart_count": 2,
        "deepseek_timeout_deferred_retry": True,
        "deepseek_load_timeout_seconds": 240.0,
        "deepseek_parallel_warmup": True,
        "deepseek_survive_gui_exit": True,
        "deepseek_idle_unload_minutes": 60.0,
        "deepseek_idle_shutdown_minutes": 0.0,
        "deepseek_max_total_recovery_seconds": 180.0,
        "deepseek_primary_for_severe": True,
        # 0 = 不限制 OCR 公式数（coverage-first mandatory 本就不该被帽截断）
        "deepseek_max_formulas_per_document": 0,
    }
    data.update(overrides)
    if normalize_preset(str(data.get("recovery_preset") or "balanced")) != "balanced":
        raise ValueError("deepseek_limited_production_requires_balanced_preset")
    return formula_config_for_preset("balanced", **data)


def formula_config_for_k5_specialist(
    preset: str = "balanced",
    **overrides: Any,
) -> FormulaConfig:
    """k5 shadow：PP-FormulaNet primary + VLM fallback。默认不写生产 Markdown。"""
    from app.formula.backends import (
        BACKEND_MODE_K5_SPECIALIST,
        SPECIALIST_PP_L,
        SPECIALIST_PP_M,
        VLM_PADDLE_VL_16,
    )

    p = normalize_preset(preset)
    specialist = SPECIALIST_PP_L if p == "quality" else SPECIALIST_PP_M
    data: dict[str, Any] = {
        "formula_backend_mode": BACKEND_MODE_K5_SPECIALIST,
        "specialist_primary": SPECIALIST_PP_M,
        "specialist_quality": SPECIALIST_PP_L,
        "recognizer_primary": specialist,
        "vlm_fallback_backend": VLM_PADDLE_VL_16,
        "vlm_fallback_enabled": p != "fast",
        "k5_shadow_only": True,
        "k5_require_consensus": p != "fast",
        "deepseek_limited_production_enabled": False,
        "deepseek_recovery_writeback_enabled": False,
        "deepseek_recovery_writeback_dry_run": True,
        "lean_docling_balanced": False,
    }
    data.update(overrides)
    return formula_config_for_preset(p, **data)


def adaptive_hard_limit_seconds(
    corrupted_count: int,
    base: float = 300.0,
) -> float:
    """按损坏公式数放宽 hard_limit（O-003 九槽约 360s）。"""
    n = max(0, int(corrupted_count or 0))
    floor = float(base or 300.0)
    if n <= 6:
        return floor
    return max(floor, 35.0 * n + 45.0)


def deepseek_scheduler_config_from_formula(cfg: FormulaConfig) -> Any:
    """从 FormulaConfig 抽出 Phase 4A SchedulerConfig（延迟导入避免环依赖）。"""
    from app.ocr.scheduler import SchedulerConfig

    # Balanced 默认见 SchedulerConfig；Quality 可放宽
    preset = normalize_preset(cfg.recovery_preset)
    base = SchedulerConfig(
        enabled=bool(cfg.deepseek_scheduler_enabled),
        page_safety_factor=float(cfg.deepseek_page_safety_factor),
        min_page_formula_count=int(cfg.deepseek_min_page_formula_count),
        max_formulas_per_document=int(cfg.deepseek_max_formulas_per_document),
        max_pages_per_document=int(cfg.deepseek_max_pages_per_document),
        max_total_recovery_seconds=float(cfg.deepseek_max_total_recovery_seconds),
        hard_limit_seconds=float(getattr(cfg, "deepseek_hard_limit_seconds", 300.0) or 300.0),
        coverage_first=bool(getattr(cfg, "deepseek_coverage_first", True)),
        guarantee_one_attempt=bool(getattr(cfg, "deepseek_coverage_first", True)),
        formula_timeout_seconds=float(
            getattr(cfg, "deepseek_formula_timeout_seconds", 30.0) or 30.0
        ),
    )
    # Phase 5G 慢调用阈值挂在 SchedulerConfig.extra 之外：由 production_pass 写入 client
    if preset == "fast":
        base.enabled = False
        base.max_total_recovery_seconds = 0.0
    elif preset == "quality":
        base.max_total_recovery_seconds = max(base.max_total_recovery_seconds, 180.0)
        base.max_formulas_per_document = max(base.max_formulas_per_document, 30)
        base.page_safety_factor = min(base.page_safety_factor, 1.05)
    return base
