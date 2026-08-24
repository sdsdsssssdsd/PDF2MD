"""RecoveryExecutor — 严格执行 Scheduler 决策（Phase 4B Shadow）。

禁止：自行改 mode、region、retry、SKIP→formula fallback、写 production Markdown。
"""
from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from app.formula.config import FormulaConfig
from app.formula.gain import evaluate_recovery_gain
from app.formula.session import FormulaRecoverySession
from app.formula.types import FormulaCandidate, FormulaQuality
from app.formula.validator import validate_latex
from app.ocr import OCRMode
from app.ocr.cache import PageOCRCache, file_sha1
from app.ocr.cost_model import RecoveryCostModel
from app.ocr.crops import page_bbox, render_clip
from app.ocr.extractor import EquationExtractor
from app.ocr.scheduler import RecoveryCostEstimate, RecoveryMode

_EQ_NUM = re.compile(r"(?:Eq\.?|Equation)\s*\((\d+)\)", re.I)
_EQ_NUM_BARE = re.compile(r"\((\d+)\)\s*$")


def _abort_reason_from_ocr(error: str | None, *, success: bool) -> str:
    if success and not error:
        return ""
    err = (error or "").lower()
    if "oom" in err or "out of memory" in err:
        return "oom"
    if "timeout" in err or "timed out" in err:
        return "timeout"
    if "abort" in err:
        return "aborted"
    if not success or error:
        return "ocr_failed"
    return ""


def _gpu_snapshot() -> dict[str, Any]:
    """主进程侧 GPU 快照（Worker 显存另计；用于看 Docling 残留压力）。"""
    try:
        import torch

        if not torch.cuda.is_available():
            return {"cuda": False}
        free_b, total_b = torch.cuda.mem_get_info(0)
        return {
            "cuda": True,
            "allocated_mb": round(torch.cuda.memory_allocated(0) / (1024**2), 1),
            "reserved_mb": round(torch.cuda.memory_reserved(0) / (1024**2), 1),
            "free_mb": round(free_b / (1024**2), 1),
            "total_mb": round(total_b / (1024**2), 1),
        }
    except Exception:
        return {"cuda": False, "error": "snapshot_failed"}


def eq_number_from_candidate(cand: FormulaCandidate) -> str:
    # 结构阶段已绑定的编号优先（EquationIdentity）
    bound = (getattr(cand, "equation_number", None) or "").strip()
    if bound:
        return bound
    # 前文最后一次 Eq.(n) 优先，避免同段 Eq.(6)/(7) 误取第一个
    before = cand.context_before or ""
    before_hits = list(_EQ_NUM.finditer(before))
    if before_hits:
        return before_hits[-1].group(1)
    for src in (cand.context_after, cand.text or "", cand.raw_text or ""):
        m = _EQ_NUM.search(src or "")
        if m:
            return m.group(1)
    m = _EQ_NUM_BARE.search((cand.text or "").strip())
    if m:
        return m.group(1)
    return ""


@dataclass
class CandidateExecutionResult:
    page: int | None
    eq_number: str
    candidate_id: str = ""
    selected_latex: str = ""
    gate_accepted: bool = False
    gate_reason: str = ""
    extractor_method: str = ""
    error: str = ""
    scheduler_mode: str = ""
    original: str = ""
    recovered: str = ""
    would_replace: bool = False
    # Phase 5E：每式细粒度 timing
    timing: dict[str, Any] = field(default_factory=dict)
    # Phase 6：归因 / salvage
    raw_output: str = ""
    failure_class: str = ""
    salvage_used: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RecoveryExecutionResult:
    mode: RecoveryMode
    decision_reason: str
    ocr_calls: int = 0
    actual_seconds: float = 0.0
    estimated_seconds: float = 0.0
    cost_error_ratio: float | None = None
    accepted: int = 0
    rejected: int = 0
    cache_hit: bool = False
    marginal_ocr_seconds: float = 0.0
    model_load_seconds: float = 0.0
    inference_seconds: float = 0.0
    extract_gate_seconds: float = 0.0
    render_seconds: float = 0.0
    candidates: list[CandidateExecutionResult] = field(default_factory=list)
    decision: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value if isinstance(self.mode, RecoveryMode) else str(self.mode),
            "decision_reason": self.decision_reason,
            "ocr_calls": self.ocr_calls,
            "actual_seconds": round(self.actual_seconds, 3),
            "estimated_seconds": round(self.estimated_seconds, 3),
            "cost_error_ratio": (
                round(self.cost_error_ratio, 3) if self.cost_error_ratio is not None else None
            ),
            "accepted": self.accepted,
            "rejected": self.rejected,
            "cache_hit": self.cache_hit,
            "marginal_ocr_seconds": round(self.marginal_ocr_seconds, 3),
            "model_load_seconds": round(self.model_load_seconds, 3),
            "inference_seconds": round(self.inference_seconds, 3),
            "extract_gate_seconds": round(self.extract_gate_seconds, 3),
            "render_seconds": round(self.render_seconds, 3),
            "candidates": [c.to_dict() for c in self.candidates],
            "decision": self.decision,
            "error": self.error,
        }


