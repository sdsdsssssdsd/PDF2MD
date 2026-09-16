"""R8：Provider Registry + Capability Model。"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.core.providers.descriptor import (
    Capability,
    ProviderDescriptor,
    ProviderType,
    ResolveConstraints,
    RuntimeKind,
)
from app.core.providers.registry import (
    ENTRY_POINT_GROUP,
    ProviderRegistry,
    discover,
    get_registry,
    reset_registry_for_tests,
)
from app.core.routing.profiler import DocumentProfile
from app.core.routing.router import suggest_parser, suggest_recovery
from app.task_model import EngineChoice


@pytest.fixture
def isolated_registry():
    reset_registry_for_tests()
    try:
        yield get_registry()
    finally:
        reset_registry_for_tests()


def test_internal_catalog_and_four_states(isolated_registry: ProviderRegistry):
    marker = isolated_registry.status("parser.marker")
    assert marker is not None
    assert marker.installed is True
    assert marker.enabled is False
    assert marker.descriptor.experimental is True
    assert marker.descriptor.source == "incubator"
    assert marker.descriptor.track == "experimental"
    pp = isolated_registry.status("table.pp_structure")
    assert pp is not None
    assert pp.enabled is False
    assert pp.descriptor.experimental is True
    vlm = isolated_registry.status("vision.docling_vlm")
    assert vlm is not None
    assert vlm.enabled is False
    docling = isolated_registry.status("parser.docling")
    assert docling is not None
    assert docling.installed is True
    assert docling.enabled is True
    snapshot = discover()
    assert "parser.marker" in snapshot
    assert "parser.docling" in snapshot
    assert "table.pp_structure" in snapshot
    assert "vision.docling_vlm" in snapshot
    assert "formula.deepseek_ocr2" in snapshot
    assert "vision.deepseek_api" in snapshot
    assert "vision.deepseek_web" in snapshot


def test_resolve_skips_disabled_experimental_and_unavailable():
    registry = ProviderRegistry()
    registry.register(
        ProviderDescriptor(
            id="table.good",
            version="1.0",
            provider_type=ProviderType.TABLE,
            capabilities=(Capability.TABLE_STRUCTURE,),
            default_enabled=True,
        ),
        available_fn=lambda: True,
    )
    registry.register(
        ProviderDescriptor(
            id="table.plugin",
            version="1.0",
            provider_type=ProviderType.TABLE,
            capabilities=(Capability.TABLE_STRUCTURE,),
            experimental=True,
            default_enabled=False,
            source="entry_point",
        ),
        available_fn=lambda: True,
        enabled=False,
    )
    registry.register(
        ProviderDescriptor(
            id="table.down",
            version="1.0",
            provider_type=ProviderType.TABLE,
            capabilities=(Capability.TABLE_STRUCTURE,),
        ),
        available_fn=lambda: False,
    )
    hit = registry.resolve(Capability.TABLE_STRUCTURE)
    assert hit is not None
    assert hit.id == "table.good"
    assert registry.resolve(
        Capability.TABLE_STRUCTURE,
        ResolveConstraints(capability=Capability.TABLE_STRUCTURE, require_enabled=False),
    ).id == "table.good"
    registry.set_enabled("table.plugin", True)
    still = registry.resolve(Capability.TABLE_STRUCTURE)
    assert still.id == "table.good"
    experimental = registry.resolve(
        Capability.TABLE_STRUCTURE,
        ResolveConstraints(
            capability=Capability.TABLE_STRUCTURE,
            allow_experimental=True,
            preferred_ids=("table.plugin",),
        ),
    )
    assert experimental.id == "table.plugin"


def test_new_provider_does_not_require_router_edit(isolated_registry: ProviderRegistry):
    isolated_registry.register(
        ProviderDescriptor(
            id="table.pp_structure",
            version="0.1",
            provider_type=ProviderType.TABLE,
            capabilities=(Capability.TABLE_STRUCTURE,),
            runtime=(RuntimeKind.CPU,),
        ),
        available_fn=lambda: True,
    )
    recovery = suggest_recovery(DocumentProfile(table_density=0.4, formula_density=0.0))
    assert recovery["table"] == "specialist"
    assert recovery["table_provider"] == "table.pp_structure"
    assert recovery["formula_provider"] in {None, "formula.deepseek_ocr2"}


def test_auto_parser_uses_registry_not_hardcoded_fallback(isolated_registry: ProviderRegistry):
    isolated_registry.set_enabled("parser.mineru", False)
    name = suggest_parser(
        engine="自动",
        profile=DocumentProfile(scan_ratio=0.95, page_count=3),
    )
    assert name == "docling"
    assert suggest_parser(engine=EngineChoice.MINERU.value) == "mineru"
    assert suggest_parser(engine=EngineChoice.DOCLING.value) == "docling"


def test_entry_points_discovered_but_not_loaded(monkeypatch, isolated_registry: ProviderRegistry):
    loaded = {"n": 0}

    class _EP:
        name = "evil"

        def load(self):
            loaded["n"] += 1
            raise AssertionError("third-party providers must stay unloaded")

    monkeypatch.setattr(
        "app.core.providers.registry._iter_entry_points",
        lambda: [_EP()],
    )
    reset_registry_for_tests()
    registry = get_registry()
    status = registry.status("plugin.evil")
    assert status is not None
    assert status.enabled is False
    assert status.descriptor.source == "entry_point"
    assert loaded["n"] == 0
    assert registry.load_entry_points() == []
    assert loaded["n"] == 0
    assert ENTRY_POINT_GROUP == "pdf2md.providers"


def test_router_source_asks_registry_not_paddle():
    text = Path("app/core/routing/router.py").read_text(encoding="utf-8")
    tree = ast.parse(text)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert "app.core.providers.registry" in imported
    assert "app.core.providers.descriptor" in imported
    for forbidden in ("paddle", "paddleocr", "marker", "app.engines"):
        assert not any(name == forbidden or name.startswith(forbidden + ".") for name in imported)
    assert "if paddle" not in text
    assert "registry.resolve(" in text
    assert "get_registry()" in text
