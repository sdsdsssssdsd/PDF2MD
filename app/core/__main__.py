"""CLI：不启动 Qt。python -m app.core <pdf> | benchmark | resources | doctor | providers"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "benchmark":
        from app.core.benchmark.cli import main as benchmark_main

        return benchmark_main(argv[1:])
    if argv and argv[0] == "resources":
        from app.core.runtime import get_runtime

        print(json.dumps(get_runtime().health(), ensure_ascii=False, indent=2))
        return 0
    if argv and argv[0] == "doctor":
        from app.core.doctor import main as doctor_main

        return doctor_main(argv[1:])
    if argv and argv[0] == "providers":
        from app.core.providers.registry import get_registry

        payload = [item.to_dict() for item in get_registry().statuses()]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if argv and argv[0] == "inspect":
        argv = argv[1:]
    if argv and argv[0] == "convert":
        from app.core.cli_convert import main as convert_main

        return convert_main(argv[1:])
    if argv and argv[0] == "protocol":
        from app.core.protocol import protocol_manifest

        print(json.dumps(protocol_manifest(), ensure_ascii=False, indent=2))
        return 0
    if argv and argv[0] == "release-check":
        from app.core.release import main as release_main

        return release_main(argv[1:])
    if argv and argv[0] == "lock":
        from app.core.lockfile import main as lock_main

        return lock_main(argv[1:])
    if argv and argv[0] == "sbom":
        from app.core.sbom import main as sbom_main

        return sbom_main(argv[1:])
    if argv and argv[0] == "smoke":
        from app.core.smoke import main as smoke_main

        return smoke_main(argv[1:])

    parser = argparse.ArgumentParser(prog="pdf2md", description="PDF2MD 1.0 CLI")
    parser.add_argument("source", type=Path, help="PDF 或 Markdown 路径")
    parser.add_argument("--workflow", default="快速自动")
    parser.add_argument("--engine", default="自动")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    from app.core.domain.job import ConversionRequest
    from app.core.pipeline.planner import plan_for_request
    from app.core.routing.profiler import profile_source

    source = Path(args.source)
    profile = profile_source(source)
    request = ConversionRequest(
        source_path=source,
        output_dir=source.parent,
        workflow=args.workflow,
        engine=args.engine,
    )
    plan = plan_for_request(request, profile=profile)
    payload = {"profile": profile.to_dict(), "plan": plan.to_dict()}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"pages={profile.page_count} scan={profile.scan_ratio:.2f} formula={profile.formula_density:.2f}")
        print(f"plan profile={plan.profile} parser={plan.parser} stages={','.join(plan.stages)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
