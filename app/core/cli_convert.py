"""pdf2md convert：Application Layer，不启动 Qt。默认 --plan-only 安全。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pdf2md convert")
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--workflow", default="快速自动")
    parser.add_argument("--engine", default="自动")
    parser.add_argument("--plan-only", action="store_true", help="只输出 profile/plan")
    parser.add_argument("--execute", action="store_true", help="真正跑 ConversionService")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv or []))

    source = Path(args.source)
    out_dir = Path(args.out) if args.out else source.parent
    from app.core.domain.job import ConversionRequest
    from app.core.pipeline.planner import plan_for_request
    from app.core.routing.profiler import profile_source

    profile = profile_source(source)
    request = ConversionRequest(
        source_path=source,
        output_dir=out_dir,
        workflow=args.workflow,
        engine=args.engine,
    )
    plan = plan_for_request(request, profile=profile)
    payload = {"profile": profile.to_dict(), "plan": plan.to_dict(), "executed": False}
    if args.execute:
        from app.core.service.conversion import ConversionOptions, ConversionService
        from app.task_model import ConvertTask, EngineChoice

        engine = args.engine if args.engine != "自动" else EngineChoice.AUTO.value
        task = ConvertTask(pdf_path=source, engine=engine, workflow=args.workflow)
        service = ConversionService(ConversionOptions(output_root=out_dir, per_folder=True))
        result = service.run_task(task)
        payload["executed"] = True
        payload["ok"] = result.ok
        payload["error"] = result.error
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"parser={plan.parser} stages={','.join(plan.stages)} executed={payload['executed']}")
    return 0
