"""Gold v2 runner：本地 markdown fixture。不跑 OmniDoc / 不进生产 QA。"""
from __future__ import annotations

import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.core.benchmark.catalog import GoldCase, load_catalog
from app.core.benchmark.report import METRIC_KEYS, BenchmarkReport
from app.core.domain.quality import CheckStatus, QualityVerdict
from app.core.qa.gold import evaluate_gold

_CHECK_TO_METRIC = {
    "page_coverage": "page_coverage",
    "formula_unresolved": "formula",
    "formula_structural_validity": "formula",
    "equation_number_preservation": "formula",
    "text_anchor_preservation": "text",
}


def run_gold_suite(
    catalog_path: Path | None = None,
    *,
    suite: str | None = None,
) -> BenchmarkReport:
    cases = load_catalog(catalog_path)
    if suite:
        cases = [c for c in cases if c.suite == suite]
    results = [run_gold_case(case) for case in cases]
    return aggregate(results, suite=suite or "gold_v2")


def run_gold_case(case: GoldCase) -> dict[str, Any]:
    markdown = ""
    if case.fixture.is_file():
        markdown = case.fixture.read_text(encoding="utf-8")
    t0 = time.perf_counter()
    report = evaluate_gold(
        markdown,
        case.gold_dir if case.gold_dir.is_dir() else None,
        page_count=case.page_count,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    expected = case.expect_status or QualityVerdict.VERIFIED.value
    passed = report.status == expected
    checks = {c.check_id: c.status for c in report.checks}
    scores = {c.check_id: c.score for c in report.checks if c.score is not None}
    return {
        "id": case.id,
        "suite": case.suite,
        "tags": list(case.tags),
        "status": report.status,
        "expected": expected,
        "passed": passed,
        "checks": checks,
        "scores": scores,
        "elapsed_ms": elapsed_ms,
    }


def aggregate(results: list[dict[str, Any]], *, suite: str = "gold_v2") -> BenchmarkReport:
    n = len(results)
    passed = sum(1 for r in results if r.get("passed"))
    slices: dict[str, float] = {}
    if n:
        slices["overall"] = passed / n
    by_tag: dict[str, list[bool]] = defaultdict(list)
    by_suite: dict[str, list[bool]] = defaultdict(list)
    metric_vals: dict[str, list[float]] = defaultdict(list)
    elapsed: list[float] = []
    for row in results:
        ok = bool(row.get("passed"))
        by_suite[str(row.get("suite") or "")].append(ok)
        for tag in row.get("tags") or []:
            by_tag[str(tag)].append(ok)
        elapsed.append(float(row.get("elapsed_ms") or 0.0))
        checks = dict(row.get("checks") or {})
        scores = dict(row.get("scores") or {})
        for check_id, metric in _CHECK_TO_METRIC.items():
            if check_id in scores and scores[check_id] is not None:
                metric_vals[metric].append(float(scores[check_id]))
            elif check_id in checks:
                metric_vals[metric].append(
                    1.0 if checks[check_id] == CheckStatus.PASS.value else 0.0
                )
    for tag, flags in sorted(by_tag.items()):
        if flags:
            slices[tag] = sum(flags) / len(flags)
    for name, flags in sorted(by_suite.items()):
        if name and flags:
            slices[f"suite:{name}"] = sum(flags) / len(flags)
    metrics: dict[str, float | None] = {k: None for k in METRIC_KEYS}
    metrics["quality"] = slices.get("overall")
    metrics["failure_rate"] = (1.0 - slices["overall"]) if n else None
    for key, vals in metric_vals.items():
        if vals:
            metrics[key] = sum(vals) / len(vals)
    if elapsed:
        ordered = sorted(elapsed)
        metrics["latency_p50"] = _percentile(ordered, 50)
        metrics["latency_p95"] = _percentile(ordered, 95)
    return BenchmarkReport(
        suite=suite,
        adapter="gold_v2",
        cases=n,
        passed=passed,
        slices=slices,
        metrics=metrics,
        extras={"results": [{"id": r["id"], "passed": r["passed"], "status": r["status"]} for r in results]},
    )


def _percentile(ordered: list[float], q: int) -> float:
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return ordered[0]
    idx = min(len(ordered) - 1, max(0, int(round((q / 100.0) * (len(ordered) - 1)))))
    return ordered[idx]
