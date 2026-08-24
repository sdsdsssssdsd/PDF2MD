#!/usr/bin/env python
"""在 DeepSeek 浏览器里演示一遍操作，保存 DOM 定位供自动回放。

用法:
  python scripts/record_deepseek_dom.py
  python scripts/record_deepseek_dom.py --skip-upload-click

录制结果写入 data/deepseek_ui.json → recorded_workflow。
只需点 3 处：新对话 / 识图模式 / 输入框。
运行时顺序：上传 bookfigures -> 填 Prompt -> 点发送（有内容后才可点）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.vision_transcribe.browser.dom_recorder import record_deepseek_workflow


def main() -> int:
    ap = argparse.ArgumentParser(description="录制 DeepSeek 网页操作演示")
    ap.add_argument(
        "--profile",
        default=str(ROOT / "data" / "deepseek_profile"),
        help="Playwright 持久化 profile",
    )
    ap.add_argument(
        "--skip-upload-click",
        action="store_true",
        help="上传步骤不点附件，仅用 set_input_files",
    )
    args = ap.parse_args()

    def log(msg: str) -> None:
        print(msg, flush=True)

    try:
        record_deepseek_workflow(
            profile_dir=Path(args.profile),
            log=log,
            skip_upload_click=bool(args.skip_upload_click),
        )
    except KeyboardInterrupt:
        print("\n已取消")
        return 130
    except Exception as e:
        print(f"录制失败: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
