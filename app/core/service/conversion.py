"""结构化转换服务：Qt 无关。JobRunner 主链 + Unified QA 终态。"""
from __future__ import annotations

import threading
import time
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from app.assets import AssetConfig, AssetPipeline
from app.core.domain.document import document_from_markdown
from app.core.domain.job import ConversionRequest, JobResult
from app.core.domain.quality import QualityVerdict
from app.core.pipeline.checkpoint import DOCUMENT_IR_NAME, QUALITY_REPORT_NAME
from app.core.pipeline.planner import plan_for_request
from app.core.pipeline.runner import JobRunner
from app.core.pipeline.stage import CallableStage, StageResult
from app.core.providers.parser import parse_pdf
from app.core.runtime import ResourceKind, get_runtime
from app.core.qa.engine import run_unified_qa
from app.engines.base import ConversionResult
from app.repair import RepairConfig, RepairPipeline
from app.task_model import ConvertTask
from app.utils.logger import new_run_id, write_task_log
from app.utils.paths import experiment_doc_dir, task_output_dir

ProgressFn = Callable[[str], None]


@dataclass(frozen=True)
class ConversionOptions:
    output_root: Path
    per_folder: bool = True
    ocr_mode: str = "auto"
    keep_images: bool = True
    keep_tables: bool = True
    keep_formulas: bool = True
    formula_recovery_preset: str = "balanced"
    deepseek_limited_production: bool = False
    images_scale: float = 2.0
    image_path_mode: str = "relative"
    export_md: bool = True
    export_raw_md: bool = False
    export_repair_json: bool = False
    export_conversion_log: bool = False
    export_manifest: bool = False
    export_formula_qa: bool = False
    export_timings: bool = False
    docling_formula_enrich: bool = field(init=False)
    repair_keep_formulas: bool = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "keep_images", True)
        mode = self.image_path_mode if self.image_path_mode in ("relative", "absolute") else "relative"
        object.__setattr__(self, "image_path_mode", mode)
        object.__setattr__(self, "docling_formula_enrich", bool(self.keep_formulas))
        object.__setattr__(
            self,
            "repair_keep_formulas",
            bool(self.deepseek_limited_production or self.keep_formulas),
        )

    def parse_keep_formulas(self) -> bool:
        if self.deepseek_limited_production:
            return True
        return self.docling_formula_enrich

    def worker_kwargs(self) -> dict[str, Any]:
        return {
            "output_root": self.output_root,
            "per_folder": self.per_folder,
            "ocr_mode": self.ocr_mode,
            "keep_images": True,
            "keep_tables": self.keep_tables,
            "keep_formulas": self.keep_formulas,
            "formula_recovery_preset": self.formula_recovery_preset,
            "deepseek_limited_production": self.deepseek_limited_production,
            "images_scale": self.images_scale,
            "image_path_mode": self.image_path_mode,
            "export_md": self.export_md,
            "export_raw_md": self.export_raw_md,
            "export_repair_json": self.export_repair_json,
            "export_conversion_log": self.export_conversion_log,
            "export_manifest": self.export_manifest,
            "export_formula_qa": self.export_formula_qa,
            "export_timings": self.export_timings,
        }


