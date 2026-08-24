# -*- coding: utf-8 -*-
"""主进程侧 Paddle 公式 Worker 客户端（localhost JSON 行协议）。"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import threading
from pathlib import Path
from typing import Any

from app.formula.ppformula_paths import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    META_PATH,
    resolve_paddle_python,
)
from app.utils.paths import SCRIPTS_DIR

_LOCK = threading.Lock()
_CLIENT = None


class PPFormulaWorkerClient:
    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        meta_path: Path | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.meta_path = meta_path or META_PATH
        self._req_id = 0

    def _next_id(self) -> int:
        self._req_id += 1
        return self._req_id

    def _rpc(self, method: str, params: dict[str, Any] | None = None, *, timeout: float = 30.0) -> dict[str, Any]:
        host, port = self.host, self.port
        if self.meta_path.is_file():
            try:
                meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
                host = str(meta.get("host") or host)
                port = int(meta.get("port") or port)
            except Exception:
                pass
        req = {"id": self._next_id(), "method": method, "params": params or {}}
        raw = (json.dumps(req, ensure_ascii=False) + "\n").encode("utf-8")
        with socket.create_connection((host, port), timeout=min(8.0, timeout)) as sock:
            sock.settimeout(timeout)
            sock.sendall(raw)
            buf = b""
            while b"\n" not in buf:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                buf += chunk
        if not buf:
            return {"ok": False, "error": "empty_response"}
        return json.loads(buf.split(b"\n", 1)[0].decode("utf-8"))

    def ping(self) -> bool:
        try:
            return bool(self._rpc("ping", timeout=2.0).get("ok"))
        except Exception:
            return False

    def health(self) -> dict[str, Any]:
        try:
            return self._rpc("health", timeout=4.0)
        except Exception as e:
            return {"ok": False, "error": str(e), "model_loaded": False}

    def load(self, model_name: str | None = None) -> dict[str, Any]:
        try:
            return self._rpc("load", {"model_name": model_name}, timeout=600.0)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def recognize(
        self,
        *,
        image_b64: str,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        try:
            return self._rpc(
                "recognize",
                {"image_b64": image_b64, "model_name": model_name},
                timeout=60.0,
            )
        except Exception as e:
            return {"ok": False, "error": str(e), "success": False}

    def spawn(self) -> dict[str, Any]:
        py = resolve_paddle_python()
        server = SCRIPTS_DIR / "paddle_formula_worker_server.py"
        if py is None or not server.is_file():
            return {"ok": False, "error": "paddle_worker_assets_missing"}
        self.meta_path.parent.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        flags = 0
        if os.name == "nt":
            flags = 0x08000000 | 0x00000200 | 0x00000008
        subprocess.Popen(
            [str(py), str(server), "--host", self.host, "--port", str(self.port)],
            cwd=str(server.parent.parent),
            env=env,
            creationflags=flags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return {"ok": True, "spawned": True}


def get_ppformula_worker_client() -> PPFormulaWorkerClient:
    global _CLIENT
    with _LOCK:
        if _CLIENT is None:
            _CLIENT = PPFormulaWorkerClient()
        return _CLIENT
