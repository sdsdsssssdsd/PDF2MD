"""Providers。"""
from app.core.providers.descriptor import (
    Capability,
    ProviderDescriptor,
    ResolveConstraints,
)
from app.core.providers.registry import (
    ENTRY_POINT_GROUP,
    discover,
    get_registry,
    reset_registry_for_tests,
)

__all__ = [
    "Capability",
    "ENTRY_POINT_GROUP",
    "ProviderDescriptor",
    "ResolveConstraints",
    "discover",
    "get_registry",
    "parse_pdf",
    "reset_registry_for_tests",
]


def __getattr__(name: str):
    if name == "parse_pdf":
        from app.core.providers.parser import parse_pdf

        return parse_pdf
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
