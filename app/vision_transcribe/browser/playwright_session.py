"""Playwright 会话子进程：与 Qt GUI 进程隔离，避免 Windows 上界面卡死。

协议（stdin/stdout 每行一个 JSON）：
  → {"cmd":"submit","images":["..."],"prompt":"..."}
  ← {"ok":true,"needs_user":false,"markdown":"..."}
  ← {"ok":false,"needs_user":true,"message":"..."}
  → {"cmd":"resume"}   # 用户登录后继续上次 submit
  → {"cmd":"close"}
  ← {"ok":true,"closed":true}
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    # 再刷底层缓冲（Windows 管道偶发延迟）
    try:
        sys.stdout.buffer.flush()
    except Exception:
        pass


def _read() -> dict | None:
    line = sys.stdin.readline()
    if not line:
        return None
    line = line.strip()
    if not line:
        return _read()
    try:
        return json.loads(line)
    except json.JSONDecodeError as e:
        _emit(
            {
                "ok": False,
                "error": f"stdin JSON 无效: {e}（请更新客户端；路径应使用正斜杠）",
                "line_head": line[:120],
            }
        )
        return {"cmd": "__bad_json__"}


def main() -> int:
    # 延迟 import，保证启动日志先出来
    _emit({"ok": True, "ready": True, "msg": "playwright_session starting"})
    try:
        from app.vision_transcribe.browser.deepseek_web import DeepSeekPlaywrightAdapter
    except Exception as e:
        _emit({"ok": False, "error": f"import failed: {e}"})
        return 1

    profile = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/deepseek_profile")
    url = sys.argv[2] if len(sys.argv) > 2 else "https://chat.deepseek.com/"

    def _log(msg: str) -> None:
        _emit({"ok": True, "log": msg})

    adapter = DeepSeekPlaywrightAdapter(
        profile_dir=profile, url=url, headless=False, log=_log
    )
    pending: dict | None = None  # 上次 needs_user 的 submit 参数

    while True:
        msg = _read()
        if msg is None:
            break
        cmd = msg.get("cmd")
        try:
            if cmd == "__bad_json__":
                continue
            if cmd == "close":
                adapter.close()
                _emit({"ok": True, "closed": True})
                break
            if cmd == "resume":
                if not pending:
                    _emit({"ok": False, "error": "no pending submit"})
                    continue
                msg = {"cmd": "submit", **pending}
                cmd = "submit"
            if cmd == "submit":
                images = [Path(p) for p in msg.get("images") or []]
                prompt = msg.get("prompt") or ""
                pending = {"images": [str(p) for p in images], "prompt": prompt}
                result = adapter.submit_batch(images, prompt)
                if result.needs_user:
                    _emit(
                        {
                            "ok": False,
                            "needs_user": True,
                            "message": result.message or "需要登录/验证",
                        }
                    )
                    continue
                pending = None
                _emit(
                    {
                        "ok": True,
                        "needs_user": False,
                        "markdown": result.markdown,
                        "extract_stats": result.extract_stats,
                    }
                )
                continue
            _emit({"ok": False, "error": f"unknown cmd: {cmd}"})
        except Exception as e:
            _emit(
                {
                    "ok": False,
                    "error": str(e),
                    "traceback": traceback.format_exc()[-2000:],
                }
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
