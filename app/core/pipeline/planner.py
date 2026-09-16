"""UI Workflow → PipelinePlan。五种模式仍对外不变，内部编译成 Stage Graph。"""
from __future__ import annotations

from pathlib import Path

from app.core.domain.job import ConversionRequest, PipelinePlan
from app.core.routing.profiler import DocumentProfile, profile_source
from app.core.routing.router import suggest_parser, suggest_page_fallbacks, suggest_recovery
from app.task_model import (
    WorkflowChoice,
    is_daily_workflow,
    is_format_repair_workflow,
    is_vision_api_workflow,
    is_vision_web_workflow,
    normalize_workflow,
)


def plan_for_request(
    request: ConversionRequest,
    *,
    profile: DocumentProfile | None = None,
) -> PipelinePlan:
    workflow = normalize_workflow(request.workflow)
    doc_profile = profile
    src = Path(request.source_path)
    if doc_profile is None and src.suffix.lower() == ".pdf":
        doc_profile = profile_source(src)

    if is_daily_workflow(workflow):
        return PipelinePlan(
            profile="daily_vision",
            parser=None,
            stages=["ingest", "vision_json", "export"],
            recovery={"provider": "deepseek_api"},
        )
    if is_vision_api_workflow(workflow):
        return PipelinePlan(
            profile="pdf_vision_api",
            parser=None,
            stages=["render", "vision_api", "validate", "merge", "figures", "export"],
            recovery={"provider": "deepseek_api", "page_fallback": "extreme"},
        )
    if is_vision_web_workflow(workflow):
        return PipelinePlan(
            profile="pdf_vision_web",
            parser=None,
            stages=["render", "vision_web", "validate", "merge", "figures", "export"],
            recovery={"provider": "deepseek_web", "experimental": True},
            notes=["experimental_provider"],
        )
    if is_format_repair_workflow(workflow):
        return PipelinePlan(
            profile="format_repair",
            parser=None,
            stages=["protect", "repair", "integrity_gate", "export"],
            recovery={"integrity_gate": True},
        )

    parser = suggest_parser(src, engine=request.engine, profile=doc_profile)
    recovery = suggest_recovery(doc_profile)
    page_overrides = suggest_page_fallbacks(doc_profile)
    notes: list[str] = []
    if doc_profile and doc_profile.scan_ratio >= 0.7:
        notes.append("high_scan_ratio")
    if doc_profile and doc_profile.formula_density >= 0.3:
        notes.append("formula_dense")
    if page_overrides:
        notes.append("page_recovery")
    return PipelinePlan(
        profile="structured",
        parser=parser,
        stages=["parse", "assets", "formula_warmup", "repair", "qa", "recover", "export"],
        recovery=recovery,
        page_overrides=page_overrides,
        notes=notes,
    )


def profile_name_for_workflow(workflow: str) -> str:
    w = normalize_workflow(workflow)
    if w == WorkflowChoice.DAILY.value:
        return "daily_vision"
    if w == WorkflowChoice.VISION_API.value:
        return "pdf_vision_api"
    if w == WorkflowChoice.VISION_WEB.value:
        return "pdf_vision_web"
    if w == WorkflowChoice.FORMAT_REPAIR.value:
        return "format_repair"
    return "structured"
