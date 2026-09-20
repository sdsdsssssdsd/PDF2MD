"""pdf2md convert：Application Layer，不启动 Qt。默认 --plan-only 安全。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.utils.paths import DEFAULT_SAVE_MODE, SAVE_MODES, normalize_save_mode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pdf2md convert")
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument(
        "--save-mode",
        default=DEFAULT_SAVE_MODE,
        choices=list(SAVE_MODES),
        help="pdf_sibling=PDF 旁「PDF名_MD」（默认）；root_folder / root_flat=导出根目录",
    )
    parser.add_argument("--workflow", default="快速自动")
    parser.add_argument("--engine", default="自动")
    parser.add_argument("--plan-only", action="store_true", help="只输出 profile/plan")
    parser.add_argument("--execute", action="store_true", help="真正跑 ConversionService")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv or []))

    source = Path(args.source)
    out_dir = Path(args.out) if args.out else source.parent
    save_mode = normalize_save_mode(args.save_mode)
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
    payload = {
        "profile": profile.to_dict(),
        "plan": plan.to_dict(),
        "executed": False,
        "save_mode": save_mode,
    }
    if args.execute:
        from app.core.service.conversion import ConversionOptions, ConversionService
        from app.task_model import ConvertTask, EngineChoice

        engine = args.engine if args.engine != "自动" else EngineChoice.AUTO.value
        task = ConvertTask(pdf_path=source, engine=engine, workflow=args.workflow)
        service = ConversionService(
            ConversionOptions(output_root=out_dir, per_folder=True, save_mode=save_mode)
        )
        result = service.run_task(task)
        payload["executed"] = True
        payload["ok"] = result.ok
        payload["error"] = result.error
        payload["output_dir"] = str(result.output_dir or "")
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            f"parser={plan.parser} stages={','.join(plan.stages)} "
            f"executed={payload['executed']} save_mode={save_mode}"
        )
    return 0
