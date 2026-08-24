#!/usr/bin/env python
"""DeepSeek Web Playwright 冒烟 PoC（见 a2-1.md）。

用法：
  1) pip install playwright && playwright install chromium
  2) python scripts/deepseek_playwright_poc.py --images path1.png ...
  3) 若提示登录：在弹出的浏览器里登录，然后回到终端按回车（窗口不要关）

登录态保存在 data/deepseek_profile；下次一般不用再登。
"""
from __future__ import annotations

import argparse
from pathlib import Path

from app.utils.paths import APP_ROOT
from app.vision_transcribe.browser.deepseek_web import DeepSeekPlaywrightAdapter
from app.vision_transcribe.prompt_builder import build_prompt


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", nargs="+", required=True, help="本批页面 PNG")
    ap.add_argument("--out", default=str(APP_ROOT / "_tmp_vision_poc" / "test.md"))
    ap.add_argument(
        "--profile",
        default=str(APP_ROOT / "data" / "deepseek_profile"),
    )
    ap.add_argument("--start-page", type=int, default=1)
    ap.add_argument("--end-page", type=int, default=None)
    ap.add_argument(
        "--keep-open",
        action="store_true",
        help="结束后不关浏览器（方便检查）",
    )
    args = ap.parse_args()

    images = [Path(p) for p in args.images]
    for p in images:
        if not p.exists():
            raise SystemExit(f"missing image: {p}")
    end = args.end_page or (args.start_page + len(images) - 1)
    prompt = build_prompt(args.start_page, end)

    adapter = DeepSeekPlaywrightAdapter(
        profile_dir=Path(args.profile),
        headless=False,
    )
    try:
        while True:
            result = adapter.submit_batch(images, prompt)
            if not result.needs_user:
                break
            print(result.message or "需要人工处理浏览器。")
            print("→ 请在浏览器完成登录/验证，完成后回到这里按回车继续（不要关窗口）。")
            try:
                input()
            except EOFError:
                print("未继续，退出。登录态若已写入 profile，下次可直接重跑。")
                return 2

        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(result.markdown, encoding="utf-8")
        print("OK →", out)
        if args.keep_open:
            print("浏览器保持打开；关窗口或 Ctrl+C 结束。")
            try:
                input()
            except EOFError:
                pass
        return 0
    finally:
        if not args.keep_open:
            adapter.close()


if __name__ == "__main__":
    raise SystemExit(main())
