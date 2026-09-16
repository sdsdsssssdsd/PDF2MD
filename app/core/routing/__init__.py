"""Routing 包。"""
from app.core.routing.profiler import DocumentProfile, PageProfile, profile_pdf, profile_source
from app.core.routing.recovery import plan_recovery, resolve_recovery, run_recovery
from app.core.routing.router import suggest_page_fallbacks, suggest_parser, suggest_recovery

__all__ = [
    "DocumentProfile",
    "PageProfile",
    "plan_recovery",
    "profile_pdf",
    "profile_source",
    "resolve_recovery",
    "run_recovery",
    "suggest_page_fallbacks",
    "suggest_parser",
    "suggest_recovery",
]
