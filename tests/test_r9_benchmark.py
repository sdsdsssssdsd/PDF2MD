"""R9：Benchmark Platform 与生产 QA 分离。"""
from __future__ import annotations

import ast
import json
from pathlib import Path

from app.core.benchmark.adapters import olmocr, omnidocbench
from app.core.benchmark.catalog import GOLD_SUITES, load_catalog
from app.core.benchmark.delta import compare_reports, default_change_allowed
from app.core.benchmark.report import BenchmarkReport
from app.core.benchmark.runner import run_gold_suite
from app.core.__main__ import main as core_main


def _imported(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_gold_v2_catalog_covers_suites_and_is_green():
    cases = load_catalog()
    suites = {c.suite for c in cases}
    assert set(GOLD_SUITES) <= suites
    assert any("dense_formula" in c.tags for c in cases)
    assert any("scan" in c.tags for c in cases)
    assert any("complex_table" in c.tags for c in cases)
    report = run_gold_suite()
    assert report.skipped is False
    assert report.cases == len(cases)
    assert report.slices["overall"] == 1.0
    assert report.slices["dense_formula"] == 1.0
    assert report.slices["scan"] == 1.0
    assert report.metrics["quality"] == 1.0
    assert report.metrics["failure_rate"] == 0.0
    assert "table" in report.metrics
    assert "reading_order" in report.metrics


def test_default_provider_gate_requires_delta():
    good = BenchmarkReport(cases=6, passed=6, slices={"overall": 1.0, "dense_formula": 1.0})
    worse = BenchmarkReport(cases=6, passed=3, slices={"overall": 0.5, "dense_formula": 1.0})
    slice_reg = BenchmarkReport(
        cases=6, passed=6, slices={"overall": 1.0, "dense_formula": 0.9}
    )
    assert compare_reports(good, good).allowed is True
    overall = compare_reports(good, worse)
    assert overall.allowed is False
    assert overall.reason == "overall_regression"
    tagged = compare_reports(good, slice_reg)
    assert tagged.allowed is False
    assert tagged.reason.startswith("slice_regression")
    empty = BenchmarkReport(cases=0, passed=0, slices={})
    allowed, reason = default_change_allowed(compare_reports(empty, empty))
    assert allowed is False
    assert reason == "insufficient_cases"


def test_external_adapters_skip_without_dataset(monkeypatch):
    monkeypatch.delenv("PDF2MD_OMNIDOC_ROOT", raising=False)
    monkeypatch.delenv("PDF2MD_OLMOCR_ROOT", raising=False)
    assert omnidocbench.available() is False
    assert olmocr.available() is False
    omni = omnidocbench.run()
    olm = olmocr.run()
    assert omni.skipped and olm.skipped
    assert omni.extras.get("ci_policy") == "nightly_or_manual"
    assert olm.extras.get("ci_policy") == "nightly_or_manual"


def test_cli_benchmark_json(capsys, tmp_path: Path):
    out = tmp_path / "bench.json"
    rc = core_main(["benchmark", "--json", "-o", str(out)])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "1.0"
    assert payload["slices"]["overall"] == 1.0
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["cases"] == payload["cases"]
    other = tmp_path / "worse.json"
    worse = BenchmarkReport.from_dict(saved)
    worse.passed = 0
    worse.slices = {**saved["slices"], "overall": 0.0}
    worse.save(other)
    rc2 = core_main(["benchmark", "--compare", str(out), str(other), "--json"])
    assert rc2 == 2
    delta = json.loads(capsys.readouterr().out)
    assert delta["allowed"] is False


def test_production_qa_does_not_import_benchmark():
    forbidden = "app.core.benchmark"
    for rel in (
        "app/core/qa/engine.py",
        "app/core/qa/gold.py",
        "app/core/qa/checks.py",
        "app/core/routing/router.py",
        "app/core/providers/builtins.py",
        "app/core/service/conversion.py",
        "app/core/domain/document.py",
    ):
        imported = _imported(Path(rel))
        assert not any(name == forbidden or name.startswith(forbidden + ".") for name in imported), rel
        text = Path(rel).read_text(encoding="utf-8")
        assert "BenchmarkReport" not in text
