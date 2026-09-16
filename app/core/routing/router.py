"""Page/block 级 Hybrid Router：整篇不再一刀切，异常页再走专项 Recovery。"""
from __future__ import annotations

from pathlib import Path

from app.core.providers.descriptor import Capability, ResolveConstraints
from app.core.providers.registry import get_registry
from app.core.routing.profiler import DocumentProfile, profile_source
from app.task_model import EngineChoice


def suggest_parser(
    path: Path | str | None = None,
    *,
    engine: str = "自动",
    profile: DocumentProfile | None = None,
) -> str:
    """返回内部 parser 名：docling | mineru。显式引擎优先生效。"""
    if engine == EngineChoice.MINERU.value:
        return "mineru"
    if engine == EngineChoice.DOCLING.value:
        return "docling"
    prof = profile
    if prof is None and path is not None:
        prof = profile_source(path)
    preferred = ("parser.mineru",) if (prof is not None and prof.scan_ratio >= 0.7) else ("parser.docling",)
    handle = get_registry().resolve(
        Capability.PARSE_STRUCTURE,
        ResolveConstraints(
            capability=Capability.PARSE_STRUCTURE,
            preferred_ids=preferred,
            require_available=False,
        ),
    )
    if handle is None:
        return "docling"
    return handle.short_name


def suggest_recovery(profile: DocumentProfile | None) -> dict:
    if profile is None:
        return {"formula": "on_demand", "table": "on_demand", "vision": "severe_page"}
    recovery = {
        "formula": "specialist" if profile.formula_density >= 0.25 else "on_demand",
        "table": "specialist" if profile.table_density >= 0.25 else "on_demand",
        "vision": "severe_page",
        "layout": "qa" if profile.multi_column_ratio >= 0.4 else "none",
    }
    if profile.scan_ratio >= 0.7:
        recovery["parser_reason"] = "scan_like"
    recovery.update(_capability_providers())
    return recovery


def suggest_page_fallbacks(
    profile: DocumentProfile | None,
    *,
    pages: list | None = None,
) -> dict[str, str]:
    """页 → required_capability。整篇 scan_ratio 低时也不把全篇打去 MinerU。"""
    mapping: dict[str, str] = {}
    items = pages if pages is not None else (profile.page_profiles if profile is not None else [])
    for page in items:
        number = getattr(page, "number", None)
        if number is None:
            continue
        cap = None
        if getattr(page, "scan_like", False):
            cap = Capability.VISION_PAGE
        elif getattr(page, "table_like", False):
            cap = Capability.TABLE_STRUCTURE
        elif getattr(page, "formula_like", False):
            cap = Capability.FORMULA_RECOGNITION
        if cap:
            mapping[str(int(number))] = cap
    return mapping


def _capability_providers() -> dict[str, str | None]:
    """Router 只问 capability，不按具体 backend 做可用性分支。"""
    registry = get_registry()
    formula = registry.resolve(
        Capability.FORMULA_RECOGNITION,
        ResolveConstraints(capability=Capability.FORMULA_RECOGNITION, input_kind=None),
    )
    table = registry.resolve(
        Capability.TABLE_STRUCTURE,
        ResolveConstraints(
            capability=Capability.TABLE_STRUCTURE,
            exclude_ids=("parser.docling", "parser.mineru"),
        ),
    )
    vision = registry.resolve(
        Capability.VISION_PAGE,
        ResolveConstraints(
            capability=Capability.VISION_PAGE,
            allow_experimental=True,
            input_kind=None,
        ),
    )
    return {
        "formula_provider": None if formula is None else formula.id,
        "table_provider": None if table is None else table.id,
        "vision_provider": None if vision is None else vision.id,
    }
