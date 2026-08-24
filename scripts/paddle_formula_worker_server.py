# -*- coding: utf-8 -*-
"""独立 Paddle 公式 Worker（.venv-paddle-formula）。GUI / Torch 环境不要跑这个文件。

协议：TCP 行分隔 JSON。方法：ping / health / load / recognize / quit
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import socket
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18775


class Runtime:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.model: Any = None
        self.model_name = ""
        self.model_loaded = False
        self.last_error = ""
        self.load_count = 0
        self.started_at = time.time()


RT = Runtime()


def _log(msg: str) -> None:
    print(f"[pp-formula-worker] {msg}", flush=True, file=sys.stderr)


def _write_meta(host: str, port: int) -> None:
    cache = ROOT / ".cache"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "paddle_formula_worker.json").write_text(
        json.dumps({"host": host, "port": port, "pid": os.getpid()}, ensure_ascii=False),
        encoding="utf-8",
    )


def _ensure_model(model_name: str | None) -> Any:
    name = model_name or RT.model_name or "PP-FormulaNet_plus-M"
    with RT.lock:
        if RT.model is not None and RT.model_name == name:
            return RT.model
        from paddleocr import FormulaRecognition  # type: ignore

        RT.model = FormulaRecognition(model_name=name)
        RT.model_name = name
        RT.model_loaded = True
        RT.load_count += 1
        RT.last_error = ""
        return RT.model


def _recognize(image_b64: str, model_name: str | None) -> dict[str, Any]:
    raw = base64.b64decode(image_b64)
    try:
        from PIL import Image

        im = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception as e:
        return {"ok": False, "error": f"decode_image:{e}"}
    model = _ensure_model(model_name)
    result = model.predict(im)
    row = result[0] if isinstance(result, list) and result else result
    latex = ""
    if isinstance(row, dict):
        latex = str(row.get("rec_formula") or row.get("latex") or "")
    elif hasattr(row, "get"):
        latex = str(row.get("rec_formula") or "")
    latex = latex.strip()
    return {
        "ok": bool(latex),
        "success": bool(latex),
        "rec_formula": latex,
        "latex": latex,
        "model_name": RT.model_name,
        "error": None if latex else "empty_rec_formula",
    }


def _handle(req: dict[str, Any]) -> dict[str, Any]:
    method = str(req.get("method") or "")
    params = req.get("params") or {}
    rid = req.get("id")
    try:
        if method == "ping":
            return {"ok": True, "id": rid, "pong": True}
        if method == "health":
            paddle_ok = True
            try:
                import paddleocr  # noqa: F401
            except Exception:
                paddle_ok = False
            return {
                "ok": True,
                "id": rid,
                "model_loaded": RT.model_loaded,
                "model_name": RT.model_name,
                "load_count": RT.load_count,
                "paddleocr_importable": paddle_ok,
                "uptime": round(time.time() - RT.started_at, 1),
                "last_error": RT.last_error,
            }
        if method == "load":
            _ensure_model(params.get("model_name"))
            return {"ok": True, "id": rid, "model_name": RT.model_name, "load_count": RT.load_count}
        if method == "recognize":
            out = _recognize(str(params.get("image_b64") or ""), params.get("model_name"))
            out["id"] = rid
            return out
        if method == "quit":
            return {"ok": True, "id": rid, "quit": True}
        return {"ok": False, "id": rid, "error": f"unknown_method:{method}"}
    except Exception as e:
        RT.last_error = f"{type(e).__name__}:{e}"
        _log(traceback.format_exc())
        return {"ok": False, "id": rid, "error": RT.last_error}


def serve(host: str, port: int) -> None:
    _write_meta(host, port)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.listen(8)
    _log(f"listen {host}:{port}")
    while True:
        conn, _addr = sock.accept()
        with conn:
            buf = b""
            while b"\n" not in buf:
                chunk = conn.recv(65536)
                if not chunk:
                    break
                buf += chunk
            if not buf:
                continue
            try:
                req = json.loads(buf.split(b"\n", 1)[0].decode("utf-8"))
            except Exception as e:
                conn.sendall((json.dumps({"ok": False, "error": str(e)}) + "\n").encode("utf-8"))
                continue
            resp = _handle(req)
            conn.sendall((json.dumps(resp, ensure_ascii=False) + "\n").encode("utf-8"))
            if resp.get("quit"):
                _log("quit")
                return


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = ap.parse_args()
    serve(args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
