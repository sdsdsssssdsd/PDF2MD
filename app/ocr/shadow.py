"""Phase 4B Shadow Mode：按页 Scheduler → Executor，只写 QA，不改 Markdown。

Phase 5B-Perf：coverage_first 时改为文档级 round-robin mandatory：
每个 corrupted 公式至少 FORMULA×1；soft budget 不饿死后续公式；
hard_limit / circuit breaker 才可中止。
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.formula.config import FormulaConfig, deepseek_scheduler_config_from_formula
from app.formula.session import FormulaRecoverySession
from app.formula.types import FormulaCandidate
from app.ocr.cache import PageOCRCache, file_sha1
from app.ocr.circuit_breaker import CircuitBreaker, OcrFailureClass
from app.ocr.cost_model import RecoveryCostModel
from app.ocr.deepseek_health import deepseek_health_check
from app.ocr.executor import (
    CandidateExecutionResult,
    ExecutorContext,
    RecoveryExecutor,
    RecoveryExecutionResult,
    eq_number_from_candidate,
)
from app.ocr.scheduler import (
    DocumentRecoveryBudget,
    RecoveryCostEstimate,
    RecoveryMode,
    RecoveryScheduler,
)


def _cand_row(c: Any, *, stage: str = "mandatory") -> dict[str, Any]:
    timing = getattr(c, "timing", None) or {}
    if not isinstance(timing, dict):
        timing = {}
    return {
        "candidate_id": getattr(c, "candidate_id", ""),
        "page": getattr(c, "page", None),
        "eq_number": getattr(c, "eq_number", ""),
        "scheduler_mode": getattr(c, "scheduler_mode", "") or "formula",
        "gate_accepted": bool(getattr(c, "gate_accepted", False)),
        "would_replace": bool(getattr(c, "would_replace", False)),
        "original": getattr(c, "original", "") or "",
        "recovered": getattr(c, "recovered", "") or "",
        "selected_latex": getattr(c, "recovered", "") or getattr(c, "selected_latex", "") or "",
        "gate_reason": getattr(c, "gate_reason", "") or "",
        "error": getattr(c, "error", "") or "",
        "extractor_method": getattr(c, "extractor_method", "") or "",
        "failure_class": getattr(c, "failure_class", "") or "",
        "salvage_used": bool(getattr(c, "salvage_used", False)),
        "raw_output": (getattr(c, "raw_output", "") or "")[:1500],
        "stage": stage,
        "timing": timing,
        "ocr_seconds": float(timing.get("ocr_seconds") or timing.get("worker_inference_seconds") or 0.0),
        "recovery_seconds": float(timing.get("recovery_seconds") or 0.0),
        "cold_start_seconds": float(timing.get("cold_start_seconds") or 0.0),
        "model_load_seconds": float(timing.get("model_load_seconds") or 0.0),
    }


@dataclass
class ShadowPageRecord:
    page: int
    corrupted_count: int
    scheduler: dict[str, Any]
    execution: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "page": self.page,
            "corrupted_formulas": self.corrupted_count,
            "scheduler": self.scheduler,
            "execution": self.execution,
        }


@dataclass
class ShadowDocumentResult:
    enabled: bool
    write_markdown: bool = False  # Phase 4B 恒 False
    pages: list[ShadowPageRecord] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "write_markdown": self.write_markdown,
            "phase": "4B_shadow",
            "pages": [p.to_dict() for p in self.pages],
            "summary": self.summary,
        }


def group_candidates_by_page(
    candidates: list[FormulaCandidate],
) -> dict[int, list[FormulaCandidate]]:
    groups: dict[int, list[FormulaCandidate]] = defaultdict(list)
    for c in candidates:
        if c.page is None:
            continue
        groups[int(c.page)].append(c)
    return dict(sorted(groups.items()))


class ShadowRecoveryRunner:
    """文档级 shadow：decide → execute → observe/commit → QA 结构。"""

    def __init__(
        self,
        *,
        config: FormulaConfig | None = None,
        recognizer: Any = None,
        cost_model: RecoveryCostModel | None = None,
        page_cache: PageOCRCache | None = None,
        scheduler: RecoveryScheduler | None = None,
        executor: RecoveryExecutor | None = None,
    ) -> None:
        self.config = config or FormulaConfig()
        self.cost = cost_model or RecoveryCostModel(auto_load=False, auto_save=False)
        sched_cfg = deepseek_scheduler_config_from_formula(self.config)
        # shadow 开启时强制启用决策引擎；生产 deepseek_scheduler_enabled 仍可默认 False
        sched_cfg.enabled = True
        self.budget = DocumentRecoveryBudget()
        self.scheduler = scheduler or RecoveryScheduler(
            cost_model=self.cost, config=sched_cfg, budget=self.budget
        )
        self.page_cache = page_cache or PageOCRCache()
        if executor is not None:
            self.executor = executor
        else:
            if recognizer is None:
                raise ValueError("shadow_runner_requires_recognizer")
            self.executor = RecoveryExecutor(
                recognizer=recognizer,
                cost_model=self.cost,
                page_cache=self.page_cache,
                formula_timeout_seconds=float(
                    getattr(sched_cfg, "formula_timeout_seconds", 30.0) or 30.0
                ),
            )
        self.recognizer = recognizer
        self.breaker = CircuitBreaker()

    def run(
        self,
        candidates: list[FormulaCandidate],
        *,
        session: FormulaRecoverySession,
        pdf_path: str | Path | None = None,
    ) -> ShadowDocumentResult:
        if not self.config.deepseek_shadow_enabled:
            return ShadowDocumentResult(enabled=False, summary={"reason": "shadow_disabled"})

        health = deepseek_health_check()
        if not health.ok:
            self.breaker.trip(OcrFailureClass.BACKEND_UNAVAILABLE, health.reason)
            return ShadowDocumentResult(
                enabled=True,
                summary={
                    "reason": "healthcheck_failed",
                    "health": health.to_dict(),
                    "circuit_breaker": self.breaker.to_dict(),
                    "corrupted_formula_count": len(candidates),
                    "attempted_at_least_once": 0,
                    "zero_attempt_count": len(candidates),
                    "coverage_rate": 0.0,
                    "ocr_calls": 0,
                    "accepted": 0,
                    "rejected": 0,
                    "would_replace": [],
                    "would_replace_count": 0,
                },
            )

        cfg = self.scheduler.config
        if cfg.coverage_first and cfg.guarantee_one_attempt:
            return self._run_coverage_first(candidates, session=session, pdf_path=pdf_path)
        return self._run_page_grouped(candidates, session=session, pdf_path=pdf_path)

    def _run_coverage_first(
        self,
        candidates: list[FormulaCandidate],
        *,
        session: FormulaRecoverySession,
        pdf_path: str | Path | None,
    ) -> ShadowDocumentResult:
        """Round-1 mandatory：每式 FORMULA×1；soft 不阻断；hard/breaker 可中止。"""
        pdf = Path(pdf_path or session.pdf_path or "")
        pdf_hash = file_sha1(pdf) if pdf.exists() else "nopdf"
        ctx_base = ExecutorContext(
            session=session,
            pdf_hash=pdf_hash,
            formula_render_scale=float(
                getattr(self.config, "crop_render_scale", 2.0) or 2.0
            ),
            page_render_scale=1.35,
            formula_config=self.config,
        )
        cfg = self.scheduler.config
        pages_out: list[ShadowPageRecord] = []
        would_replace_rows: list[dict[str, Any]] = []
        total_ocr = 0
        total_acc = 0
        total_rej = 0
        act_sum = 0.0
        infer_sum = 0.0
        load_sum = 0.0
        mode_counts: dict[str, int] = {"formula": 0, "skip": 0}
        attempted_ids: set[int] = set()
        zero_attempt = 0
        by_page_exec: dict[int, list[CandidateExecutionResult]] = defaultdict(list)
        by_page_sched: dict[int, dict[str, Any]] = {}

        # Round 1 — mandatory coverage：静态优先序 + 7.2D 周期性动态重排
        # 禁止用本篇最终 profile；禁止 early-stop；跑满全部 candidate
        from app.ocr.prioritization import (
            NUM_NON_EQ,
            classify_equation_number_plausibility,
            prioritize_candidates,
        )
        from app.ocr.sequential_ranking import (
            TrajectoryState,
            build_static_score_map,
            reorder_remaining,
        )

        prio_on = bool(
            getattr(self.config, "deepseek_candidate_prioritization", True)
        )
        seq_on = bool(getattr(self.config, "deepseek_sequential_ranking", True))
        reorder_every = max(
            1, int(getattr(self.config, "deepseek_sequential_reorder_every", 3) or 3)
        )
        ordered, order_meta = prioritize_candidates(candidates, enabled=prio_on)
        static_scores = build_static_score_map(ordered, order_meta)
        remaining: list[FormulaCandidate] = list(ordered)
        traj = TrajectoryState()
        reorder_log: list[dict[str, Any]] = []
        attempt_i = 0

        while remaining:
            cand = remaining.pop(0)
            page = int(cand.page) if cand.page is not None else -1
            if self.breaker.tripped:
                row = CandidateExecutionResult(
                    page=cand.page,
                    eq_number=eq_number_from_candidate(cand),
                    error=f"backend_unhealthy:{self.breaker.reason}",
                    scheduler_mode="skip",
                    original=(cand.raw_text or cand.text or "")[:500],
                )
                by_page_exec[page].append(row)
                zero_attempt += 1
                mode_counts["skip"] = mode_counts.get("skip", 0) + 1
                continue

            if self.budget.hard_exceeded(cfg):
                row = CandidateExecutionResult(
                    page=cand.page,
                    eq_number=eq_number_from_candidate(cand),
                    error="hard_limit_exceeded",
                    scheduler_mode="skip",
                    original=(cand.raw_text or cand.text or "")[:500],
                )
                by_page_exec[page].append(row)
                zero_attempt += 1
                mode_counts["skip"] = mode_counts.get("skip", 0) + 1
                continue

            plaus = classify_equation_number_plausibility(cand)
            if plaus["class"] == NUM_NON_EQ:
                row = CandidateExecutionResult(
                    page=cand.page,
                    eq_number=eq_number_from_candidate(cand),
                    error="skip_non_equation_number",
                    gate_reason="skip_non_equation_number",
                    scheduler_mode="skip",
                    original=(cand.raw_text or cand.text or "")[:500],
                )
                by_page_exec[page].append(row)
                zero_attempt += 1
                mode_counts["skip"] = mode_counts.get("skip", 0) + 1
                continue

            unit = self.cost.estimate_formula_unit()
            load_est = 0.0 if self.cost.runtime.model_loaded else self.cost.estimate_model_load()
            decision = RecoveryCostEstimate(
                formula_count=1,
                estimated_formula_seconds=round(load_est + unit, 3),
                estimated_page_seconds=0.0,
                safety_factor=float(cfg.page_safety_factor),
                chosen_mode=RecoveryMode.FORMULA,
                reason="mandatory_coverage_round1",
                page=cand.page,
                estimated_model_load_seconds=round(load_est, 3),
                budget_remaining_seconds=max(
                    0.0, float(cfg.hard_limit_seconds) - self.budget.seconds_used
                ),
                trace={
                    "stage": "mandatory",
                    "coverage_first": True,
                    "soft_budget": cfg.max_total_recovery_seconds,
                    "hard_limit": cfg.hard_limit_seconds,
                    "sequential_ranking": seq_on,
                },
            )
            by_page_sched[page] = {
                "decision": decision.chosen_mode.value,
                "decision_reason": decision.reason,
                "estimated_formula_seconds": decision.estimated_formula_seconds,
                "trace": decision.trace,
            }
            exec_res = self.executor.execute_page([cand], decision, ctx_base)
            self.scheduler.commit_decision(decision, actual_seconds=exec_res.actual_seconds)
            self.budget.mandatory_attempts += 1
            total_ocr += exec_res.ocr_calls
            total_acc += exec_res.accepted
            total_rej += exec_res.rejected
            act_sum += float(exec_res.actual_seconds)
            infer_sum += float(exec_res.inference_seconds)
            load_sum += float(exec_res.model_load_seconds)
            mode_counts["formula"] = mode_counts.get("formula", 0) + 1
            attempted_ids.add(id(cand))

            row_dicts: list[dict[str, Any]] = []
            for c in exec_res.candidates:
                if c.error:
                    cls = self.breaker.observe_error(c.error, success=False)
                    c.error = f"{cls.value}:{c.error}" if cls.value not in (c.error or "") else c.error
                by_page_exec[page].append(c)
                rd = _cand_row(c, stage="mandatory")
                would_replace_rows.append(rd)
                row_dicts.append(rd)

            if exec_res.error:
                self.breaker.observe_error(exec_res.error, success=False)

            # trajectory：用本 attempt 的结果更新（无未来）
            if row_dicts:
                traj.observe(row_dicts[0], cand)
            attempt_i += 1

            # 每 N 次对剩余重排（不 stop）
            if (
                seq_on
                and remaining
                and attempt_i % reorder_every == 0
                and not self.breaker.tripped
            ):
                remaining, expl = reorder_remaining(
                    remaining,
                    static_scores=static_scores,
                    traj=traj,
                    after_attempt=attempt_i,
                )
                reorder_log.append(expl)

        # 供 summary / 超时重试使用的最终执行序（已执行 + 未执行剩余为空）
        ordered = list(ordered)  # 初始序保留在 order_meta；实际序见 would_replace
        order_meta = dict(order_meta or {})
        order_meta["sequential_ranking"] = {
            "enabled": seq_on,
            "reorder_every": reorder_every,
            "reorder_events": len(reorder_log),
            "reorders": reorder_log,
            "final_trajectory": traj.to_dict(),
        }

        # Phase 5G：整轮结束后对 timeout 公式 deferred retry ×1（coverage-first 不丢）
        defer_on = bool(getattr(self.config, "deepseek_timeout_deferred_retry", True))
        timed_out_cands: list[FormulaCandidate] = []
        if defer_on and not self.breaker.tripped:
            seen_to: set[int] = set()
            for page, rows in by_page_exec.items():
                for row in rows:
                    err = (row.error or "").lower()
                    if "timeout" not in err:
                        continue
                    # 找回原 candidate
                    for cand in ordered:
                        if id(cand) in seen_to:
                            continue
                        if cand.page == row.page and eq_number_from_candidate(cand) == row.eq_number:
                            timed_out_cands.append(cand)
                            seen_to.add(id(cand))
                            break

        for cand in timed_out_cands:
            if self.breaker.tripped or self.budget.hard_exceeded(cfg):
                break
            client = getattr(self.recognizer, "client", None)
            if client is not None and getattr(client, "disabled", False):
                break

            page = int(cand.page) if cand.page is not None else -1
            unit = self.cost.estimate_formula_unit()
            decision = RecoveryCostEstimate(
                formula_count=1,
                estimated_formula_seconds=round(unit, 3),
                estimated_page_seconds=0.0,
                safety_factor=float(cfg.page_safety_factor),
                chosen_mode=RecoveryMode.FORMULA,
                reason="deferred_retry_after_timeout",
                page=cand.page,
                estimated_model_load_seconds=0.0,
                budget_remaining_seconds=max(
                    0.0, float(cfg.hard_limit_seconds) - self.budget.seconds_used
                ),
                trace={
                    "stage": "deferred_retry",
                    "coverage_first": True,
                    "timeout_deferred_retry": True,
                },
            )
            exec_res = self.executor.execute_page([cand], decision, ctx_base)
            self.scheduler.commit_decision(decision, actual_seconds=exec_res.actual_seconds)
            total_ocr += exec_res.ocr_calls
            total_acc += exec_res.accepted
            total_rej += exec_res.rejected
            act_sum += float(exec_res.actual_seconds)
            infer_sum += float(exec_res.inference_seconds)
            load_sum += float(exec_res.model_load_seconds)
            if client is not None and hasattr(client, "session_stats"):
                client.session_stats.deferred_retry_count += 1

            # 用 deferred 结果替换同式 timeout 行
            for c in exec_res.candidates:
                if c.error:
                    cls = self.breaker.observe_error(c.error, success=False)
                    c.error = f"{cls.value}:{c.error}" if cls.value not in (c.error or "") else c.error
                old_rows = by_page_exec.get(page) or []
                replaced = False
                for i, old in enumerate(old_rows):
                    if old.eq_number == c.eq_number and "timeout" in (old.error or "").lower():
                        old_rows[i] = c
                        replaced = True
                        break
                if not replaced:
                    old_rows.append(c)
                by_page_exec[page] = old_rows
                would_replace_rows.append(_cand_row(c, stage="deferred_retry"))
            if exec_res.error:
                self.breaker.observe_error(exec_res.error, success=False)

        for page in sorted(by_page_exec.keys()):
            rows = by_page_exec[page]
            acc = sum(1 for r in rows if r.gate_accepted)
            pages_out.append(
                ShadowPageRecord(
                    page=page,
                    corrupted_count=len(rows),
                    scheduler=by_page_sched.get(
                        page,
                        {"decision": "formula", "decision_reason": "mandatory_coverage_round1"},
                    ),
                    execution={
                        "mode": "formula",
                        "decision_reason": "mandatory_coverage_round1",
                        "ocr_calls": sum(1 for r in rows if not (r.error or "").startswith("backend") and not (r.error or "").startswith("hard_")),
                        "accepted": acc,
                        "rejected": len(rows) - acc,
                        "candidates": [r.to_dict() for r in rows],
                    },
                )
            )

        load_count = 0
        if self.recognizer is not None:
            mlc = getattr(self.recognizer, "model_load_count", None)
            load_count = int(mlc() if callable(mlc) else (mlc or 0))

        corrupted_n = len(candidates)
        attempted = len(attempted_ids)
        # zero_attempt：从未进入 OCR 的（熔断/硬限）
        zero_attempt = max(zero_attempt, corrupted_n - attempted)
        coverage = (attempted / corrupted_n) if corrupted_n else 1.0

        worker_session: dict[str, Any] | None = None
        tail_protected = bool(getattr(cfg, "formula_timeout_seconds", 0) or 0) > 0
        client = getattr(self.recognizer, "client", None)
        if client is not None and hasattr(client, "session_stats"):
            worker_session = client.session_stats.to_dict()
            tail_protected = bool(client.session_stats.tail_latency_protected)

        summary = {
            "pages": len(pages_out),
            "corrupted_formula_count": corrupted_n,
            "ocr_calls": total_ocr,
            "attempted": total_ocr,
            "accepted": total_acc,
            "rejected": total_rej,
            "accept_rate": round(total_acc / total_ocr, 4) if total_ocr else None,
            "would_replace_count": sum(1 for r in would_replace_rows if r.get("would_replace")),
            "mode_counts": mode_counts,
            "model_load_count": load_count,
            "model_load_seconds": round(load_sum, 3),
            "ocr_inference_seconds": round(infer_sum, 3),
            "estimated_seconds": None,
            "actual_seconds": round(act_sum, 3),
            "recovery_yield": (
                round(total_acc / total_ocr, 4) if total_ocr else None
            ),
            "seconds_per_accept": (
                round(infer_sum / total_acc, 3) if total_acc else None
            ),
            "cost_per_recovered_formula": (
                round(act_sum / total_acc, 3) if total_acc else None
            ),
            "ocr_calls_per_accept": (
                round(total_ocr / total_acc, 3) if total_acc else None
            ),
            "salvage_used_count": sum(
                1 for r in would_replace_rows if r.get("salvage_used")
            ),
            "failure_class_counts": {
                k: sum(1 for r in would_replace_rows if r.get("failure_class") == k)
                for k in sorted(
                    {
                        str(r.get("failure_class") or "")
                        for r in would_replace_rows
                        if r.get("failure_class")
                    }
                )
            },
            "budget": {
                "formulas_used": self.budget.formulas_used,
                "pages_used": self.budget.pages_used,
                "seconds_used": round(self.budget.seconds_used, 3),
                "mandatory_attempts": self.budget.mandatory_attempts,
                "optional_attempts": self.budget.optional_attempts,
                "soft_budget_seconds": cfg.max_total_recovery_seconds,
                "hard_limit_seconds": cfg.hard_limit_seconds,
                "soft_exceeded": self.budget.soft_exceeded(cfg),
            },
            "coverage": {
                "attempted_at_least_once": attempted,
                "zero_attempt_count": zero_attempt,
                "coverage_rate": round(coverage, 4),
                "policy": "coverage_first_mandatory_round1",
                "deferred_timeout_retries": len(timed_out_cands) if defer_on else 0,
            },
            "prioritization": order_meta,
            "sequential_ranking": (order_meta or {}).get("sequential_ranking"),
            "attempted_at_least_once": attempted,
            "zero_attempt_count": zero_attempt,
            "coverage_rate": round(coverage, 4),
            "circuit_breaker": self.breaker.to_dict(),
            "health": health.to_dict() if (health := deepseek_health_check()) else None,
            "would_replace": would_replace_rows,
            "worker_session": worker_session,
            "tail_latency_protected": tail_protected,
            "acceptance": {
                "model_load_count_le_1": load_count <= 1,
                "write_markdown": False,
                "coverage_rate_is_one": coverage >= 1.0 - 1e-9
                or self.breaker.tripped
                or self.budget.hard_exceeded(cfg),
                "tail_latency_protected": tail_protected,
            },
        }
        # Phase 7.1：成本分账 + 文档 profile（只观察）
        cold_from_rows = sum(
            float(r.get("cold_start_seconds") or 0.0) for r in would_replace_rows
        )
        wait_from_rows = sum(
            float((r.get("timing") or {}).get("worker_ready_wait_seconds") or 0.0)
            for r in would_replace_rows
        )
        extract_from_rows = sum(
            float((r.get("timing") or {}).get("extraction_cpu_seconds") or 0.0)
            for r in would_replace_rows
        )
        cold_s = max(float(load_sum or 0.0), cold_from_rows)
        summary["cost_breakdown"] = {
            "model_cold_start": round(cold_s, 3),
            "worker_ready_wait": round(wait_from_rows, 3),
            "ocr_inference": round(infer_sum, 3),
            "extraction_cpu": round(extract_from_rows, 3),
            "actual_wall": round(act_sum, 3),
            "steady_state": round(max(0.0, act_sum - cold_s), 3),
        }
        summary["cold_start_seconds"] = round(cold_s, 3)
        summary["cold_start_affected"] = cold_s >= 30.0
        try:
            from app.diagnostics.document_profile import build_document_recovery_profile
            from app.diagnostics.failure_memory import record_shadow_failures

            doc_id = Path(str(pdf_path or session.pdf_path or "")).stem
            profile = build_document_recovery_profile(
                would_replace_rows,
                document_id=doc_id,
                ocr_calls=total_ocr,
                accepted=total_acc,
                rejected=total_rej,
                ocr_inference_seconds=infer_sum,
                model_load_seconds=load_sum,
                cold_start_seconds=cold_s,
                actual_seconds=act_sum,
            )
            summary["document_recovery_profile"] = profile
            # 决策实验：顶层也挂 accept curve，免挖 profile
            summary["first_accept_attempt"] = profile.get("first_accept_attempt")
            summary["last_accept_attempt"] = profile.get("last_accept_attempt")
            summary["accept_positions"] = profile.get("accept_positions")
            summary["cumulative_accept_curve"] = profile.get("cumulative_accept_curve")
            summary["accept_curve_auc"] = profile.get("accept_curve_auc")
            summary["counterfactual_budget"] = profile.get("counterfactual_budget")
            summary["recall_at_k"] = (
                (profile.get("counterfactual_budget") or {}).get("recall_at_k") or {}
            )
            try:
                from app.ocr.prioritization import build_ranking_error_analysis

                summary["ranking_error_analysis"] = build_ranking_error_analysis(
                    summary.get("prioritization") or {},
                    would_replace_rows,
                )
            except Exception as e:
                summary["ranking_error_analysis"] = {"error": str(e)}
            fm = record_shadow_failures(
                would_replace_rows,
                run_id=str(getattr(session, "run_id", "") or ""),
                document_id=doc_id,
                pdf_path=pdf_path or session.pdf_path,
                source="shadow_coverage_first",
                document_profile=profile,
            )
            summary["failure_memory"] = fm
        except Exception as e:
            summary["failure_memory"] = {"error": str(e)}
        return ShadowDocumentResult(
            enabled=True, write_markdown=False, pages=pages_out, summary=summary
        )

    def _run_page_grouped(
        self,
        candidates: list[FormulaCandidate],
        *,
        session: FormulaRecoverySession,
        pdf_path: str | Path | None,
    ) -> ShadowDocumentResult:
        """旧路径：按页 decide（可选阶段 / 兼容测试）。"""
        pdf = Path(pdf_path or session.pdf_path or "")
        pdf_hash = file_sha1(pdf) if pdf.exists() else "nopdf"
        groups = group_candidates_by_page(candidates)
        pages_out: list[ShadowPageRecord] = []
        total_ocr = 0
        total_acc = 0
        total_rej = 0
        est_sum = 0.0
        act_sum = 0.0
        infer_sum = 0.0
        load_sum = 0.0
        mode_counts: dict[str, int] = {}
        would_replace_rows: list[dict[str, Any]] = []

        ctx_base = ExecutorContext(
            session=session,
            pdf_hash=pdf_hash,
            formula_render_scale=float(
                getattr(self.config, "crop_render_scale", 2.0) or 2.0
            ),
            page_render_scale=1.35,
            formula_config=self.config,
        )

        for page, cands in groups.items():
            if self.breaker.tripped:
                decision = RecoveryCostEstimate(
                    formula_count=len(cands),
                    estimated_formula_seconds=0.0,
                    estimated_page_seconds=0.0,
                    safety_factor=1.0,
                    chosen_mode=RecoveryMode.SKIP,
                    reason="backend_unhealthy",
                    page=page,
                )
            else:
                cached = self._page_is_cached(page, pdf_hash)
                decision = self.scheduler.decide_page(
                    page=page,
                    corrupted_formula_count=len(cands),
                    page_cached=cached,
                )
            exec_res = self.executor.execute_page(cands, decision, ctx_base)
            if decision.chosen_mode == RecoveryMode.SKIP:
                assert exec_res.ocr_calls == 0
            if decision.chosen_mode == RecoveryMode.PAGE_REUSE:
                assert exec_res.ocr_calls == 0

            self.scheduler.commit_decision(
                decision, actual_seconds=exec_res.actual_seconds
            )
            total_ocr += exec_res.ocr_calls
            total_acc += exec_res.accepted
            total_rej += exec_res.rejected
            est_sum += float(exec_res.estimated_seconds)
            act_sum += float(exec_res.actual_seconds)
            infer_sum += float(exec_res.inference_seconds)
            load_sum += float(exec_res.model_load_seconds)
            mode_counts[decision.chosen_mode.value] = (
                mode_counts.get(decision.chosen_mode.value, 0) + 1
            )
            for c in exec_res.candidates:
                if c.error:
                    self.breaker.observe_error(c.error, success=bool(c.would_replace))
                row = _cand_row(c, stage="legacy")
                row["scheduler_mode"] = c.scheduler_mode or decision.chosen_mode.value
                would_replace_rows.append(row)

            pages_out.append(
                ShadowPageRecord(
                    page=page,
                    corrupted_count=len(cands),
                    scheduler={
                        "decision": decision.chosen_mode.value,
                        "decision_reason": decision.reason,
                        "estimated_formula_seconds": decision.estimated_formula_seconds,
                        "estimated_page_seconds": decision.estimated_page_seconds,
                        "page_cost_with_safety": decision.page_cost_with_safety,
                        "trace": decision.trace,
                    },
                    execution=exec_res.to_dict(),
                )
            )

        load_count = 0
        if self.recognizer is not None:
            mlc = getattr(self.recognizer, "model_load_count", None)
            load_count = int(mlc() if callable(mlc) else (mlc or 0))

        summary = {
            "pages": len(pages_out),
            "corrupted_formula_count": len(candidates),
            "ocr_calls": total_ocr,
            "attempted": total_ocr,
            "accepted": total_acc,
            "rejected": total_rej,
            "accept_rate": round(total_acc / total_ocr, 4) if total_ocr else None,
            "would_replace_count": sum(1 for r in would_replace_rows if r.get("would_replace")),
            "mode_counts": mode_counts,
            "model_load_count": load_count,
            "model_load_seconds": round(load_sum, 3),
            "ocr_inference_seconds": round(infer_sum, 3),
            "estimated_seconds": round(est_sum, 3),
            "actual_seconds": round(act_sum, 3),
            "cost_error_ratio": round(act_sum / est_sum, 3) if est_sum > 1e-6 else None,
            "recovery_yield": (
                round(total_acc / total_ocr, 4) if total_ocr else None
            ),
            "seconds_per_accept": (
                round(infer_sum / total_acc, 3) if total_acc else None
            ),
            "cost_per_recovered_formula": (
                round(act_sum / total_acc, 3) if total_acc else None
            ),
            "salvage_used_count": sum(
                1 for r in would_replace_rows if r.get("salvage_used")
            ),
            "budget": {
                "formulas_used": self.budget.formulas_used,
                "pages_used": self.budget.pages_used,
                "seconds_used": round(self.budget.seconds_used, 3),
            },
            "circuit_breaker": self.breaker.to_dict(),
            "would_replace": would_replace_rows,
            "acceptance": {
                "model_load_count_le_1": load_count <= 1,
                "write_markdown": False,
            },
        }
        cold_s = float(load_sum or 0.0)
        summary["cost_breakdown"] = {
            "model_cold_start": round(cold_s, 3),
            "ocr_inference": round(infer_sum, 3),
            "actual_wall": round(act_sum, 3),
            "steady_state": round(max(0.0, act_sum - cold_s), 3),
        }
        summary["cold_start_seconds"] = round(cold_s, 3)
        summary["cold_start_affected"] = cold_s >= 30.0
        try:
            from app.diagnostics.document_profile import build_document_recovery_profile
            from app.diagnostics.failure_memory import record_shadow_failures

            doc_id = Path(str(pdf_path or session.pdf_path or "")).stem
            profile = build_document_recovery_profile(
                would_replace_rows,
                document_id=doc_id,
                ocr_calls=total_ocr,
                accepted=total_acc,
                rejected=total_rej,
                ocr_inference_seconds=infer_sum,
                model_load_seconds=load_sum,
                cold_start_seconds=cold_s,
                actual_seconds=act_sum,
            )
            summary["document_recovery_profile"] = profile
            summary["first_accept_attempt"] = profile.get("first_accept_attempt")
            summary["last_accept_attempt"] = profile.get("last_accept_attempt")
            summary["accept_positions"] = profile.get("accept_positions")
            summary["cumulative_accept_curve"] = profile.get("cumulative_accept_curve")
            summary["accept_curve_auc"] = profile.get("accept_curve_auc")
            summary["counterfactual_budget"] = profile.get("counterfactual_budget")
            summary["recall_at_k"] = (
                (profile.get("counterfactual_budget") or {}).get("recall_at_k") or {}
            )
            try:
                from app.ocr.prioritization import build_ranking_error_analysis

                summary["ranking_error_analysis"] = build_ranking_error_analysis(
                    summary.get("prioritization") or {},
                    would_replace_rows,
                )
            except Exception as e:
                summary["ranking_error_analysis"] = {"error": str(e)}
            fm = record_shadow_failures(
                would_replace_rows,
                document_id=doc_id,
                pdf_path=pdf_path or session.pdf_path,
                source="shadow_page_grouped",
                document_profile=profile,
            )
            summary["failure_memory"] = fm
        except Exception as e:
            summary["failure_memory"] = {"error": str(e)}
        return ShadowDocumentResult(
            enabled=True,
            write_markdown=False,
            pages=pages_out,
            summary=summary,
        )

    def _page_is_cached(self, page: int, pdf_hash: str) -> bool:
        conf = {
            "page_render_scale": 1.35,
            "prompt": "",
            "recognizer": getattr(self.recognizer, "name", "deepseek-ocr-2")
            if self.recognizer
            else "deepseek-ocr-2",
        }
        key = self.page_cache.make_key(
            pdf_hash=pdf_hash,
            page=page,
            recognizer=getattr(self.recognizer, "name", "deepseek-ocr-2")
            if self.recognizer
            else "deepseek-ocr-2",
            config=conf,
        )
        return key in getattr(self.page_cache, "_store", {})
