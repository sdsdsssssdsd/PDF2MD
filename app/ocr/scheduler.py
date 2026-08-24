"""Cost-aware RecoveryScheduler v1（Phase 4A）。

只负责：选 FORMULA / FORMULA_BATCH / PAGE / PAGE_REUSE / SKIP，并控预算。
不改 DeepSeek 参数、Gate、Extractor；不引入 region；不增加 retry。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from app.ocr.cost_model import RecoveryCostModel


class RecoveryMode(str, Enum):
    FORMULA = "formula"
    FORMULA_BATCH = "formula_batch"
    PAGE = "page"
    PAGE_REUSE = "page_reuse"
    SKIP = "skip"


@dataclass
class SchedulerConfig:
    """Balanced 默认；region 永不启用。

    Phase 5B-Perf：coverage_first 时 soft budget 不得导致某式 0 attempt；
    hard_limit / circuit breaker 才可中止。
    """

    enabled: bool = True
    page_safety_factor: float = 1.2
    min_page_formula_count: int = 8
    max_formulas_per_document: int = 10
    max_pages_per_document: int = 2
    # soft：optional 阶段参考；coverage_first 下不阻断 mandatory
    max_total_recovery_seconds: float = 90.0
    # hard：整篇安全上限（含 mandatory overcommit）
    hard_limit_seconds: float = 300.0
    coverage_first: bool = True
    guarantee_one_attempt: bool = True
    formula_timeout_seconds: float = 30.0
    max_page_usable_deficit: int = 1
    # v1 不跑 region
    allow_region: bool = False
    allow_retry: bool = False


@dataclass
class DocumentRecoveryBudget:
    """文档级预算计数（Scheduler 自管，不改旧 BudgetTracker 语义）。"""

    formulas_used: int = 0
    pages_used: int = 0
    seconds_used: float = 0.0
    mandatory_attempts: int = 0
    optional_attempts: int = 0
    decisions: list[dict[str, Any]] = field(default_factory=list)

    def soft_exceeded(self, cfg: SchedulerConfig, *, extra_seconds: float = 0.0) -> bool:
        soft = float(cfg.max_total_recovery_seconds or 0.0)
        if soft <= 0:
            return False
        return self.seconds_used + extra_seconds > soft

    def hard_exceeded(self, cfg: SchedulerConfig, *, extra_seconds: float = 0.0) -> bool:
        hard = float(getattr(cfg, "hard_limit_seconds", 0.0) or 0.0)
        if hard <= 0:
            return False
        return self.seconds_used + extra_seconds > hard

    def would_exceed(
        self,
        *,
        cfg: SchedulerConfig,
        extra_formulas: int = 0,
        extra_pages: int = 0,
        extra_seconds: float = 0.0,
        stage: str = "optional",
    ) -> tuple[bool, str]:
        """stage=mandatory|optional。

        coverage_first + mandatory：仅 hard / 公式页数硬帽可阻断；soft 不阻断。
        """
        if cfg.max_formulas_per_document > 0 and (
            self.formulas_used + extra_formulas > cfg.max_formulas_per_document
        ):
            # coverage_first：公式数量帽在 mandatory 仍允许 overcommit 到「每式一次」
            if not (
                cfg.coverage_first
                and stage == "mandatory"
                and bool(cfg.guarantee_one_attempt)
            ):
                return True, "budget_exceeded_formulas"
        if cfg.max_pages_per_document > 0 and (
            self.pages_used + extra_pages > cfg.max_pages_per_document
        ):
            if stage != "mandatory" or not cfg.coverage_first:
                return True, "budget_exceeded_pages"
        if self.hard_exceeded(cfg, extra_seconds=extra_seconds):
            return True, "hard_limit_exceeded"
        if stage != "mandatory" or not cfg.coverage_first:
            if cfg.max_total_recovery_seconds > 0 and (
                self.seconds_used + extra_seconds > cfg.max_total_recovery_seconds
            ):
                return True, "budget_exceeded"
        return False, ""

    def record(
        self,
        *,
        formulas: int = 0,
        pages: int = 0,
        seconds: float = 0.0,
        decision: dict[str, Any] | None = None,
    ) -> None:
        self.formulas_used += max(0, int(formulas))
        self.pages_used += max(0, int(pages))
        self.seconds_used += max(0.0, float(seconds))
        if decision:
            self.decisions.append(decision)


@dataclass
class RecoveryCostEstimate:
    formula_count: int
    estimated_formula_seconds: float
    estimated_page_seconds: float
    safety_factor: float
    chosen_mode: RecoveryMode
    reason: str
    page: int | None = None
    page_cost_with_safety: float = 0.0
    estimated_model_load_seconds: float = 0.0
    page_cached: bool = False
    budget_remaining_seconds: float | None = None
    trace: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["chosen_mode"] = self.chosen_mode.value
        return d


class RecoveryScheduler:
    """按页决策；禁止 count≥2→PAGE；禁止 region/retry。"""

    def __init__(
        self,
        *,
        cost_model: RecoveryCostModel | None = None,
        config: SchedulerConfig | None = None,
        budget: DocumentRecoveryBudget | None = None,
    ) -> None:
        self.cost = cost_model or RecoveryCostModel(auto_load=False, auto_save=False)
        self.config = config or SchedulerConfig()
        self.budget = budget or DocumentRecoveryBudget()

    def decide_page(
        self,
        *,
        page: int,
        corrupted_formula_count: int,
        page_cached: bool = False,
        page_features: dict[str, Any] | None = None,
    ) -> RecoveryCostEstimate:
        cfg = self.config
        n = max(0, int(corrupted_formula_count))
        safety = float(cfg.page_safety_factor)

        formula_unit = self.cost.estimate_formula_unit()
        model_load = self.cost.estimate_model_load()
        formula_cost = model_load + n * formula_unit
        page_raw = 0.0 if page_cached else (model_load + self.cost.estimate_page(page_features))
        page_with_safety = page_raw * safety if not page_cached else 0.0

        remaining = None
        if cfg.max_total_recovery_seconds > 0:
            remaining = max(0.0, cfg.max_total_recovery_seconds - self.budget.seconds_used)

        base_trace = {
            "page": page,
            "corrupted_formulas": n,
            "formula_cost_estimate": round(formula_cost, 3),
            "page_cost_estimate": round(page_raw, 3),
            "page_cost_with_safety": round(page_with_safety, 3),
            "model_load_estimate": round(model_load, 3),
            "model_loaded": self.cost.runtime.model_loaded,
            "page_cached": page_cached,
            "min_page_formula_count": cfg.min_page_formula_count,
            "safety_factor": safety,
        }

        def _result(
            mode: RecoveryMode,
            reason: str,
            *,
            est_seconds: float,
        ) -> RecoveryCostEstimate:
            trace = {**base_trace, "selected": mode.value, "reason": reason}
            return RecoveryCostEstimate(
                formula_count=n,
                estimated_formula_seconds=round(formula_cost, 3),
                estimated_page_seconds=round(page_raw, 3),
                safety_factor=safety,
                chosen_mode=mode,
                reason=reason,
                page=page,
                page_cost_with_safety=round(page_with_safety, 3),
                estimated_model_load_seconds=round(model_load, 3),
                page_cached=page_cached,
                budget_remaining_seconds=remaining,
                trace=trace,
            )

        if not cfg.enabled:
            return _result(RecoveryMode.SKIP, "scheduler_disabled", est_seconds=0.0)

        if n <= 0:
            return _result(RecoveryMode.SKIP, "no_corrupted_formulas", est_seconds=0.0)

        if cfg.allow_region:
            # 硬边界：v1 即使配置误开也不走 region
            pass

        # 1) 已有 page cache → 边际 OCR 成本 ≈ 0，直接复用
        if page_cached:
            exceed, br = self.budget.would_exceed(
                cfg=cfg,
                extra_formulas=n,
                extra_pages=0,
                extra_seconds=0.05,
                stage="optional",
            )
            if exceed and not (cfg.coverage_first and br == "budget_exceeded"):
                return _result(RecoveryMode.SKIP, br or "budget_exceeded", est_seconds=0.0)
            return _result(RecoveryMode.PAGE_REUSE, "page_cache_hit", est_seconds=0.0)

        # 2) 单式：永远 FORMULA（一次 OCR）
        if n == 1:
            exceed, br = self.budget.would_exceed(
                cfg=cfg,
                extra_formulas=1,
                extra_pages=0,
                extra_seconds=formula_cost,
                stage="mandatory" if cfg.coverage_first else "optional",
            )
            if exceed:
                return _result(RecoveryMode.SKIP, br or "budget_exceeded", est_seconds=formula_cost)
            return _result(RecoveryMode.FORMULA, "single_formula", est_seconds=formula_cost)

        # 3) 门槛：未达 min_page_formula_count → 强制 FORMULA_BATCH
        if n < int(cfg.min_page_formula_count):
            exceed, br = self.budget.would_exceed(
                cfg=cfg,
                extra_formulas=n,
                extra_pages=0,
                extra_seconds=formula_cost,
                stage="mandatory" if cfg.coverage_first else "optional",
            )
            if exceed:
                return _result(RecoveryMode.SKIP, br or "budget_exceeded", est_seconds=formula_cost)
            return _result(
                RecoveryMode.FORMULA_BATCH,
                "below_min_page_formula_count",
                est_seconds=formula_cost,
            )

        # 4) 成本比较 + 质量门
        quality_ok = self.cost.page_usable_not_worse(max_deficit=cfg.max_page_usable_deficit)
        page_cheaper = page_with_safety < formula_cost

        if page_cheaper and quality_ok:
            exceed, br = self.budget.would_exceed(
                cfg=cfg,
                extra_formulas=n,
                extra_pages=1,
                extra_seconds=page_raw,
                stage="optional",
            )
            if exceed:
                # page 超预算则退回 formula；formula 也超则 SKIP（mandatory 仍尽量 formula）
                exceed_f, br_f = self.budget.would_exceed(
                    cfg=cfg,
                    extra_formulas=n,
                    extra_pages=0,
                    extra_seconds=formula_cost,
                    stage="mandatory" if cfg.coverage_first else "optional",
                )
                if exceed_f:
                    return _result(
                        RecoveryMode.SKIP, br_f or "budget_exceeded", est_seconds=formula_cost
                    )
                return _result(
                    RecoveryMode.FORMULA_BATCH,
                    "page_budget_fallback_formula",
                    est_seconds=formula_cost,
                )
            return _result(RecoveryMode.PAGE, "page_cheaper_with_safety", est_seconds=page_raw)

        # 质量不足
        if page_cheaper and not quality_ok:
            reason = "page_quality_insufficient"
        else:
            reason = "formula_batch_cheaper"

        exceed, br = self.budget.would_exceed(
            cfg=cfg,
            extra_formulas=n,
            extra_pages=0,
            extra_seconds=formula_cost,
            stage="mandatory" if cfg.coverage_first else "optional",
        )
        if exceed:
            return _result(RecoveryMode.SKIP, br or "budget_exceeded", est_seconds=formula_cost)
        return _result(RecoveryMode.FORMULA_BATCH, reason, est_seconds=formula_cost)

    def commit_decision(
        self,
        estimate: RecoveryCostEstimate,
        *,
        actual_seconds: float | None = None,
    ) -> None:
        """执行后记账；actual_seconds 缺省用估计值。"""
        mode = estimate.chosen_mode
        if mode == RecoveryMode.SKIP:
            self.budget.record(decision=estimate.to_dict())
            return
        secs = float(actual_seconds) if actual_seconds is not None else float(
            estimate.estimated_formula_seconds
            if mode in (RecoveryMode.FORMULA, RecoveryMode.FORMULA_BATCH)
            else estimate.estimated_page_seconds
        )
        pages = 1 if mode == RecoveryMode.PAGE else 0
        formulas = int(estimate.formula_count)
        if mode == RecoveryMode.PAGE_REUSE:
            pages = 0
            secs = float(actual_seconds) if actual_seconds is not None else 0.0
        self.budget.record(
            formulas=formulas,
            pages=pages,
            seconds=secs,
            decision=estimate.to_dict(),
        )