class ConversionService:
    def __init__(self, options: ConversionOptions) -> None:
        self.options = options
        self._cancel = threading.Event()
        self._repair = RepairPipeline(
            RepairConfig(
                enabled=True,
                mode="safe",
                keep_formulas=options.repair_keep_formulas,
                formula_recovery_preset=options.formula_recovery_preset,
                deepseek_limited_production=options.deepseek_limited_production,
                fix_bold=True,
                write_raw_md=options.export_raw_md,
                write_repair_json=options.export_repair_json,
                write_final_md=options.export_md,
                use_geometry=True,
            )
        )

    def request_cancel(self) -> None:
        self._cancel.set()

    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def parse_keep_formulas(self) -> bool:
        return self.options.parse_keep_formulas()

    def prepare_batch_client(self):
        if not self.options.deepseek_limited_production:
            return None
        try:
            from app.ocr.deepseek_worker_client import get_deepseek_worker_client

            return get_deepseek_worker_client()
        except Exception:
            return None

    def run_task(
        self,
        task: ConvertTask,
        *,
        progress: ProgressFn | None = None,
        batch_idx: int = 0,
        batch_id: str = "",
        batch_client=None,
        run_id: str = "",
    ) -> JobResult:
        emit = progress or (lambda _m: None)
        out_dir = task_output_dir(self.options.output_root, task.pdf_path, self.options.per_folder)
        out_dir.mkdir(parents=True, exist_ok=True)
        request = ConversionRequest(
            source_path=task.pdf_path,
            output_dir=out_dir,
            workflow=getattr(task, "workflow", None) or "快速自动",
            engine=task.engine,
            extra={"options": self.options.to_dict()},
        )
        plan = plan_for_request(request)
        ctx: dict[str, Any] = {
            "task": task,
            "out_dir": out_dir,
            "progress": emit,
            "timings": {"batch_id": batch_id or new_run_id()},
            "t0": time.time(),
            "run_id": run_id or new_run_id(),
            "warmup_thread": None,
            "batch_idx": batch_idx,
            "batch_client": batch_client,
            "docling_span": None,
            "parsed": None,
            "repaired": None,
            "images_dir": None,
            "metrics": {},
            "runtime": get_runtime(),
            "resource_kinds": (ResourceKind.GPU, ResourceKind.CPU),
        }
        stages = [
            CallableStage("parse", self._stage_parse),
            CallableStage("assets", self._stage_assets),
            CallableStage("formula_warmup", self._stage_formula_warmup),
            CallableStage("repair", self._stage_repair),
            CallableStage("qa", self._stage_qa),
            CallableStage("recover", self._stage_recover),
            CallableStage("export", self._stage_export),
        ]
        return JobRunner().run(
            request,
            stages,
            plan=plan,
            cancelled=self.cancelled,
            log=emit,
            context=ctx,
        )

    def _stage_parse(self, ctx: dict[str, Any]) -> StageResult:
        task: ConvertTask = ctx["task"]
        out_dir: Path = ctx["out_dir"]
        progress: ProgressFn = ctx["progress"]
        timings: dict[str, Any] = ctx["timings"]
        opt = self.options
        batch_client = ctx.get("batch_client")
        if opt.deepseek_limited_production and batch_client is not None:
            try:
                if int(ctx.get("batch_idx") or 0) > 0:
                    from app.ocr.deepseek_worker_client import prepare_document_worker_session

                    prepare_document_worker_session(batch_client)
                h = batch_client.health()
                model_state = str(h.get("model_state") or "")
                model_ready = bool(h.get("model_loaded")) and model_state == "MODEL_READY"
                if model_ready:
                    progress("DeepSeek：模型已暖机，跳过重复加载")
                else:
                    progress("DeepSeek：并行预热 Worker（与 Docling 重叠）…")
                    ctx["warmup_thread"] = batch_client.warmup_async()
            except Exception as e:
                progress(f"DeepSeek 预热跳过：{e}")

        t_doc = time.time()
        parsed = parse_pdf(
            engine=task.engine,
            pdf_path=task.pdf_path,
            out_dir=out_dir,
            ocr_mode=opt.ocr_mode,
            keep_images=opt.keep_images,
            keep_tables=opt.keep_tables,
            keep_formulas=opt.parse_keep_formulas(),
            images_scale=opt.images_scale,
            image_path_mode=opt.image_path_mode,
            progress=progress,
        )
        timings["docling"] = round(time.time() - t_doc, 3)
        ctx["docling_span"] = (t_doc, time.time())
        ctx["parsed"] = parsed
        if isinstance(getattr(parsed, "metadata", None), dict):
            dmeta = parsed.metadata.get("docling") or {}
            if dmeta:
                timings["docling_detail"] = dmeta
                progress(
                    f"Docling 遥测：reused={dmeta.get('converter_reused')} "
                    f"create={dmeta.get('converter_create_count')} "
                    f"init={dmeta.get('docling_init_seconds')}s "
                    f"convert={dmeta.get('docling_convert_seconds')}s "
                    f"export={dmeta.get('docling_export_seconds')}s"
                )
        progress(f"解析器：{parsed.parser} → {parsed.markdown_path.name}")
        self._stamp_warmup_overlap(ctx)
        return StageResult(name="parse", status="ok", provenance={"parser": parsed.parser})

    def _stamp_warmup_overlap(self, ctx: dict[str, Any]) -> None:
        warmup_thread = ctx.get("warmup_thread")
        docling_span = ctx.get("docling_span")
        timings = ctx["timings"]
        if warmup_thread is None:
            return
        try:
            from app.ocr.deepseek_worker_client import get_deepseek_worker_client

            client = get_deepseek_worker_client()
            if not warmup_thread.is_alive() and docling_span:
                ds, de = docling_span
                rt = client.run_timings
                ls, lf = rt.load_started_at, rt.load_finished_at
                if ls and lf and rt.model_load_seconds > 0.05:
                    lo = max(ls, ds)
                    hi = min(lf, de)
                    overlap = max(0.0, hi - lo)
                    client.run_timings.load_overlap_seconds = overlap
                    client.run_timings.blocking_load_seconds = max(
                        0.0, rt.model_load_seconds - overlap
                    )
                timings["deepseek_load"] = float(rt.model_load_seconds or 0)
                timings["deepseek_load_overlap"] = float(rt.load_overlap_seconds or 0)
                timings["deepseek_blocking_load"] = float(rt.blocking_load_seconds or 0)
                timings["deepseek_current_run"] = rt.to_dict()
                timings["deepseek_worker_lifetime"] = client.worker_lifetime.to_dict()
        except Exception:
            pass

    def _stage_assets(self, ctx: dict[str, Any]) -> StageResult:
        parsed: ConversionResult = ctx["parsed"]
        task: ConvertTask = ctx["task"]
        out_dir: Path = ctx["out_dir"]
        progress: ProgressFn = ctx["progress"]
        timings = ctx["timings"]
        images_dir = parsed.artifacts_dir or (out_dir / "images")
        if not images_dir.exists():
            images_dir = out_dir / "images"
        ctx["images_dir"] = images_dir
        t_asset = time.time()
        asset_result = AssetPipeline(
            AssetConfig(
                enabled=True,
                enable_subfigure_split=True,
                image_path_mode=self.options.image_path_mode,
                write_manifest=self.options.export_manifest,
                cleanup_parser_files=True,
            )
        ).run(
            pdf_path=task.pdf_path,
            markdown_path=parsed.markdown_path,
            images_dir=images_dir,
            parser_source=parsed.parser,
            progress=progress,
        )
        timings["asset"] = round(time.time() - t_asset, 3)
        for w in asset_result.warnings[:8]:
            progress(f"Asset 提示：{w}")
        return StageResult(name="assets", status="ok", warnings=list(asset_result.warnings[:8]))

    def _stage_formula_warmup(self, ctx: dict[str, Any]) -> StageResult:
        if not self.options.deepseek_limited_production:
            return StageResult(name="formula_warmup", status="skipped")
        parsed: ConversionResult = ctx["parsed"]
        task: ConvertTask = ctx["task"]
        progress: ProgressFn = ctx["progress"]
        timings = ctx["timings"]
        warmup_thread = ctx.get("warmup_thread")
        needs_ensure = False
        try:
            from app.formula.deepseek_preflight import (
                document_has_deepseek_recovery_work,
                should_ensure_deepseek_before_repair,
            )
            from app.ocr.deepseek_batch_warmup import zero_deepseek_document_timings

            raw_text = parsed.markdown_path.read_text(encoding="utf-8")
            needs_ensure = should_ensure_deepseek_before_repair(
                raw_text,
                task.pdf_path,
                warmup_in_flight=warmup_thread is not None,
            )
            has_recovery = document_has_deepseek_recovery_work(raw_text, task.pdf_path)
            if not needs_ensure:
                zero_deepseek_document_timings(timings, needs_deepseek=has_recovery)
                progress("DeepSeek：本文无需批前加载（无公式恢复任务）")
        except Exception as e:
            needs_ensure = True
            progress(f"DeepSeek 预检异常（保守阻塞）：{e}")
        if needs_ensure:
            try:
                from app.ocr.deepseek_batch_warmup import ensure_deepseek_before_repair
                from app.ocr.deepseek_worker_client import get_deepseek_worker_client

                client = get_deepseek_worker_client()
                ensure_deepseek_before_repair(
                    client=client,
                    warmup_thread=warmup_thread,
                    docling_span=ctx.get("docling_span"),
                    timings=timings,
                    progress=progress,
                )
            except Exception as e:
                progress(f"DeepSeek 批前加载跳过：{e}")
        return StageResult(name="formula_warmup", status="ok")

    def _stage_repair(self, ctx: dict[str, Any]) -> StageResult:
        parsed: ConversionResult = ctx["parsed"]
        task: ConvertTask = ctx["task"]
        out_dir: Path = ctx["out_dir"]
        progress: ProgressFn = ctx["progress"]
        timings = ctx["timings"]
        t_repair = time.time()
        repaired = self._repair.run(
            pdf_path=task.pdf_path,
            raw_markdown_path=parsed.markdown_path,
            out_dir=out_dir,
            progress=progress,
        )
        timings["repair_total"] = round(time.time() - t_repair, 3)
        ctx["repaired"] = repaired
        ctx["markdown_path"] = repaired.markdown_path
        try:
            qa_path = out_dir / f"{task.pdf_path.stem}.formula_qa.json"
            if qa_path.is_file():
                import json as _json

                qa = _json.loads(qa_path.read_text(encoding="utf-8"))
                sm = (qa.get("deepseek_shadow") or {}).get("summary") or {}
                cb = sm.get("cost_breakdown") or {}
                if cb:
                    timings["recovery_cost_breakdown"] = cb
                if sm.get("ocr_inference_seconds") is not None:
                    timings["ocr_inference_seconds"] = sm.get("ocr_inference_seconds")
                if sm.get("cold_start_seconds") is not None:
                    timings["recovery_cold_start_seconds"] = sm.get("cold_start_seconds")
                if sm.get("document_recovery_profile"):
                    timings["document_recovery_profile"] = sm.get("document_recovery_profile")
                if sm.get("ocr_calls") is not None:
                    timings["recovery"] = {
                        "attempted": sm.get("attempted", sm.get("ocr_calls")),
                        "accepted": sm.get("accepted"),
                        "rejected": sm.get("rejected"),
                        "accept_rate": sm.get("accept_rate"),
                        "seconds_per_accept": sm.get("seconds_per_accept"),
                        "cost_per_recovered_formula": sm.get("cost_per_recovered_formula"),
                        "profile": ((sm.get("document_recovery_profile") or {}).get("profile")),
                    }
        except Exception:
            pass
        timings["total"] = round(time.time() - ctx["t0"], 3)
        from app.ocr.deepseek_batch_warmup import deepseek_critical_path_seconds

        cold_batch = deepseek_critical_path_seconds(timings)
        if cold_batch <= 0.0:
            cold_batch = float(
                timings.get("model_cold_start") or timings.get("deepseek_blocking_load") or 0.0
            )
        timings["deepseek_critical_path_seconds"] = round(cold_batch, 3)
        timings["batch_cold_start_seconds"] = round(cold_batch, 3)
        timings["batch_steady_state_seconds"] = round(
            max(0.0, float(timings.get("total") or 0.0) - cold_batch), 3
        )
        warmup_thread = ctx.get("warmup_thread")
        if warmup_thread is not None and ctx.get("docling_span"):
            try:
                from app.ocr.deepseek_batch_warmup import finalize_deepseek_timings_after_repair
                from app.ocr.deepseek_worker_client import get_deepseek_worker_client

                client = get_deepseek_worker_client()
                finalize_deepseek_timings_after_repair(
                    timings=timings,
                    warmup_thread=warmup_thread,
                    docling_span=ctx.get("docling_span"),
                    client=client,
                )
            except Exception:
                pass
        if repaired.report_path and repaired.report_path.exists():
            try:
                import json

                data = json.loads(repaired.report_path.read_text(encoding="utf-8"))
                data["parser"] = parsed.parser
                data["run_id"] = ctx["run_id"]
                data["timings"] = timings
                repaired.report_path.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception:
                pass
        return StageResult(name="repair", status="ok")

    def _stage_qa(self, ctx: dict[str, Any]) -> StageResult:
        parsed: ConversionResult = ctx["parsed"]
        repaired = ctx["repaired"]
        task: ConvertTask = ctx["task"]
        timings = ctx["timings"]
        md_path = repaired.markdown_path if getattr(repaired, "markdown_path", None) else None
        md_text = ""
        if md_path is not None and Path(md_path).is_file():
            md_text = Path(md_path).read_text(encoding="utf-8")
        document = document_from_markdown(
            md_text,
            source=str(task.pdf_path),
            provider=parsed.parser,
            page_count=parsed.pages,
        )
        from app.core.repair.ir import apply_ir_rules

        document, _ir_traces = apply_ir_rules(document)
        quality = run_unified_qa(
            md_text,
            document=document,
            page_count=parsed.pages,
            context={"recovery": timings.get("recovery") or {}, "retries": timings.get("retries")},
        )
        ctx["quality"] = quality
        ctx["document"] = document
        ctx["document_ir_name"] = DOCUMENT_IR_NAME
        ctx["quality_report_name"] = QUALITY_REPORT_NAME
        if quality.status == QualityVerdict.FAILED.value:
            return StageResult(
                name="qa",
                status="failed",
                retryable=False,
                error="unified_qa_failed",
                artifacts={"status": quality.status},
            )
        return StageResult(
            name="qa",
            status="ok",
            artifacts={"status": quality.status},
            warnings=list(quality.warnings),
        )

    def _stage_recover(self, ctx: dict[str, Any]) -> StageResult:
        from app.core.routing.recovery import run_recovery

        quality = ctx.get("quality")
        document = ctx.get("document")
        md_path = ctx.get("markdown_path")
        if quality is None or document is None:
            return StageResult(name="recover", status="skipped")
        md_text = ""
        if md_path is not None and Path(md_path).is_file():
            md_text = Path(md_path).read_text(encoding="utf-8")
        parsed = ctx.get("parsed")
        page_count = getattr(parsed, "pages", None) if parsed is not None else None
        outcome = run_recovery(
            quality=quality,
            document=document,
            markdown=md_text,
            page_count=page_count,
            executors=ctx.get("recovery_executors"),
            cancelled=self.cancelled,
        )
        ctx["recovery_requests"] = [req.to_dict() for req in outcome.requests]
        ctx["document"] = outcome.document
        ctx["quality"] = outcome.quality
        if outcome.changed and md_path is not None:
            Path(md_path).write_text(outcome.markdown, encoding="utf-8")
        if outcome.quality is not None and outcome.quality.status == QualityVerdict.FAILED.value:
            return StageResult(
                name="recover",
                status="failed",
                retryable=False,
                error="unified_qa_failed_after_recover",
                metrics={"recovery_requests": len(outcome.requests), "changed": outcome.changed},
            )
        status = "ok" if outcome.requests else "skipped"
        return StageResult(
            name="recover",
            status=status,
            warnings=list(getattr(outcome.quality, "warnings", None) or []),
            metrics={
                "recovery_requests": len(outcome.requests),
                "changed": outcome.changed,
                "resolved": sum(1 for r in outcome.requests if r.status == "resolved"),
                "skipped": sum(1 for r in outcome.requests if r.status == "skipped"),
            },
        )

    def _stage_export(self, ctx: dict[str, Any]) -> StageResult:
        task: ConvertTask = ctx["task"]
        out_dir: Path = ctx["out_dir"]
        timings = ctx["timings"]
        self._mirror_experiment_artifacts(
            stem=task.pdf_path.stem,
            out_dir=out_dir,
            run_id=str(ctx["run_id"]),
            timings=timings,
            pdf_path=task.pdf_path,
        )
        if self.options.export_conversion_log:
            write_task_log(
                out_dir,
                f"OK components md={self.options.export_md} raw={self.options.export_raw_md} "
                f"json={self.options.export_repair_json} log={self.options.export_conversion_log} "
                f"manifest={self.options.export_manifest} qa={self.options.export_formula_qa} "
                f"timings={self.options.export_timings} run_id={ctx['run_id']} "
                f"timings_data={timings}",
                run_id=str(ctx["run_id"]),
            )
        self._cleanup_optional_exports(out_dir, ctx.get("images_dir"))
        ctx["metrics"] = {"elapsed": round(time.time() - ctx["t0"], 3), "timings": timings}
        return StageResult(name="export", status="ok")

    def _cleanup_optional_exports(self, out_dir: Path, images_dir: Path | None) -> None:
        def _unlink(path: Path) -> None:
            try:
                if path.is_file():
                    path.unlink()
            except OSError:
                pass

        if not self.options.export_conversion_log:
            _unlink(out_dir / "conversion.log")
            for p in out_dir.glob("conversion_*.log"):
                _unlink(p)
        if not self.options.export_manifest:
            for base in (images_dir, out_dir / "images"):
                if base is None:
                    continue
                _unlink(Path(base) / "manifest.json")
        if not self.options.export_formula_qa:
            for p in out_dir.glob("*.formula_qa.json"):
                _unlink(p)
        if not self.options.export_timings:
            for p in out_dir.glob("timings_*.json"):
                _unlink(p)

    def _mirror_experiment_artifacts(
        self,
        *,
        stem: str,
        out_dir: Path,
        run_id: str,
        timings: dict[str, Any],
        pdf_path: Path,
    ) -> None:
        import json
        import shutil

        exp = experiment_doc_dir(stem)
        payload = {"run_id": run_id, "batch_id": timings.get("batch_id") or "", "timings": timings, "pdf": str(pdf_path)}
        try:
            (exp / f"timings_{run_id}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            pass
        src_qa = out_dir / f"{stem}.formula_qa.json"
        if src_qa.is_file():
            try:
                shutil.copy2(src_qa, exp / src_qa.name)
            except OSError:
                pass
        if self.options.export_timings:
            try:
                (out_dir / f"timings_{run_id}.json").write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            except OSError:
                pass


def format_task_error(exc: BaseException) -> str:
    return f"{exc}\n{traceback.format_exc()}"
