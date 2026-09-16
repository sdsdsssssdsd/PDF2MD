"""Benchmark CLI：python -m app.core benchmark"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.core.benchmark.adapters import olmocr, omnidocbench
from app.core.benchmark.delta import compare_reports
from app.core.benchmark.report import BenchmarkReport
from app.core.benchmark.runner import run_gold_suite


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pdf2md-core benchmark")
    parser.add_argument("--suite", default="", help="academic|scan|table|multilingual|pathological|regression")
    parser.add_argument("--adapter", default="gold_v2", choices=("gold_v2", "omnidocbench", "olmocr"))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("-o", "--output", type=Path, default=None)
    parser.add_argument("--compare", nargs=2, metavar=("BASELINE", "CANDIDATE"), default=None)
    args = parser.parse_args(argv)

    if args.compare:
        baseline = BenchmarkReport.load(Path(args.compare[0]))
        candidate = BenchmarkReport.load(Path(args.compare[1]))
        delta = compare_reports(baseline, candidate)
        payload = delta.to_dict()
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else _fmt_delta(delta))
        return 0 if delta.allowed else 2

    if args.adapter == "omnidocbench":
        report = omnidocbench.run()
    elif args.adapter == "olmocr":
        report = olmocr.run()
    else:
        report = run_gold_suite(suite=args.suite or None)
    if args.output:
        report.save(args.output)
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(_fmt_report(report))
    if report.skipped and args.adapter != "gold_v2":
        return 0
    return 0 if (report.overall or 0) >= 0 else 1


def _fmt_report(report: BenchmarkReport) -> str:
    if report.skipped:
        return f"{report.adapter} skipped: {report.skip_reason}"
    lines = [
        f"{report.adapter} cases={report.cases} passed={report.passed}",
    ]
    for name, value in sorted(report.slices.items()):
        lines.append(f"  {name} {value:.4f}")
    return "\n".join(lines)


def _fmt_delta(delta) -> str:
    lines = [f"allowed={delta.allowed} reason={delta.reason}"]
    for name, item in sorted(delta.slices.items()):
        sign = f"{item.delta:+.4f}"
        lines.append(f"  {name} {item.baseline:.4f} -> {item.candidate:.4f} ({sign})")
    return "\n".join(lines)