@dataclass
class ExecutorContext:
    session: FormulaRecoverySession
    pdf_hash: str = ""
    formula_render_scale: float = 2.0
    page_render_scale: float = 1.35
    formula_config: FormulaConfig | None = None


class RecoveryExecutor:
    """只执行 decision.chosen_mode，不得改写。"""

    def __init__(
        self,
        *,
        recognizer: Any,
        cost_model: RecoveryCostModel,
        page_cache: PageOCRCache | None = None,
        extractor: EquationExtractor | None = None,
        prompt: str | None = None,
        formula_timeout_seconds: float = 30.0,
    ) -> None:
        self.recognizer = recognizer
        self.cost = cost_model
        self.page_cache = page_cache or PageOCRCache()
        self.extractor = extractor or EquationExtractor()
        self.prompt = prompt
        self.formula_timeout_seconds = float(formula_timeout_seconds or 0.0)

    def _recognize_with_timeout(self, image: Any, *, mode: Any) -> Any:
        """单次 OCR hard timeout（Phase 5G）。

        冷启动（模型未加载）不做线程超时：4060 上 DeepSeek 首次加载常 60~180s，
        30s 硬杀会误报 timeout 并空烧后续公式。
        热路径：ThreadPool 兜底；超时必须回调 recognizer.on_inference_timeout
        （Worker 路径会 kill + restart，禁止继续复用卡死进程）。
        Worker 客户端自身还有 socket-level hard timeout。
        """
        from app.ocr import DocumentOCRResult

        model_loaded = bool(getattr(self.cost.runtime, "model_loaded", False))
        # 冷启动：必须等加载完成，禁止 ThreadPool 超时截断
        if not model_loaded or self.formula_timeout_seconds <= 0:
            return self.recognizer.recognize(image, mode=mode, prompt=self.prompt)

        import concurrent.futures

        # 略宽于 client socket timeout，优先让 client 自己 kill；此处为兜底
        pool_timeout = float(self.formula_timeout_seconds) + 2.0
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(
                self.recognizer.recognize, image, mode=mode, prompt=self.prompt
            )
            try:
                return fut.result(timeout=pool_timeout)
            except concurrent.futures.TimeoutError:
                on_to = getattr(self.recognizer, "on_inference_timeout", None)
                if callable(on_to):
                    try:
                        on_to()
                    except Exception:
                        pass
                return DocumentOCRResult(
                    raw_output="",
                    markdown=None,
                    recognizer=getattr(self.recognizer, "name", "deepseek-ocr-2"),
                    mode=str(getattr(mode, "value", mode)),
                    elapsed_seconds=self.formula_timeout_seconds,
                    success=False,
                    error=f"timeout:{self.formula_timeout_seconds}s",
                    metadata={
                        "ocr_inference_seconds": self.formula_timeout_seconds,
                        "watchdog": "executor_thread_timeout",
                    },
                )

    def execute_page(
        self,
        page_candidates: list[FormulaCandidate],
        decision: RecoveryCostEstimate,
        context: ExecutorContext,
    ) -> RecoveryExecutionResult:
        mode = decision.chosen_mode
        # 硬规则：不得自行改 mode
        if mode != decision.chosen_mode:
            raise RuntimeError("executor_must_not_change_mode")

        estimated = self._estimated_for_mode(decision, mode)
        t0 = time.perf_counter()

        if mode == RecoveryMode.SKIP:
            res = self._exec_skip(decision)
        elif mode == RecoveryMode.PAGE_REUSE:
            res = self._exec_page_reuse(page_candidates, decision, context)
        elif mode == RecoveryMode.PAGE:
            res = self._exec_page(page_candidates, decision, context)
        elif mode in (RecoveryMode.FORMULA, RecoveryMode.FORMULA_BATCH):
            res = self._exec_formula_batch(page_candidates, decision, context)
        else:
            res = RecoveryExecutionResult(
                mode=mode,
                decision_reason=decision.reason,
                error=f"unsupported_mode:{mode}",
                decision=decision.to_dict(),
            )

        res.actual_seconds = time.perf_counter() - t0
        res.estimated_seconds = estimated
        if estimated > 1e-6:
            res.cost_error_ratio = res.actual_seconds / estimated
        elif res.actual_seconds <= 1e-6:
            res.cost_error_ratio = 1.0
        else:
            res.cost_error_ratio = None
        res.decision = decision.to_dict()
        res.decision_reason = decision.reason
        return res

    @staticmethod
    def _estimated_for_mode(decision: RecoveryCostEstimate, mode: RecoveryMode) -> float:
        if mode in (RecoveryMode.SKIP, RecoveryMode.PAGE_REUSE):
            return 0.0
        if mode == RecoveryMode.PAGE:
            return float(decision.estimated_page_seconds)
        return float(decision.estimated_formula_seconds)

    def _exec_skip(self, decision: RecoveryCostEstimate) -> RecoveryExecutionResult:
        return RecoveryExecutionResult(
            mode=RecoveryMode.SKIP,
            decision_reason=decision.reason,
            ocr_calls=0,
            marginal_ocr_seconds=0.0,
            cache_hit=False,
        )

    def _gate(self, latex: str, cand: FormulaCandidate, fcfg: FormulaConfig) -> tuple[bool, str]:
        before_q = FormulaQuality(
            syntax_score=0.05,
            corruption_score=0.95,
            semantic_score=0.1,
            valid=False,
            recoverable=True,
            reasons=["shadow_corrupted"],
        )
        vr = validate_latex(
            latex,
            fcfg,
            context_before=cand.context_before,
            context_after=cand.context_after,
        )
        gain = evaluate_recovery_gain(
            before_quality=before_q,
            after_quality=vr.quality,
            before_latex=cand.text or r"\quad garbage",
            after_latex=latex,
            context_before=cand.context_before,
            context_after=cand.context_after,
            after_valid=bool(latex) and vr.valid,
        )
        return bool(gain.accept), ",".join(gain.reasons) if gain.reasons else ""

    def _try_spaced_letter_salvage_result(
        self,
        cand: FormulaCandidate,
        fcfg: FormulaConfig,
        *,
        scheduler_mode: str = "",
        error: str = "",
    ) -> CandidateExecutionResult | None:
        from app.formula.spaced_letter_salvage import salvage_spaced_letter_latex
        from app.ocr.failure_class import classify_recovery_failure

        orig_full = cand.raw_text or cand.text or ""
        salv = salvage_spaced_letter_latex(orig_full, cfg=fcfg)
        if not salv:
            return None
        ok, reason = self._gate(salv, cand, fcfg)
        if not ok:
            return None
        n = eq_number_from_candidate(cand)
        cid = (getattr(cand, "candidate_id", "") or "").strip()
        if not cid:
            cid = f"p{cand.page}_eq{n or 'x'}_{id(cand) % 100000}"
        fail_cls = classify_recovery_failure(
            gate_accepted=ok,
            gate_reason=reason,
            error="",
            extractor_method="spaced_letter_original_salvage",
            raw_output="",
            selected_latex=salv,
        )
        return CandidateExecutionResult(
            page=cand.page,
            eq_number=n,
            candidate_id=str(cid),
            selected_latex=salv,
            gate_accepted=ok,
            gate_reason=reason,
            extractor_method="spaced_letter_original_salvage",
            error=error,
            scheduler_mode=scheduler_mode,
            original=orig_full[:500],
            recovered=salv[:500],
            would_replace=True,
            raw_output="",
            failure_class=fail_cls.value,
            salvage_used=True,
        )

    def _try_classification_metrics_salvage_result(
        self,
        cand: FormulaCandidate,
        fcfg: FormulaConfig,
        *,
        scheduler_mode: str = "",
        error: str = "",
    ) -> CandidateExecutionResult | None:
        from app.formula.classification_metrics_salvage import (
            salvage_classification_metrics_latex,
        )
        from app.ocr.failure_class import classify_recovery_failure

        orig_full = cand.raw_text or cand.text or ""
        salv = salvage_classification_metrics_latex(
            orig_full,
            cfg=fcfg,
            context_before=cand.context_before or "",
        )
        if not salv:
            return None
        ok, reason = self._gate(salv, cand, fcfg)
        if not ok:
            return None
        n = eq_number_from_candidate(cand)
        cid = (getattr(cand, "candidate_id", "") or "").strip()
        if not cid:
            cid = f"p{cand.page}_eq{n or 'x'}_{id(cand) % 100000}"
        fail_cls = classify_recovery_failure(
            gate_accepted=ok,
            gate_reason=reason,
            error="",
            extractor_method="classification_metrics_original_salvage",
            raw_output="",
            selected_latex=salv,
        )
        return CandidateExecutionResult(
            page=cand.page,
            eq_number=n,
            candidate_id=str(cid),
            selected_latex=salv,
            gate_accepted=ok,
            gate_reason=reason,
            extractor_method="classification_metrics_original_salvage",
            error=error,
            scheduler_mode=scheduler_mode,
            original=orig_full[:500],
            recovered=salv[:500],
            would_replace=True,
            raw_output="",
            failure_class=fail_cls.value,
            salvage_used=True,
        )

    def _try_prose_prefix_salvage_result(
        self,
        cand: FormulaCandidate,
        fcfg: FormulaConfig,
        *,
        scheduler_mode: str = "",
        error: str = "",
    ) -> CandidateExecutionResult | None:
        from app.formula.prose_prefix_salvage import salvage_prose_prefixed_latex
        from app.ocr.failure_class import classify_recovery_failure

        orig_full = cand.raw_text or cand.text or ""
        salv = salvage_prose_prefixed_latex(
            orig_full,
            cfg=fcfg,
            context_before=cand.context_before or "",
        )
        if not salv:
            return None
        ok, reason = self._gate(salv, cand, fcfg)
        if not ok:
            return None
        n = eq_number_from_candidate(cand)
        cid = (getattr(cand, "candidate_id", "") or "").strip()
        if not cid:
            cid = f"p{cand.page}_eq{n or 'x'}_{id(cand) % 100000}"
        fail_cls = classify_recovery_failure(
            gate_accepted=ok,
            gate_reason=reason,
            error="",
            extractor_method="prose_prefix_original_salvage",
            raw_output="",
            selected_latex=salv,
        )
        return CandidateExecutionResult(
            page=cand.page,
            eq_number=n,
            candidate_id=str(cid),
            selected_latex=salv,
            gate_accepted=ok,
            gate_reason=reason,
            extractor_method="prose_prefix_original_salvage",
            error=error,
            scheduler_mode=scheduler_mode,
            original=orig_full[:500],
            recovered=salv[:500],
            would_replace=True,
            raw_output="",
            failure_class=fail_cls.value,
            salvage_used=True,
        )

    def _extract_and_gate(
        self,
        *,
        raw: str,
        cand: FormulaCandidate,
        fcfg: FormulaConfig,
        scheduler_mode: str = "",
        formula_crop: bool = True,
    ) -> CandidateExecutionResult:
        n = eq_number_from_candidate(cand)
        cid = (getattr(cand, "candidate_id", "") or "").strip()
        if not cid:
            cid = f"p{cand.page}_eq{n or 'x'}_{id(cand) % 100000}"
        t_eg = time.perf_counter()
        salvage_used = False
        if formula_crop:
            from app.ocr.formula_crop_extract import extract_formula_crop

            er = extract_formula_crop(
                raw,
                eq_number=n,
                context_before=cand.context_before or "",
                context_after=cand.context_after or "",
                original_latex=(cand.raw_text or cand.text or ""),
            )
            salvage_used = str(er.method or "").startswith("formula_crop") and bool(er.latex)
        else:
            er = self.extractor.extract(
                raw,
                eq_number=n,
                context_before=cand.context_before,
                context_after=cand.context_after,
            )
        latex = er.latex or ""
        # Phase 6E：主提取失败时 CPU salvage（仍用同一 raw，不增 OCR）
        if not latex and formula_crop:
            from app.ocr.formula_crop_extract import salvage_formula_from_raw

            er2 = salvage_formula_from_raw(raw)
            if er2.latex:
                er = er2
                latex = er2.latex
                salvage_used = True
        if latex:
            from app.formula.gain import repair_known_ocr_subscripts

            original = (cand.raw_text or cand.text or "")
            latex = repair_known_ocr_subscripts(original, latex)
        ok, reason = self._gate(latex, cand, fcfg) if latex else (False, er.failure_reason or "empty")
        if not ok:
            salv_row = self._try_spaced_letter_salvage_result(
                cand,
                fcfg,
                scheduler_mode=scheduler_mode,
                error=er.failure_reason or reason or "empty",
            )
            if salv_row is not None:
                return salv_row
            salv_row = self._try_classification_metrics_salvage_result(
                cand,
                fcfg,
                scheduler_mode=scheduler_mode,
                error=er.failure_reason or reason or "empty",
            )
            if salv_row is not None:
                return salv_row
            salv_row = self._try_prose_prefix_salvage_result(
                cand,
                fcfg,
                scheduler_mode=scheduler_mode,
                error=er.failure_reason or reason or "empty",
            )
            if salv_row is not None:
                return salv_row
        _ = time.perf_counter() - t_eg
        original = (cand.raw_text or cand.text or "")[:500]
        from app.ocr.failure_class import classify_recovery_failure

        fail_cls = classify_recovery_failure(
            gate_accepted=ok,
            gate_reason=reason,
            error="" if latex else (er.failure_reason or "formula_not_found_in_ocr"),
            extractor_method=er.method,
            raw_output=raw,
            selected_latex=latex,
        )
        return CandidateExecutionResult(
            page=cand.page,
            eq_number=n,
            candidate_id=cid,
            selected_latex=latex,
            gate_accepted=ok,
            gate_reason=reason,
            extractor_method=er.method,
            error="" if latex else (er.failure_reason or "formula_not_found_in_ocr"),
            scheduler_mode=scheduler_mode,
            original=original,
            recovered=latex[:500],
            would_replace=bool(ok and latex.strip()),
            raw_output=(raw or "")[:2000],
            failure_class=fail_cls.value,
            salvage_used=salvage_used,
        )

    def _page_cache_key(self, context: ExecutorContext, page: int) -> tuple[Any, ...]:
        conf = {
            "page_render_scale": context.page_render_scale,
            "prompt": self.prompt or "",
            "recognizer": getattr(self.recognizer, "name", "deepseek-ocr-2"),
        }
        return self.page_cache.make_key(
            pdf_hash=context.pdf_hash or "nopdf",
            page=page,
            recognizer=getattr(self.recognizer, "name", "deepseek-ocr-2"),
            config=conf,
        )

    def _exec_page_reuse(
        self,
        page_candidates: list[FormulaCandidate],
        decision: RecoveryCostEstimate,
        context: ExecutorContext,
    ) -> RecoveryExecutionResult:
        fcfg = context.formula_config or FormulaConfig()
        page = int(decision.page if decision.page is not None else (page_candidates[0].page or 0))
        key = self._page_cache_key(context, page)
        cached = self.page_cache.get(key)
        rows: list[CandidateExecutionResult] = []
        if cached is None:
            return RecoveryExecutionResult(
                mode=RecoveryMode.PAGE_REUSE,
                decision_reason=decision.reason,
                ocr_calls=0,
                cache_hit=False,
                marginal_ocr_seconds=0.0,
                error="page_cache_miss",
                candidates=rows,
            )
        raw = cached.text or ""
        mode_s = decision.chosen_mode.value
        for cand in page_candidates:
            rows.append(
                self._extract_and_gate(
                    raw=raw,
                    cand=cand,
                    fcfg=fcfg,
                    scheduler_mode=mode_s,
                    formula_crop=False,
                )
            )
        acc = sum(1 for r in rows if r.gate_accepted)
        return RecoveryExecutionResult(
            mode=RecoveryMode.PAGE_REUSE,
            decision_reason=decision.reason,
            ocr_calls=0,
            cache_hit=True,
            marginal_ocr_seconds=0.0,
            accepted=acc,
            rejected=len(rows) - acc,
            candidates=rows,
        )

    def _exec_page(
        self,
        page_candidates: list[FormulaCandidate],
        decision: RecoveryCostEstimate,
        context: ExecutorContext,
    ) -> RecoveryExecutionResult:
        fcfg = context.formula_config or FormulaConfig()
        page = int(decision.page if decision.page is not None else (page_candidates[0].page or 0))
        key = self._page_cache_key(context, page)
        cached = self.page_cache.get(key)
        if cached is not None:
            # 决策是 PAGE 但已有 cache：仍 0 OCR，不污染 EMA
            raw = cached.text or ""
            mode_s = decision.chosen_mode.value
            rows = [
                self._extract_and_gate(
                    raw=raw, cand=c, fcfg=fcfg, scheduler_mode=mode_s
                )
                for c in page_candidates
            ]
            acc = sum(1 for r in rows if r.gate_accepted)
            return RecoveryExecutionResult(
                mode=RecoveryMode.PAGE,
                decision_reason=decision.reason,
                ocr_calls=0,
                cache_hit=True,
                marginal_ocr_seconds=0.0,
                accepted=acc,
                rejected=len(rows) - acc,
                candidates=rows,
                error="page_already_cached_zero_ocr",
            )

        if context.session.pdf_doc is None:
            return RecoveryExecutionResult(
                mode=RecoveryMode.PAGE,
                decision_reason=decision.reason,
                error="no_pdf_doc",
            )

        page_obj = context.session.pdf_doc[page]
        image = render_clip(page_obj, page_bbox(page_obj), scale=context.page_render_scale)
        doc_res = self._recognize_with_timeout(image, mode=OCRMode.PAGE)
        meta = doc_res.metadata or {}
        load_s = float(meta.get("model_load_seconds") or 0.0)
        infer_s = float(meta.get("ocr_inference_seconds") or doc_res.elapsed_seconds or 0.0)
        # 首次 load：若 class 已 load，load_s 可能是累计值；仅 cold 时 observe
        was_loaded = self.cost.runtime.model_loaded
        abort = _abort_reason_from_ocr(doc_res.error, success=bool(doc_res.success))
        if not was_loaded and load_s > 0.5:
            self.cost.observe_model_load(load_s, success=not abort, abort_reason=abort)
        self.cost.observe_page(
            infer_s, from_cache=False, success=not abort, abort_reason=abort
        )
        if doc_res.success:
            self.page_cache.put(key, doc_res)

        raw = doc_res.text or ""
        mode_s = decision.chosen_mode.value
        t_eg = time.perf_counter()
        rows = [
            self._extract_and_gate(
                raw=raw,
                cand=c,
                fcfg=fcfg,
                scheduler_mode=mode_s,
                formula_crop=False,
            )
            for c in page_candidates
        ]
        eg_sec = time.perf_counter() - t_eg
        acc = sum(1 for r in rows if r.gate_accepted)
        return RecoveryExecutionResult(
            mode=RecoveryMode.PAGE,
            decision_reason=decision.reason,
            ocr_calls=1,
            cache_hit=False,
            marginal_ocr_seconds=infer_s,
            model_load_seconds=0.0 if was_loaded else load_s,
            inference_seconds=infer_s,
            extract_gate_seconds=eg_sec,
            accepted=acc,
            rejected=len(rows) - acc,
            candidates=rows,
            error=doc_res.error or "",
        )

    def _exec_formula_batch(
        self,
        page_candidates: list[FormulaCandidate],
        decision: RecoveryCostEstimate,
        context: ExecutorContext,
    ) -> RecoveryExecutionResult:
        fcfg = context.formula_config or FormulaConfig()
        rows: list[CandidateExecutionResult] = []
        ocr_calls = 0
        infer_total = 0.0
        load_total = 0.0
        was_loaded = self.cost.runtime.model_loaded

        if context.session.pdf_doc is None:
            return RecoveryExecutionResult(
                mode=decision.chosen_mode,
                decision_reason=decision.reason,
                error="no_pdf_doc",
            )

        for cand in page_candidates:
            row, ocr_delta, infer_part, load_part = self._ocr_one_formula(
                context, cand, decision, fcfg, was_loaded=was_loaded
            )
            ocr_calls += ocr_delta
            infer_total += infer_part
            if load_part > 0:
                load_total += load_part
            rows.append(row)
        acc = sum(1 for r in rows if r.gate_accepted)
        return RecoveryExecutionResult(
            mode=decision.chosen_mode,
            decision_reason=decision.reason,
            ocr_calls=ocr_calls,
            cache_hit=False,
            marginal_ocr_seconds=infer_total,
            model_load_seconds=0.0 if was_loaded else load_total,
            inference_seconds=infer_total,
            accepted=acc,
            rejected=len(rows) - acc,
            candidates=rows,
        )

    def _ocr_one_formula(
        self,
        context: ExecutorContext,
        cand: FormulaCandidate,
        decision: Any,
        fcfg: FormulaConfig,
        *,
        was_loaded: bool,
    ) -> tuple[CandidateExecutionResult, int, float, float]:
        """单次公式 OCR；散文 ref 时允许一次全页重定位重试。"""
        from app.ocr.extractor import ocr_raw_is_prose_ref

        ocr_calls = 0
        infer_total = 0.0
        load_total = 0.0
        t_render = time.perf_counter()
        crop_bbox = cand.bbox
        try:
            from app.formula.geometry import crop_bbox_suspicious, refine_formula_crop_bbox

            need_refine = cand.page is None or cand.bbox is None
            if (
                not need_refine
                and getattr(cand, "_geometry_prefetched", False)
                and getattr(cand, "crop_class", "") not in {"likely_prose", "likely_table"}
            ):
                need_refine = False
            elif not need_refine:
                need_refine = crop_bbox_suspicious(
                    context.session.pdf_doc,
                    cand.page,
                    cand.bbox,
                    getattr(cand, "crop_class", "") or "",
                )

            if need_refine:
                refined = refine_formula_crop_bbox(
                    context.session.pdf_doc,
                    getattr(context.session, "anchor_index", None),
                    page=cand.page,
                    bbox=cand.bbox,
                    context_before=cand.context_before or "",
                    context_after=cand.context_after or "",
                    equation_number=(cand.equation_number or "").strip(),
                    crop_class=getattr(cand, "crop_class", "") or "",
                    original_latex=cand.raw_text or cand.text or "",
                )
                if refined is not None:
                    cand.page, crop_bbox, cand.crop_class, cand.geometry_source = (
                        refined[0],
                        refined[1],
                        refined[2],
                        refined[3],
                    )
                    cand.bbox = crop_bbox
                    cand.recovery_log.append(
                        {
                            "action": "ocr_pre_refine",
                            "page": cand.page,
                            "source": cand.geometry_source,
                        }
                    )
        except Exception:
            crop_bbox = cand.bbox

        if (
            cand.page is not None
            and crop_bbox is not None
            and getattr(cand, "crop_class", "") in {"likely_prose", "likely_table"}
            and not getattr(cand, "_prose_precheck_relocate", False)
        ):
            try:
                from app.formula.geometry import proactive_cross_page_relocate

                old_page, old_bbox = cand.page, crop_bbox
                retry_refined = proactive_cross_page_relocate(
                    context.session.pdf_doc,
                    getattr(context.session, "anchor_index", None),
                    page=cand.page,
                    bbox=crop_bbox,
                    context_before=cand.context_before or "",
                    context_after=cand.context_after or "",
                    equation_number=(cand.equation_number or "").strip(),
                    original_latex=cand.raw_text or cand.text or "",
                )
                if retry_refined and (
                    retry_refined[0] != old_page or retry_refined[1] != old_bbox
                ):
                    setattr(cand, "_prose_precheck_relocate", True)
                    cand.page, crop_bbox = retry_refined[0], retry_refined[1]
                    cand.bbox = crop_bbox
                    cand.crop_class, cand.geometry_source = retry_refined[2], retry_refined[3]
                    cand.recovery_log.append(
                        {
                            "action": "ocr_prose_precheck_relocate",
                            "page": cand.page,
                            "source": cand.geometry_source,
                        }
                    )
            except Exception:
                pass

        if cand.page is None or crop_bbox is None:
            try:
                from app.formula.geometry import FormulaGeometryResolver

                dec = FormulaGeometryResolver(
                    context.session.pdf_doc,
                    getattr(context.session, "anchor_index", None),
                ).resolve(
                    context_before=cand.context_before or "",
                    context_after=cand.context_after or "",
                    equation_number=(cand.equation_number or "").strip(),
                    hint_page=cand.page,
                    original_latex=cand.raw_text or cand.text or "",
                )
                if dec.page is not None and dec.bbox is not None:
                    cand.page, crop_bbox = int(dec.page), tuple(dec.bbox)
                    cand.bbox = crop_bbox
                    cand.crop_class = dec.crop_class or ""
                    cand.geometry_source = dec.source or "resolver_fallback"
                    cand.recovery_log.append(
                        {
                            "action": "executor_resolver_fallback",
                            "page": cand.page,
                            "source": cand.geometry_source,
                        }
                    )
            except Exception:
                pass

        if cand.page is None or crop_bbox is None:
            salv_row = self._try_spaced_letter_salvage_result(
                cand,
                fcfg,
                scheduler_mode=decision.chosen_mode.value,
                error="geometry_unresolved",
            )
            if salv_row is not None:
                return salv_row, 0, 0.0, 0.0
            cid = getattr(cand, "candidate_id", "") or eq_number_from_candidate(cand)
            return (
                CandidateExecutionResult(
                    page=cand.page,
                    eq_number=eq_number_from_candidate(cand),
                    candidate_id=str(cid),
                    error="geometry_unresolved",
                    scheduler_mode=decision.chosen_mode.value,
                    original=(cand.raw_text or cand.text or "")[:500],
                    failure_class="extraction_failure",
                ),
                0,
                0.0,
                0.0,
            )

        def _run_ocr() -> tuple[str, CandidateExecutionResult, float, float, float, int, int]:
            nonlocal crop_bbox
            page_obj = context.session.pdf_doc[cand.page]
            image = render_clip(
                page_obj, crop_bbox, scale=context.formula_render_scale
            )
            render_s = time.perf_counter() - t_render
            crop_w = int(getattr(image, "size", (0, 0))[0] or 0)
            crop_h = int(getattr(image, "size", (0, 0))[1] or 0)
            gpu_before = _gpu_snapshot()
            t_queue = time.perf_counter()
            doc_res = self._recognize_with_timeout(image, mode=OCRMode.FORMULA)
            wall_recognize = time.perf_counter() - t_queue
            meta = doc_res.metadata or {}
            load_s = float(
                meta.get("cold_start_seconds")
                or meta.get("model_load_seconds")
                or 0.0
            )
            infer_s = float(meta.get("ocr_inference_seconds") or doc_res.elapsed_seconds or 0.0)
            worker_infer = float(
                meta.get("worker_elapsed_seconds")
                or meta.get("ocr_inference_seconds")
                or infer_s
            )
            accounted = worker_infer + load_s
            queue_wait = max(0.0, wall_recognize - accounted)
            cold_s = float(meta.get("cold_start_seconds") or 0.0)
            if cold_s < 0.5 and not was_loaded and wall_recognize > infer_s + 5.0:
                cold_s = max(0.0, wall_recognize - max(infer_s, worker_infer))
                load_s = max(load_s, cold_s)
                queue_wait = max(0.0, wall_recognize - worker_infer - load_s)
            abort = _abort_reason_from_ocr(doc_res.error, success=bool(doc_res.success))
            if (not self.cost.runtime.model_loaded) and load_s > 0.5:
                self.cost.observe_model_load(
                    load_s, success=not abort, abort_reason=abort
                )
            self.cost.observe_formula(
                infer_s, success=not abort, abort_reason=abort
            )
            raw = doc_res.text or ""
            t_post = time.perf_counter()
            row = self._extract_and_gate(
                raw=raw,
                cand=cand,
                fcfg=fcfg,
                scheduler_mode=decision.chosen_mode.value,
                formula_crop=True,
            )
            post_s = time.perf_counter() - t_post
            if doc_res.error and not row.selected_latex:
                row.error = doc_res.error
            gpu_after = _gpu_snapshot()
            row.timing = {
                "candidate_id": row.candidate_id,
                "crop_px_width": crop_w,
                "crop_px_height": crop_h,
                "render_seconds": round(render_s, 4),
                "queue_wait_seconds": round(queue_wait, 4),
                "worker_ready_wait_seconds": round(queue_wait, 4),
                "worker_inference_seconds": round(worker_infer, 4),
                "ocr_seconds": round(infer_s, 4),
                "model_load_seconds": round(load_s, 4),
                "cold_start_seconds": round(
                    cold_s if cold_s else (load_s if not was_loaded else 0.0), 4
                ),
                "recognize_wall_seconds": round(wall_recognize, 4),
                "postprocess_seconds": round(post_s, 4),
                "extraction_cpu_seconds": round(post_s, 4),
                "recovery_seconds": round(wall_recognize + post_s, 4),
                "gpu_before": gpu_before,
                "gpu_after": gpu_after,
                "worker_gpu_allocated_mb": meta.get("gpu_allocated_mb"),
                "worker_gpu_free_mb": meta.get("gpu_free_mb"),
                "timing_breakdown": meta.get("timing_breakdown") or {},
                "profile": meta.get("profile"),
                "max_new_tokens": meta.get("max_new_tokens"),
                "crop_mode": meta.get("crop_mode"),
                "input_px_width": meta.get("input_px_width"),
                "input_px_height": meta.get("input_px_height"),
                "model_dtype": meta.get("model_dtype"),
                "cold_start_inferred": bool(meta.get("cold_start_inferred")),
                "auto_load_before_recognize": bool(meta.get("auto_load_before_recognize")),
            }
            return raw, row, infer_s, load_s if not was_loaded and load_s > 0.5 else 0.0, wall_recognize, crop_w, crop_h

        raw, row, infer_s, load_s, _, _, _ = _run_ocr()
        ocr_calls += 1
        infer_total += infer_s
        load_total += load_s

        from app.formula.tokens import operator_direction_conflict

        dir_conflict = False
        if row.selected_latex:
            dir_conflict, _ = operator_direction_conflict(
                cand.context_before or "",
                row.selected_latex or "",
                original_latex=cand.raw_text or cand.text or "",
            )

        if (
            not row.gate_accepted
            and not getattr(cand, "_geometry_ocr_retry", False)
            and (
                (not row.selected_latex and ocr_raw_is_prose_ref(raw))
                or dir_conflict
                or (
                    ocr_raw_is_prose_ref(raw)
                    and "no_equation_blocks" in (row.gate_reason or "")
                )
            )
        ):
            try:
                from app.formula.geometry import proactive_cross_page_relocate

                old_page, old_bbox = cand.page, cand.bbox
                retry_refined = proactive_cross_page_relocate(
                    context.session.pdf_doc,
                    getattr(context.session, "anchor_index", None),
                    page=cand.page,
                    bbox=cand.bbox,
                    context_before=cand.context_before or "",
                    context_after=cand.context_after or "",
                    equation_number=(cand.equation_number or "").strip(),
                    original_latex=cand.raw_text or cand.text or "",
                )
                if retry_refined and (
                    retry_refined[0] != old_page or retry_refined[1] != old_bbox
                ):
                    setattr(cand, "_geometry_ocr_retry", True)
                    cand.page, crop_bbox = retry_refined[0], retry_refined[1]
                    cand.bbox = crop_bbox
                    cand.crop_class, cand.geometry_source = retry_refined[2], retry_refined[3]
                    cand.recovery_log.append(
                        {
                            "action": (
                                "ocr_direction_retry_relocate"
                                if dir_conflict
                                else "ocr_prose_retry_relocate"
                            ),
                            "page": cand.page,
                            "source": cand.geometry_source,
                        }
                    )
                    raw2, row2, infer2, load2, _, _, _ = _run_ocr()
                    ocr_calls += 1
                    infer_total += infer2
                    load_total += load2
                    if row2.timing:
                        row2.timing["geometry_relocate_retry"] = True
                    row = row2
                    _ = raw2
            except Exception:
                pass

        return row, ocr_calls, infer_total, load_total
