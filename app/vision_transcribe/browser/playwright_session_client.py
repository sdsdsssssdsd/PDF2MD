"""GUI / Worker 侧：通过子进程驱动 DeepSeek Playwright，避免卡死主界面。"""
from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

from app.utils.paths import APP_ROOT, PYTHON_EXE
from app.vision_transcribe.browser.base import AdapterResult, VisionWebAdapter
from app.vision_transcribe.browser.profile_utils import (
    clear_stale_profile_locks,
    kill_profile_chromium,
)


def _norm_wire_path(p: str | Path) -> str:
    """子进程 JSON 协议：用正斜杠，避免 Windows 反斜杠在管道里破坏 JSON。"""
    return str(Path(p).resolve()).replace("\\", "/")


def _wire_dumps(obj: dict) -> str:
    """序列化发往子进程的命令（路径先规范化）。"""
    payload = dict(obj)
    if "images" in payload and isinstance(payload["images"], list):
        payload["images"] = [_norm_wire_path(p) for p in payload["images"]]
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class PlaywrightSessionClient(VisionWebAdapter):
    """长驻子进程客户端；submit_batch / resume / close。

    关键用后台线程持续读 stdout → 队列，避免 Windows 上
    「readline 超时线程仍占着管道」导致日志行丢失，后台面板空白。
    """

    def __init__(
        self,
        *,
        profile_dir: Path,
        url: str = "https://chat.deepseek.com/",
        python_exe: Path | None = None,
        log=None,
    ) -> None:
        self.profile_dir = Path(profile_dir)
        self.url = url
        self.python_exe = Path(python_exe or PYTHON_EXE)
        self._log = log or (lambda _m: None)
        self._proc: subprocess.Popen | None = None
        self._out_q: queue.Queue[str | None] = queue.Queue()
        self._reader: threading.Thread | None = None
        self._stderr_chunks: list[str] = []

    def start(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            return
        cleared = clear_stale_profile_locks(self.profile_dir)
        if cleared:
            self._log(f"已清理 profile 锁: {', '.join(cleared)}")
        killed = kill_profile_chromium(self.profile_dir)
        if killed:
            self._log(f"已结束占用 profile 的 Chromium 进程: {killed}")
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        env = dict(**{k: v for k, v in __import__("os").environ.items()})
        env["PYTHONPATH"] = str(APP_ROOT) + (
            (";" + env["PYTHONPATH"]) if env.get("PYTHONPATH") else ""
        )
        env["PYTHONIOENCODING"] = "utf-8"
        # 强制子进程 stdout 无缓冲，保证 {"log":...} 实时进面板
        env["PYTHONUNBUFFERED"] = "1"
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        self._out_q = queue.Queue()
        self._stderr_chunks = []
        self._proc = subprocess.Popen(
            [
                str(self.python_exe),
                "-u",
                "-m",
                "app.vision_transcribe.browser.playwright_session",
                str(self.profile_dir),
                self.url,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(APP_ROOT),
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=creationflags,
        )
        self._reader = threading.Thread(
            target=self._stdout_reader_loop, daemon=True, name="pw-stdout"
        )
        self._reader.start()
        threading.Thread(
            target=self._stderr_reader_loop, daemon=True, name="pw-stderr"
        ).start()
        self._log("正在启动 DeepSeek 浏览器子进程…")
        self._log("[PW] 子进程：连接中…")
        ready = self._recv(timeout=30.0)
        if not ready or not ready.get("ok"):
            err = (ready or {}).get("error") if ready else None
            if not err:
                err = self._stderr_tail() or "子进程启动超时（30s）"
            self.close()
            raise RuntimeError(f"Playwright 子进程启动失败: {err}")
        self._log("浏览器子进程就绪（首次 submit 时打开浏览器）")
        self._log("[PW] 子进程：已连接")

    def _stdout_reader_loop(self) -> None:
        proc = self._proc
        if not proc or not proc.stdout:
            self._out_q.put(None)
            return
        try:
            while True:
                line = proc.stdout.readline()
                if line == "":
                    break
                self._out_q.put(line)
        except Exception:
            pass
        finally:
            self._out_q.put(None)

    def _stderr_reader_loop(self) -> None:
        proc = self._proc
        if not proc or not proc.stderr:
            return
        try:
            while True:
                chunk = proc.stderr.readline()
                if chunk == "":
                    break
                self._stderr_chunks.append(chunk)
                if len(self._stderr_chunks) > 200:
                    self._stderr_chunks = self._stderr_chunks[-100:]
        except Exception:
            pass

    def submit_batch(self, images: list[Path], prompt: str) -> AdapterResult:
        self.start()
        self._log(f"[PW] 提交本批：{len(images)} 张图")
        self._send(
            {
                "cmd": "submit",
                "images": images,
                "prompt": prompt,
            }
        )
        # 识图可能很久；期间持续转发子进程 log
        resp = self._recv(timeout=600.0)
        if resp is None:
            return AdapterResult(
                markdown="",
                needs_user=False,
                message=self._stderr_tail() or "子进程无响应",
            )
        if resp.get("needs_user"):
            return AdapterResult(
                markdown="",
                needs_user=True,
                message=str(resp.get("message") or "需要登录/验证"),
            )
        if not resp.get("ok"):
            raise RuntimeError(str(resp.get("error") or resp))
        return AdapterResult(
            markdown=str(resp.get("markdown") or ""),
            needs_user=False,
            extract_stats=resp.get("extract_stats")
            if isinstance(resp.get("extract_stats"), dict)
            else None,
        )

    def resume(self) -> AdapterResult:
        """用户登录后继续。"""
        self._log("[PW] resume：继续上次提交")
        self._send({"cmd": "resume"})
        resp = self._recv(timeout=600.0)
        if resp is None:
            raise RuntimeError("resume 无响应: " + self._stderr_tail())
        if resp.get("needs_user"):
            return AdapterResult(
                markdown="",
                needs_user=True,
                message=str(resp.get("message") or "仍需人工处理"),
            )
        if not resp.get("ok"):
            raise RuntimeError(str(resp.get("error") or resp))
        return AdapterResult(
            markdown=str(resp.get("markdown") or ""),
            needs_user=False,
            extract_stats=resp.get("extract_stats")
            if isinstance(resp.get("extract_stats"), dict)
            else None,
        )

    def close(self) -> None:
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        try:
            if proc.poll() is None and proc.stdin:
                proc.stdin.write(json.dumps({"cmd": "close"}) + "\n")
                proc.stdin.flush()
                proc.wait(timeout=15)
        except Exception:
            pass
        try:
            if proc.poll() is None:
                proc.kill()
        except Exception:
            pass

    def _send(self, obj: dict) -> None:
        assert self._proc and self._proc.stdin
        self._proc.stdin.write(_wire_dumps(obj) + "\n")
        self._proc.stdin.flush()

    def _recv(self, *, timeout: float) -> dict | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._proc is not None and self._proc.poll() is not None:
                self._drain_logs_nonblocking()
                return {
                    "ok": False,
                    "error": "子进程已退出: " + self._stderr_tail(),
                }
            remaining = max(0.05, deadline - time.monotonic())
            try:
                line = self._out_q.get(timeout=min(0.5, remaining))
            except queue.Empty:
                continue
            if line is None:
                return {
                    "ok": False,
                    "error": "子进程 stdout 已关闭: " + self._stderr_tail(),
                }
            parsed = self._handle_stdout_line(line)
            if parsed is not None:
                return parsed
        return None

    def _handle_stdout_line(self, line: str) -> dict | None:
        """处理一行 stdout。进度 log 返回 None；命令结果返回 dict。"""
        line = line.strip()
        if not line:
            return None
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            self._log(f"[pw] {line[:300]}")
            return None
        # 子进程进度：{"ok": true, "log": "..."}
        if (
            "log" in obj
            and "markdown" not in obj
            and "error" not in obj
            and "needs_user" not in obj
            and "ready" not in obj
            and "closed" not in obj
        ):
            self._log(str(obj.get("log") or ""))
            return None
        return obj

    def _drain_logs_nonblocking(self) -> None:
        while True:
            try:
                line = self._out_q.get_nowait()
            except queue.Empty:
                return
            if line is None:
                return
            self._handle_stdout_line(line)

    def _stderr_tail(self) -> str:
        return "".join(self._stderr_chunks)[-1500:]
