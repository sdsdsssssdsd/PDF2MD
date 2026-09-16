"""Qt 无关的 JobRunner：顺序执行 Stage，支持取消与 checkpoint。"""
from __future__ import annotations

from typing import Any, Callable, Iterable

from app.core.domain.document import DocumentIR
from app.core.domain.job import ConversionRequest, Job, JobResult, PipelinePlan
from app.core.domain.quality import pipeline_failure_report
from app.core.pipeline.checkpoint import RunManifest, write_run_sidecar
from app.core.pipeline.stage import Stage, StageResult
from app.core.runtime import ResourceBusy, ResourceCancelled, get_runtime, isolate_call

LogFn = Callable[[str], None]
CancelFn = Callable[[], bool]


class JobRunner:
    def run(
        self,
        request: ConversionRequest,
        stages: Iterable[Stage],
        *,
        plan: PipelinePlan | None = None,
        cancelled: CancelFn | None = None,
        log: LogFn | None = None,
        context: dict[str, Any] | None = None,
    ) -> JobResult:
        emit = log or (lambda _m: None)
        job = Job.create(request, plan or PipelinePlan(profile=request.workflow))
        job.status = "running"
        ctx: dict[str, Any] = dict(context or {})
        ctx["request"] = request
        ctx["job"] = job
        ctx["plan"] = job.plan
        results: list[StageResult] = []
        manifest = RunManifest.for_job(job)
        try:
            manifest.save(request.output_dir)
        except OSError:
            pass
        runtime = ctx.get("runtime") or get_runtime()
        ctx["runtime"] = runtime

        def finish(*, ok: bool, error: str = "") -> JobResult:
            self._persist_sidecar(job=job, request=request, ctx=ctx, results=results)
            md = ctx.get("markdown_path")
            quality = ctx.get("quality")
            return JobResult(
                job=job,
                ok=ok,
                markdown_path=md,
                output_dir=request.output_dir,
                error=error,
                stage_results=results,
                metrics=dict(ctx.get("metrics") or {}),
                quality=quality,
            )

        kinds = tuple(ctx.get("resource_kinds") or ())
        try:
            with runtime.job_scope(job.id, kinds=kinds, cancelled=cancelled) as bag:
                ctx["resources"] = bag
                if cancelled and cancelled():
                    job.status = "cancelled"
                    emit("[job] 取消于 start")
                    return finish(ok=False, error="cancelled")

                for stage in stages:
                    if cancelled and cancelled():
                        job.status = "cancelled"
                        emit(f"[job] 取消于 {getattr(stage, 'name', stage)}")
                        return finish(ok=False, error="cancelled")
                    name = getattr(stage, "name", type(stage).__name__)
                    emit(f"[job] stage {name}")
                    isolated = isolate_call(stage.execute, ctx)
                    if isolated.ok:
                        result = isolated.value
                        if not isinstance(result, StageResult):
                            result = StageResult(
                                name=name,
                                status="failed",
                                retryable=True,
                                error="invalid_stage_result",
                            )
                    else:
                        result = StageResult(
                            name=name,
                            status="failed",
                            retryable=True,
                            error=isolated.error,
                        )
                    results.append(result)
                    manifest.record_stage(result)
                    try:
                        manifest.save(request.output_dir)
                    except OSError:
                        pass
                    if not result.ok:
                        job.status = "failed"
                        job.error = result.error or f"{name} failed"
                        emit(f"[job] {name} 失败：{job.error}")
                        return finish(ok=False, error=job.error)

                job.status = "done"
                return finish(ok=True)
        except ResourceCancelled:
            job.status = "cancelled"
            emit("[job] 取消于资源等待")
            return finish(ok=False, error="cancelled")
        except ResourceBusy as exc:
            job.status = "failed"
            job.error = str(exc)
            emit(f"[job] 资源繁忙：{job.error}")
            return finish(ok=False, error=job.error)

    def _persist_sidecar(
        self,
        *,
        job: Job,
        request: ConversionRequest,
        ctx: dict[str, Any],
        results: list[StageResult],
    ) -> None:
        md = ctx.get("markdown_path")
        if md is not None:
            job.markdown_path = str(md)
        document = ctx.get("document")
        quality = ctx.get("quality")
        failed = job.status in {"failed", "cancelled"}
        if failed and document is None:
            document = DocumentIR(source=str(request.source_path))
            ctx["document"] = document
        if failed and quality is None:
            quality = pipeline_failure_report(job.error, cancelled=job.status == "cancelled")
            ctx["quality"] = quality
        if job.status != "cancelled" and quality is not None:
            job.status = getattr(quality, "status", None) or job.status
        parsed = ctx.get("parsed")
        parser = job.plan.parser
        if parsed is not None:
            parser = getattr(parsed, "parser", parser) or parser
        stages = [
            {
                "name": r.name,
                "status": r.status,
                "retryable": r.retryable,
                "error": r.error,
                "warnings": list(r.warnings),
                "metrics": dict(r.metrics),
            }
            for r in results
        ]
        try:
            write_run_sidecar(
                request.output_dir,
                workflow=job.request.workflow,
                profile=job.plan.profile,
                parser=parser,
                source=str(job.request.source_path),
                markdown_path=job.markdown_path,
                status=job.status,
                plan=job.plan.to_dict(),
                document=document,
                quality=quality,
                stages=stages,
                job_id=job.id,
            )
        except OSError:
            pass
