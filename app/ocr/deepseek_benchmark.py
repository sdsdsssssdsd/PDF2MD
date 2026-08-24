"""DeepSeek-OCR 2 vs Pix2Tex/UniMERNet 对比 Benchmark（实验专用，不改 Markdown）。

四组：
  A. formula recognizer (pix2tex / unimernet) on formula bbox
  B. DeepSeek formula bbox
  C. DeepSeek region
  D. DeepSeek page（同页复用 PageOCRCache）
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from app.formula.benchmark import (
    BenchmarkCase,
    crop_formula_image,
    resolve_case_bbox,
)
from app.formula.config import FormulaConfig
from app.formula.gain import evaluate_recovery_gain
from app.formula.recognizer import FormulaRecognizer, build_recognizer
from app.formula.session import FormulaRecoverySession
from app.formula.validator import validate_latex
from app.ocr import OCRMode, PROMPT_DOCUMENT
from app.ocr.cache import PageOCRCache, RegionOCRCache, file_sha1
from app.ocr.crops import page_bbox, region_bbox_from_formula, render_clip
from app.ocr.deepseek_ocr2 import DeepSeekOCR2Recognizer, FakeDeepSeekOCR2Recognizer
from app.ocr.deepseek_profiles import DeepSeekOCRProfile, DEEPSEEK_FORMULA_PROFILE
from app.ocr.extractor import (
    EquationExtractor,
    extractor_selected_gold,
    raw_ocr_contains_gold,
)
from app.ocr.match_eval import FormulaMatchEvaluator
from app.ocr.k4_failure_taxonomy import classify_failure_layer
from app.utils.paths import BENCHMARK_RUNS, ensure_dirs

ProgressCB = Callable[[str], None]


@dataclass
class DeepSeekBenchmarkConfig:
    enabled: bool = False
    experiment_only: bool = True
    experiment_id: str = ""  # k4 A/B/C/D/E
    model_name: str = "deepseek-ai/DeepSeek-OCR-2"
    device: str = "auto"
    dtype: str = "auto"
    base_size: int = 1024
    image_size: int = 768
    crop_mode: bool = True
    allow_cpu: bool = False
    prompt: str = PROMPT_DOCUMENT
    formula_render_scale: float = 2.0
    region_render_scale: float = 1.8
    page_render_scale: float = 1.5
    region_height_ratio: float = 0.22
    baseline_recognizer: str = "pix2tex"  # pix2tex | unimernet
    run_baseline: bool = True
    run_deepseek_formula: bool = True
    run_deepseek_region: bool = True
    run_deepseek_page: bool = True


@dataclass
class ModeTiming:
    model_load_seconds: float = 0.0
    pdf_render_seconds: float = 0.0
    ocr_inference_seconds: float = 0.0
    postprocess_seconds: float = 0.0
    validation_seconds: float = 0.0
    total_seconds: float = 0.0
    cache_hit: bool = False


@dataclass
class ModeResult:
    recognizer: str
    mode: str
    output: str = ""
    extracted_latex: str = ""
    error: str = ""
    timing: ModeTiming = field(default_factory=ModeTiming)
    syntax_score: float = 0.0
    corruption_score: float = 1.0
    context_score: float = 0.0
    structure_score: float = 0.0
    gain: float = 0.0
    accepted: bool = False
    reason: str = ""
    gold_match: str = "—"  # = extractor_selected_gold（兼容旧字段）
    failure_code: str = ""
    raw_ocr_contains_gold: str = "—"
    extractor_selected_gold: str = "—"
    extractor_failure_reason: str = ""
    extractor_method: str = ""
    equation_block_count: int = 0
    exact_normalized_match: bool = False
    structural_match: bool = False
    human_usable: bool = False
    failure_layer: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# O-018 五个关键回归式（可被 corpus JSON 覆盖）
DEFAULT_O018_CASES: list[dict[str, Any]] = [
    {
        "eq_number": "1",
        "context_before": "The expected mean squared error (MSE) of a predictive model can be expressed by Eq. (1):",
        "gold_latex": r"E[(y-\hat{f})^2]=Bias^2+Var+\varepsilon",
        "parser_latex": "",
    },
    {
        "eq_number": "4",
        "context_before": "Recall can be calculated using Eq. (4):",
        "gold_latex": r"Recall=\frac{TP}{TP+FN}",
        "parser_latex": "",
    },
    {
        "eq_number": "5",
        "context_before": "It can be calculated from Eq. (5):",
        "gold_latex": r"F1=2\times\frac{Precision\times Recall}{Precision+Recall}",
        "parser_latex": "",
    },
    {
        "eq_number": "6",
        "context_before": "True Positive Rate (TPR), which can be calculated using Eq. (6)",
        "gold_latex": r"TPR=\frac{TP}{TP+FN}",
        "parser_latex": "",
    },
    {
        "eq_number": "7",
        "context_before": "False Positive Rate (FPR) using Eq. (7)",
        "gold_latex": r"FPR=\frac{FP}{FP+TN}",
        "parser_latex": "",
    },
]


class FormulaBenchmarkService:
    """CLI / 未来 Qt 共用的 DeepSeek 对比服务。"""

    def __init__(
        self,
        cfg: DeepSeekBenchmarkConfig | None = None,
        *,
        doc_recognizer: Any | None = None,
        formula_recognizer: FormulaRecognizer | None = None,
    ) -> None:
        self.cfg = cfg or DeepSeekBenchmarkConfig()
        self.doc_recognizer = doc_recognizer
        self.formula_recognizer = formula_recognizer
        self.page_cache = PageOCRCache()
        self.region_cache = RegionOCRCache()
        self.extractor = EquationExtractor()
        self._match_eval = FormulaMatchEvaluator()
        self.telemetry: dict[str, Any] = {
            "ocr_calls": 0,
            "unique_pages_ocr": 0,
            "unique_regions_ocr": 0,
            "cache_hits": 0,
        }
        self._pages_seen: set[int] = set()
        self._regions_seen: set[tuple[Any, ...]] = set()

    def _get_doc_recognizer(self) -> Any:
        if self.doc_recognizer is not None:
            return self.doc_recognizer
        fp = DeepSeekOCRProfile(
            name=f"formula_k4_{self.cfg.image_size}",
            base_size=int(self.cfg.base_size),
            image_size=int(self.cfg.image_size),
            crop_mode=bool(self.cfg.crop_mode),
            max_new_tokens=DEEPSEEK_FORMULA_PROFILE.max_new_tokens,
            save_results=DEEPSEEK_FORMULA_PROFILE.save_results,
            eval_mode=DEEPSEEK_FORMULA_PROFILE.eval_mode,
            prompt=self.cfg.prompt,
        )
        self.doc_recognizer = DeepSeekOCR2Recognizer(
            model_name=self.cfg.model_name,
            device=self.cfg.device,
            dtype=self.cfg.dtype,
            base_size=self.cfg.base_size,
            image_size=self.cfg.image_size,
            crop_mode=self.cfg.crop_mode,
            allow_cpu=self.cfg.allow_cpu,
            default_prompt=self.cfg.prompt,
            formula_profile=fp,
        )
        return self.doc_recognizer

    def _get_formula_recognizer(self) -> FormulaRecognizer:
        if self.formula_recognizer is not None:
            return self.formula_recognizer
        self.formula_recognizer = build_recognizer(
            FormulaConfig(recognizer_primary=self.cfg.baseline_recognizer)
        )
        return self.formula_recognizer

    def run_case(
        self,
        case: BenchmarkCase,
        *,
        progress: ProgressCB | None = None,
    ) -> dict[str, Any]:
        ensure_dirs()
        cfg = self.cfg
        fcfg = FormulaConfig()
        pdf = Path(case.pdf_path)
        pdf_hash = file_sha1(pdf)
        modes: dict[str, ModeResult] = {}

        def emit(msg: str) -> None:
            if progress:
                progress(msg)

        with FormulaRecoverySession(pdf, fcfg) as session:
            page, formula_box = resolve_case_bbox(case, session)
            page_obj = session.pdf_doc[page]
            region_box = region_bbox_from_formula(
                page_obj, formula_box, height_ratio=cfg.region_height_ratio
            )
            full_box = page_bbox(page_obj)

            before_q = None
            if (case.parser_latex or "").strip():
                vr0 = validate_latex(
                    case.parser_latex,
                    fcfg,
                    context_before=case.context_before,
                    context_after=case.context_after,
                )
                before_q = vr0.quality

            if cfg.run_baseline:
                emit(f"Eq.({case.eq_number}) baseline {cfg.baseline_recognizer}")
                modes["baseline"] = self._run_baseline(
                    session, page, formula_box, case, before_q
                )

            if cfg.run_deepseek_formula:
                emit(f"Eq.({case.eq_number}) deepseek formula")
                modes["deepseek_formula"] = self._run_doc_mode(
                    session,
                    pdf_hash=pdf_hash,
                    page=page,
                    bbox=formula_box,
                    scale=cfg.formula_render_scale,
                    mode=OCRMode.FORMULA,
                    case=case,
                    before_q=before_q,
                )

            if cfg.run_deepseek_region:
                emit(f"Eq.({case.eq_number}) deepseek region")
                modes["deepseek_region"] = self._run_doc_mode(
                    session,
                    pdf_hash=pdf_hash,
                    page=page,
                    bbox=region_box,
                    scale=cfg.region_render_scale,
                    mode=OCRMode.REGION,
                    case=case,
                    before_q=before_q,
                )

            if cfg.run_deepseek_page:
                emit(f"Eq.({case.eq_number}) deepseek page")
                modes["deepseek_page"] = self._run_page_mode(
                    session,
                    pdf_hash=pdf_hash,
                    page=page,
                    bbox=full_box,
                    case=case,
                    before_q=before_q,
                )

        return {
            "equation": f"Eq. ({case.eq_number})",
            "page": page,
            "formula_bbox": list(formula_box),
            "region_bbox": list(region_box),
            "parser_formula": case.parser_latex,
            "gold_latex": case.gold_latex,
            "context_before": case.context_before,
            "modes": {k: v.to_dict() for k, v in modes.items()},
            "experiment_only": cfg.experiment_only,
        }

    def _score_latex(
        self,
        latex: str,
        case: BenchmarkCase,
        before_q: Any,
        *,
        t_val0: float | None = None,
    ) -> tuple[dict[str, Any], float]:
        fcfg = FormulaConfig()
        t0 = t_val0 or time.perf_counter()
        if not (latex or "").strip():
            return {
                "syntax_score": 0.0,
                "corruption_score": 1.0,
                "context_score": 0.0,
                "structure_score": 0.0,
                "gain": 0.0,
                "accepted": False,
                "reason": "formula_not_found_in_ocr",
                "failure_code": "formula_not_found_in_ocr",
                "gold_match": "—",
                "extractor_selected_gold": "—",
                "exact_normalized_match": False,
                "structural_match": False,
                "human_usable": False,
            }, time.perf_counter() - t0
        vr = validate_latex(
            latex,
            fcfg,
            context_before=case.context_before,
            context_after=case.context_after,
        )
        q = vr.quality
        gain = evaluate_recovery_gain(
            before_quality=before_q,
            after_quality=q,
            before_latex=case.parser_latex,
            after_latex=latex,
            context_before=case.context_before,
            context_after=case.context_after,
            after_valid=bool(latex) and vr.valid,
        )
        reason = ",".join(gain.reasons) if gain.reasons else ("accepted" if gain.accept else "rejected")
        failure = ""
        if not gain.accept:
            if "ocr_context_conflict" in gain.reasons:
                failure = "context_conflict"
            elif not vr.valid:
                failure = "invalid_latex"
            elif q and q.corruption_score >= 0.65:
                failure = "still_corrupted"
            else:
                failure = "insufficient_evidence"
        sel = extractor_selected_gold(latex, case.gold_latex)
        match = self._match_eval.compare(latex, case.gold_latex)
        return {
            "syntax_score": round(float(q.syntax_score) if q else 0.0, 3),
            "corruption_score": round(float(q.corruption_score) if q else 1.0, 3),
            "context_score": round(gain.token_overlap, 3),
            "structure_score": round(float(getattr(q, "structure_score", 0.0) or 0.0), 3)
            if q
            else 0.0,
            "gain": round(gain.gain, 3),
            "accepted": bool(gain.accept),
            "reason": reason,
            "failure_code": failure,
            "gold_match": sel,
            "extractor_selected_gold": sel,
            "exact_normalized_match": bool(match.exact_normalized_match),
            "structural_match": bool(match.structural_match),
            "human_usable": bool(match.human_usable),
        }, time.perf_counter() - t0

    def _failure_layer_for(
        self,
        *,
        raw_flag: str,
        sel: str,
        exact: bool,
        ocr_error: str = "",
    ) -> str:
        return classify_failure_layer(
            raw_ocr_contains_gold=raw_flag,
            extractor_selected_gold=sel,
            exact_normalized_match=exact,
            ocr_error=ocr_error,
        )

    def _run_baseline(
        self,
        session: FormulaRecoverySession,
        page: int,
        bbox: tuple[float, float, float, float],
        case: BenchmarkCase,
        before_q: Any,
    ) -> ModeResult:
        timing = ModeTiming()
        t_all = time.perf_counter()
        try:
            t0 = time.perf_counter()
            image = crop_formula_image(
                session, page, bbox, scale=self.cfg.formula_render_scale, pad_x=0.08, pad_y=0.12
            )
            timing.pdf_render_seconds = time.perf_counter() - t0
            rec = self._get_formula_recognizer()
            t1 = time.perf_counter()
            result = rec.recognize(image, context=None)
            timing.ocr_inference_seconds = time.perf_counter() - t1
            self.telemetry["ocr_calls"] += 1
            latex = (result.latex or "") if result.success else ""
            scores, vsec = self._score_latex(latex, case, before_q)
            timing.validation_seconds = vsec
            timing.total_seconds = time.perf_counter() - t_all
            raw_flag = raw_ocr_contains_gold(latex, case.gold_latex)
            scores["failure_layer"] = self._failure_layer_for(
                raw_flag=raw_flag,
                sel=scores.get("extractor_selected_gold", "—"),
                exact=bool(scores.get("exact_normalized_match")),
                ocr_error=result.error or "",
            )
            return ModeResult(
                recognizer=getattr(rec, "name", self.cfg.baseline_recognizer),
                mode="formula",
                output=latex,
                extracted_latex=latex,
                error=result.error or "",
                timing=timing,
                raw_ocr_contains_gold=raw_flag,
                extractor_method="baseline_direct",
                equation_block_count=1 if latex else 0,
                **scores,
            )
        except Exception as e:
            timing.total_seconds = time.perf_counter() - t_all
            return ModeResult(
                recognizer=self.cfg.baseline_recognizer,
                mode="formula",
                error=f"ocr_failed:{type(e).__name__}",
                timing=timing,
                failure_code="ocr_failed",
                reason=str(e)[:200],
            )

    def _run_doc_mode(
        self,
        session: FormulaRecoverySession,
        *,
        pdf_hash: str,
        page: int,
        bbox: tuple[float, float, float, float],
        scale: float,
        mode: OCRMode,
        case: BenchmarkCase,
        before_q: Any,
    ) -> ModeResult:
        timing = ModeTiming()
        t_all = time.perf_counter()
        rec = self._get_doc_recognizer()
        prompt = self.cfg.prompt
        cache_key = self.region_cache.make_key(
            pdf_hash=pdf_hash,
            page=page,
            bbox=bbox,
            recognizer=getattr(rec, "name", "deepseek-ocr-2"),
            render_scale=scale,
            prompt=prompt,
            mode=mode,
        )
        cached = self.region_cache.get(cache_key)
        if cached is not None:
            timing.cache_hit = True
            self.telemetry["cache_hits"] += 1
            doc_res = cached
        else:
            try:
                t0 = time.perf_counter()
                image = render_clip(session.pdf_doc[page], bbox, scale=scale)
                timing.pdf_render_seconds = time.perf_counter() - t0
                doc_res = rec.recognize(image, mode=mode, prompt=prompt)
                timing.model_load_seconds = float(
                    (doc_res.metadata or {}).get("model_load_seconds") or 0.0
                )
                timing.ocr_inference_seconds = float(
                    (doc_res.metadata or {}).get("ocr_inference_seconds")
                    or doc_res.elapsed_seconds
                )
                self.telemetry["ocr_calls"] += 1
                self.telemetry["unique_regions_ocr"] += 1
                self.region_cache.put(cache_key, doc_res)
            except Exception as e:
                timing.total_seconds = time.perf_counter() - t_all
                return ModeResult(
                    recognizer=getattr(rec, "name", "deepseek-ocr-2"),
                    mode=mode.value,
                    error=f"ocr_failed:{type(e).__name__}",
                    timing=timing,
                    failure_code="ocr_failed",
                    reason=str(e)[:200],
                )

        if not doc_res.success:
            timing.total_seconds = time.perf_counter() - t_all
            code = doc_res.error or "ocr_failed"
            if code == "gpu_recommended":
                code = "model_unavailable"
            return ModeResult(
                recognizer=doc_res.recognizer,
                mode=mode.value,
                output=doc_res.text,
                error=doc_res.error or "",
                timing=timing,
                failure_code=code,
                reason=str((doc_res.metadata or {}).get("detail") or doc_res.error or ""),
            )

        t_post = time.perf_counter()
        er = self.extractor.extract(
            doc_res.text,
            eq_number=case.eq_number,
            context_before=case.context_before,
            context_after=case.context_after,
        )
        latex = er.latex
        timing.postprocess_seconds = time.perf_counter() - t_post
        scores, vsec = self._score_latex(latex, case, before_q)
        if not latex and er.failure_reason:
            scores["reason"] = er.failure_reason
            scores["failure_code"] = "formula_not_found_in_ocr"
        timing.validation_seconds = vsec
        timing.total_seconds = time.perf_counter() - t_all
        raw = doc_res.text or ""
        raw_flag = raw_ocr_contains_gold(raw, case.gold_latex)
        scores["failure_layer"] = self._failure_layer_for(
            raw_flag=raw_flag,
            sel=scores.get("extractor_selected_gold", "—"),
            exact=bool(scores.get("exact_normalized_match")),
            ocr_error=doc_res.error or "",
        )
        return ModeResult(
            recognizer=doc_res.recognizer,
            mode=mode.value,
            output=raw[:16000],
            extracted_latex=latex,
            timing=timing,
            raw_ocr_contains_gold=raw_flag,
            extractor_failure_reason=er.failure_reason,
            extractor_method=er.method,
            equation_block_count=len(er.blocks),
            **scores,
        )

    def _run_page_mode(        self,
        session: FormulaRecoverySession,
        *,
        pdf_hash: str,
        page: int,
        bbox: tuple[float, float, float, float],
        case: BenchmarkCase,
        before_q: Any,
    ) -> ModeResult:
        timing = ModeTiming()
        t_all = time.perf_counter()
        rec = self._get_doc_recognizer()
        conf = {
            "base_size": self.cfg.base_size,
            "image_size": self.cfg.image_size,
            "crop_mode": self.cfg.crop_mode,
            "prompt": self.cfg.prompt,
            "page_render_scale": self.cfg.page_render_scale,
        }
        key = self.page_cache.make_key(
            pdf_hash=pdf_hash,
            page=page,
            recognizer=getattr(rec, "name", "deepseek-ocr-2"),
            config=conf,
        )
        cached = self.page_cache.get(key)
        if cached is not None:
            timing.cache_hit = True
            self.telemetry["cache_hits"] += 1
            doc_res = cached
        else:
            try:
                t0 = time.perf_counter()
                image = render_clip(
                    session.pdf_doc[page], bbox, scale=self.cfg.page_render_scale
                )
                timing.pdf_render_seconds = time.perf_counter() - t0
                doc_res = rec.recognize(image, mode=OCRMode.PAGE, prompt=self.cfg.prompt)
                timing.model_load_seconds = float(
                    (doc_res.metadata or {}).get("model_load_seconds") or 0.0
                )
                timing.ocr_inference_seconds = float(
                    (doc_res.metadata or {}).get("ocr_inference_seconds")
                    or doc_res.elapsed_seconds
                )
                self.telemetry["ocr_calls"] += 1
                if page not in self._pages_seen:
                    self._pages_seen.add(page)
                    self.telemetry["unique_pages_ocr"] += 1
                self.page_cache.put(key, doc_res)
            except Exception as e:
                timing.total_seconds = time.perf_counter() - t_all
                return ModeResult(
                    recognizer=getattr(rec, "name", "deepseek-ocr-2"),
                    mode="page",
                    error=f"ocr_failed:{type(e).__name__}",
                    timing=timing,
                    failure_code="ocr_failed",
                    reason=str(e)[:200],
                )

        if not doc_res.success:
            timing.total_seconds = time.perf_counter() - t_all
            code = doc_res.error or "ocr_failed"
            if code == "gpu_recommended":
                code = "model_unavailable"
            return ModeResult(
                recognizer=doc_res.recognizer,
                mode="page",
                output=doc_res.text,
                error=doc_res.error or "",
                timing=timing,
                failure_code=code,
                reason=str((doc_res.metadata or {}).get("detail") or doc_res.error or ""),
            )

        t_post = time.perf_counter()
        er = self.extractor.extract(
            doc_res.text,
            eq_number=case.eq_number,
            context_before=case.context_before,
            context_after=case.context_after,
        )
        latex = er.latex
        timing.postprocess_seconds = time.perf_counter() - t_post
        scores, vsec = self._score_latex(latex, case, before_q)
        if not latex and er.failure_reason:
            scores["reason"] = er.failure_reason
            scores["failure_code"] = "formula_not_found_in_ocr"
        timing.validation_seconds = vsec
        timing.total_seconds = time.perf_counter() - t_all
        raw = doc_res.text or ""
        return ModeResult(
            recognizer=doc_res.recognizer,
            mode="page",
            output=raw[:16000],
            extracted_latex=latex,
            timing=timing,
            raw_ocr_contains_gold=raw_ocr_contains_gold(raw, case.gold_latex),
            extractor_failure_reason=er.failure_reason,
            extractor_method=er.method,
            equation_block_count=len(er.blocks),
            **scores,
        )


def build_o018_cases(pdf_path: str | Path, specs: list[dict[str, Any]] | None = None) -> list[BenchmarkCase]:
    specs = specs or DEFAULT_O018_CASES
    pdf = str(pdf_path)
    return [
        BenchmarkCase(
            pdf_path=pdf,
            eq_number=str(s["eq_number"]),
            context_before=str(s.get("context_before") or ""),
            gold_latex=str(s.get("gold_latex") or ""),
            parser_latex=str(s.get("parser_latex") or ""),
        )
        for s in specs
    ]


def summarize_deepseek_run(results: list[dict[str, Any]], telemetry: dict[str, Any]) -> dict[str, Any]:
    modes = ["baseline", "deepseek_formula", "deepseek_region", "deepseek_page"]
    by_mode: dict[str, dict[str, Any]] = {}
    for m in modes:
        rows = [r["modes"].get(m) for r in results if r.get("modes", {}).get(m)]
        rows = [x for x in rows if x]
        if not rows:
            continue
        gold = sum(1 for x in rows if x.get("extractor_selected_gold") == "yes" or x.get("gold_match") == "yes")
        raw_gold = sum(1 for x in rows if x.get("raw_ocr_contains_gold") == "yes")
        exact = sum(1 for x in rows if x.get("exact_normalized_match"))
        human = sum(1 for x in rows if x.get("human_usable"))
        acc = sum(1 for x in rows if x.get("accepted"))
        layers: dict[str, int] = {}
        for x in rows:
            layer = str(x.get("failure_layer") or "unknown")
            layers[layer] = layers.get(layer, 0) + 1
        secs = [float((x.get("timing") or {}).get("total_seconds") or 0.0) for x in rows]
        by_mode[m] = {
            "n": len(rows),
            "raw_ocr_contains_gold": raw_gold,
            "extractor_selected_gold": gold,
            "gold_yes": gold,  # 兼容旧字段 = extractor_selected
            "exact_normalized_match": exact,
            "human_usable": human,
            "accepted": acc,
            "mean_seconds": round(sum(secs) / max(1, len(secs)), 3),
            "cache_hits": sum(1 for x in rows if (x.get("timing") or {}).get("cache_hit")),
            "extractor_gap": raw_gold - gold,
            "failure_layers": layers,
        }
    return {
        "by_mode": by_mode,
        "telemetry": telemetry,
        "default_recovery_path": "deepseek_formula",
        "region_page_policy": "multi_broken_on_page_with_cache_only",
        "k4_note": (
            "exact_normalized_match 才是公式级准确率；"
            "任务表「恢复覆盖」仅为 Gate 通过数，不是 Equation Exact Accuracy，不可混用。"
        ),
        "decision_hint": (
            "比较 raw_ocr_contains_gold vs extractor_selected_gold："
            "差距大说明抽取仍在拖累；extractor_gap→0 后再评估 RecoveryScheduler。"
            "单式默认路径保持 deepseek_formula，勿把 region/page 作为默认。"
        ),
    }


def run_deepseek_benchmark(
    pdf_path: str | Path,
    *,
    cfg: DeepSeekBenchmarkConfig | None = None,
    cases: list[BenchmarkCase] | None = None,
    doc_recognizer: Any | None = None,
    formula_recognizer: FormulaRecognizer | None = None,
    progress: ProgressCB | None = None,
    out_path: Path | None = None,
) -> dict[str, Any]:
    ensure_dirs()
    cfg = cfg or DeepSeekBenchmarkConfig(experiment_only=True)
    svc = FormulaBenchmarkService(
        cfg, doc_recognizer=doc_recognizer, formula_recognizer=formula_recognizer
    )
    case_list = cases or build_o018_cases(pdf_path)
    results: list[dict[str, Any]] = []
    t0 = time.perf_counter()
    for case in case_list:
        results.append(svc.run_case(case, progress=progress))
    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "pdf_path": str(pdf_path),
        "experiment_only": cfg.experiment_only,
        "config": {
            "experiment_id": cfg.experiment_id,
            "baseline_recognizer": cfg.baseline_recognizer,
            "model_name": cfg.model_name,
            "device": cfg.device,
            "base_size": cfg.base_size,
            "image_size": cfg.image_size,
            "formula_render_scale": cfg.formula_render_scale,
            "prompt_head": (cfg.prompt or "")[:80],
            "region_height_ratio": cfg.region_height_ratio,
        },
        "results": results,
        "summary": summarize_deepseek_run(results, dict(svc.telemetry)),
        "total_seconds": round(time.perf_counter() - t0, 3),
        "note": "experiment_only=true：结果不写入转换 Markdown。",
    }
    dest = out_path
    if dest is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = BENCHMARK_RUNS / f"{ts}_{Path(pdf_path).stem}_deepseek_benchmark.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    payload["output_path"] = str(dest)
    return payload


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="DeepSeek-OCR 2 formula recovery benchmark (experiment only)")
    p.add_argument("pdf", type=str, help="PDF path")
    p.add_argument("--baseline", default="pix2tex", choices=["pix2tex", "unimernet", "null"])
    p.add_argument("--fake", action="store_true", help="用 Fake recognizer（不下载模型）")
    p.add_argument("--skip-baseline", action="store_true")
    p.add_argument("--skip-deepseek-formula", action="store_true")
    p.add_argument("--skip-deepseek-region", action="store_true")
    p.add_argument("--skip-deepseek-page", action="store_true")
    p.add_argument("--allow-cpu", action="store_true")
    p.add_argument("--out", type=str, default="")
    args = p.parse_args(argv)

    cfg = DeepSeekBenchmarkConfig(
        experiment_only=True,
        baseline_recognizer=args.baseline,
        run_baseline=not args.skip_baseline,
        run_deepseek_formula=not args.skip_deepseek_formula,
        run_deepseek_region=not args.skip_deepseek_region,
        run_deepseek_page=not args.skip_deepseek_page,
        allow_cpu=args.allow_cpu,
    )
    fake = None
    if args.fake:
        # 最小假输出：带编号公式，便于测 extractor + page cache
        md_page = (
            "$$E[(y-\\hat{f})^2]=Bias^2+Var+\\varepsilon$$\n(1)\n"
            "$$Recall=\\frac{TP}{TP+FN}$$\n(4)\n"
            "$$F1=2\\times\\frac{Precision\\times Recall}{Precision+Recall}$$\n(5)\n"
            "$$TPR=\\frac{TP}{TP+FN}$$\n(6)\n"
            "$$FPR=\\frac{FP}{FP+TN}$$\n(7)\n"
        )
        fake = FakeDeepSeekOCR2Recognizer(
            {
                "formula": "$$Recall=\\frac{TP}{TP+FN}$$ (4)",
                "region": "Recall can be calculated:\n$$Recall=\\frac{TP}{TP+FN}$$\n(4)",
                "page": md_page,
                "*": md_page,
            }
        )

    def progress(msg: str) -> None:
        print(msg, flush=True)

    payload = run_deepseek_benchmark(
        args.pdf,
        cfg=cfg,
        doc_recognizer=fake,
        progress=progress,
        out_path=Path(args.out) if args.out else None,
    )
    print("wrote", payload.get("output_path"))
    print(json.dumps(payload.get("summary"), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
