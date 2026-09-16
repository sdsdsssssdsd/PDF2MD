"""R12 Incubator + 晋级门；顺带 R14 规则幂等、R15 doctor。"""
from __future__ import annotations

import ast
import json
from pathlib import Path

from app.core.__main__ import main as core_main
from app.core.benchmark.report import BenchmarkReport
from app.core.benchmark.delta import compare_reports
from app.core.domain.job import ConversionRequest
from app.core.domain.recovery import RecoveryRequest, RecoveryScope
from app.core.pipeline.planner import plan_for_request
from app.core.providers.builtins import MARKER, PP_STRUCTURE
from app.core.providers.descriptor import Capability
from app.core.providers.incubator import INCUBATOR_EXECUTE_ENV, incubator_execute_allowed
from app.core.providers.promotion import (
    GATES,
    PromotionTrack,
    evaluate_promotion,
)
from app.core.providers.registry import get_registry, reset_registry_for_tests
from app.core.repair import apply_markdown_rules, iter_rules, rule_is_idempotent
from app.core.routing.recovery import resolve_recovery
from app.core.routing.router import suggest_parser
from app.task_model import EngineChoice


def _imported(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_incubator_is_registered_but_not_default():
    reset_registry_for_tests()
    try:
        registry = get_registry()
        for pid in ("table.pp_structure", "vision.docling_vlm", "parser.marker"):
            status = registry.status(pid)
            assert status is not None
            assert status.enabled is False
            assert status.descriptor.experimental is True
            assert status.descriptor.track == PromotionTrack.EXPERIMENTAL
            assert status.descriptor.source == "incubator"
        assert suggest_parser(engine="自动") == "docling"
        plan = plan_for_request(
            ConversionRequest(source_path=Path("dummy.pdf"), output_dir=Path("."), workflow="快速自动")
        )
        assert plan.parser == "docling"
        assert plan.recovery.get("table_provider") != "table.pp_structure"
    finally:
        reset_registry_for_tests()


def test_enabled_pp_structure_is_table_specialist_not_parser():
    reset_registry_for_tests()
    try:
        registry = get_registry()
        registry.register(PP_STRUCTURE, enabled=True, available_fn=lambda: True)
        req = RecoveryRequest(
            id="r1",
            scope=RecoveryScope.PAGE,
            page=15,
            required_capability=Capability.TABLE_STRUCTURE,
            problem_type="table_structure",
        )
        handle = resolve_recovery(req)
        assert handle is not None
        assert handle.id == "table.pp_structure"
        assert Capability.TABLE_STRUCTURE in handle.descriptor.capabilities
        assert suggest_parser(engine=EngineChoice.AUTO.value) == "docling"
        assert handle.short_name != "docling"
    finally:
        reset_registry_for_tests()


def test_promotion_requires_all_gates_not_just_benchmark():
    all_ok = {name: True for name in GATES}
    half = {name: True for name in GATES}
    half["stability"] = False
    to_candidate = evaluate_promotion(PP_STRUCTURE, target=PromotionTrack.CANDIDATE, gates=half)
    assert to_candidate.allowed is False
    assert "gate:stability" in to_candidate.reasons
    good = evaluate_promotion(PP_STRUCTURE, target=PromotionTrack.CANDIDATE, gates=all_ok)
    assert good.allowed is True
    delta = compare_reports(
        BenchmarkReport(cases=6, passed=6, slices={"overall": 1.0}),
        BenchmarkReport(cases=6, passed=6, slices={"overall": 1.0}),
    )
    blocked = evaluate_promotion(
        MARKER,
        target=PromotionTrack.DEFAULT_ELIGIBLE,
        gates=all_ok,
        benchmark_allowed=delta.allowed,
    )
    assert blocked.allowed is False
    assert "license_not_default_eligible" in blocked.reasons
    assert "still_experimental" in blocked.reasons


def test_incubator_execute_off_by_default(monkeypatch):
    monkeypatch.delenv(INCUBATOR_EXECUTE_ENV, raising=False)
    assert incubator_execute_allowed() is False
    from app.core.providers.incubator import PPStructureTableProvider

    assert PPStructureTableProvider().recover_blocks(
        RecoveryRequest(
            id="x",
            scope=RecoveryScope.BLOCK,
            required_capability=Capability.TABLE_STRUCTURE,
            problem_type="table_structure",
        ),
        None,
        "",
    ) is None


def test_ui_has_no_paddle_or_marker_mode():
    text = Path("app/main_window.py").read_text(encoding="utf-8")
    assert "Paddle" not in text
    assert "PP-Structure" not in text
    assert "Marker" not in text
    imported = _imported(Path("app/main_window.py"))
    assert "app.core.providers.incubator" not in imported


def test_repair_rules_are_idempotent():
    ids = {r.id for r in iter_rules(phase="markdown")}
    assert "figure_table_separation" in ids
    assert "display_math_multiline" in ids
    assert "heading_spacing" in ids
    assert "legacy_correction" not in ids
    messy = "| a | b |\n| --- | --- |\n| 1 | 2 |\n![Fig](images/x.png)\n$$E=mc^2\\tag{1}$$\n"
    from app.core.repair import apply_markdown_rules_traced
    from app.utils.md_postprocess import postprocess_markdown

    once = apply_markdown_rules(messy)
    twice = apply_markdown_rules(once)
    assert once == twice
    assert "\n\n![" in once or "\n\n$$" in once
    _out, traces = apply_markdown_rules_traced(messy)
    assert {t.rule_id for t in traces} == ids
    piped = postprocess_markdown(messy, pdf_path=None, fix_bold=False, mode="safe")
    assert "\n\n![" in piped or "\n\n$$" in piped
    for rule in iter_rules(phase="markdown"):
        assert rule.deterministic is True
        assert rule_is_idempotent(rule, messy)


def test_doctor_and_providers_cli(capsys):
    reset_registry_for_tests()
    try:
        assert core_main(["doctor"]) == 0
        doctor = json.loads(capsys.readouterr().out)
        assert doctor["schema_version"] == "1.0"
        ids = {p["id"] for p in doctor["providers"]}
        assert "parser.docling" in ids
        assert "table.pp_structure" in ids
        assert doctor["os"]
        assert "runtime" in doctor
        assert "models" in doctor
        from app.__main__ import main as package_main

        assert package_main(["doctor"]) == 0
        again = json.loads(capsys.readouterr().out)
        assert again["schema_version"] == "1.0"
        assert core_main(["providers"]) == 0
        listing = json.loads(capsys.readouterr().out)
        assert any(item["id"] == "vision.docling_vlm" for item in listing)
        vlm = next(item for item in listing if item["id"] == "vision.docling_vlm")
        assert vlm["enabled"] is False
        assert vlm["experimental"] is True
    finally:
        reset_registry_for_tests()
