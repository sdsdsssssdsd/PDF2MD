"""启动 Playwright 前清理 profile 锁 / 残留进程。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def clear_stale_profile_locks(profile_dir: Path) -> list[str]:
    removed: list[str] = []
    profile_dir = Path(profile_dir)
    if not profile_dir.exists():
        return removed
    for name in ("SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile"):
        p = profile_dir / name
        if p.exists():
            try:
                p.unlink()
                removed.append(name)
            except OSError:
                pass
    default = profile_dir / "Default"
    if default.is_dir():
        for name in ("Lockfile", "LOCK"):
            p = default / name
            if p.exists():
                try:
                    p.unlink()
                    removed.append(f"Default/{name}")
                except OSError:
                    pass
    return removed


DEEPSEEK_VIEWPORT_WIDTH = 1400
DEEPSEEK_VIEWPORT_HEIGHT = 900
DEEPSEEK_BROWSER_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-first-run",
    "--no-default-browser-check",
    "--start-maximized",
    "--window-position=0,0",
]
DEEPSEEK_SEND_POLL_MS_MIN = 300
DEEPSEEK_SEND_POLL_MS_DEFAULT = 400


def maximize_browser_window(page, log=None) -> bool:
    """有头窗口最大化，避免固定 viewport 与窗口尺寸不一致导致页面缩放闪动。"""
    log_fn = log or (lambda _m: None)
    try:
        cdp = page.context.new_cdp_session(page)
        info = cdp.send("Browser.getWindowForTarget")
        window_id = info.get("windowId")
        if window_id is not None:
            cdp.send(
                "Browser.setWindowBounds",
                {
                    "windowId": window_id,
                    "bounds": {"windowState": "maximized"},
                },
            )
            page.wait_for_timeout(500)
            log_fn("浏览器窗口已最大化")
            return True
    except Exception as exc:
        log_fn(f"CDP 最大化跳过（已启用 --start-maximized）: {exc}")
    return False


def kill_profile_chromium(profile_dir: Path) -> int:
    """Windows：结束仍占用该 user-data-dir 的 Chromium（Playwright 残留）。"""
    if sys.platform != "win32":
        return 0
    profile = str(Path(profile_dir).resolve())
    # wmic 查命令行含 profile 路径的 chrome/chromium
    try:
        out = subprocess.check_output(
            [
                "wmic",
                "process",
                "where",
                "name='chrome.exe' or name='chromium.exe'",
                "get",
                "processid,commandline",
                "/format:csv",
            ],
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except Exception:
        return 0
    killed = 0
    for line in out.splitlines():
        if profile.replace("\\", "\\\\") not in line and profile not in line:
            continue
        parts = line.strip().split(",")
        if not parts:
            continue
        try:
            pid = int(parts[-1].strip())
            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            killed += 1
        except (ValueError, OSError):
            continue
    return killed
