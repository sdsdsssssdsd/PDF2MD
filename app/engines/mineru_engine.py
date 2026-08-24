"""MinerU 引擎：通过 CLI subprocess 隔离，更稳定。"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable

from app.utils.paths import MINERU_EXE, PYTHON_EXE
from app.utils.transformers_patch import ensure_transformers_prune_api

ProgressCB = Callable[[str], None]


def _hf_env() -> dict[str, str]:
    """国内直连 HuggingFace 易卡住，默认走镜像；已设置则不覆盖。"""
    env = os.environ.copy()
    env.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    env.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    env.setdefault("PYTHONUNBUFFERED", "1")
    # transformers 5.x 与 MinerU Unimernet 不兼容；且勿拉坏掉的 TensorFlow
    env.setdefault("TRANSFORMERS_NO_TF", "1")
    env.setdefault("USE_TF", "0")
    env.setdefault("USE_TORCH", "1")
    # 国内 HuggingFace 元数据常失败，优先 ModelScope
    env.setdefault("MINERU_MODEL_SOURCE", "modelscope")
    return env


def convert_pdf(
    pdf_path: Path,
    out_dir: Path,
    *,
    ocr_mode: str = "auto",
    keep_tables: bool = True,
    keep_formulas: bool = True,
    progress: ProgressCB | None = None,
):
    """MinerU 解析，返回 ConversionResult（原始 Markdown）。"""
    from app.engines.base import ConversionResult

    ensure_transformers_prune_api()

    def emit(msg: str) -> None:
        if progress:
            progress(msg)

    out_dir.mkdir(parents=True, exist_ok=True)
    method = {"auto": "auto", "force": "ocr", "disable": "txt"}.get(ocr_mode, "auto")

    cmd = [
        str(MINERU_EXE if MINERU_EXE.exists() else PYTHON_EXE),
    ]
    if not MINERU_EXE.exists():
        cmd += ["-m", "mineru.cli.client"]

    cmd += [
        "-p",
        str(pdf_path),
        "-o",
        str(out_dir),
        "-m",
        method,
        "-b",
        "pipeline",
        "-f",
        str(keep_formulas).lower(),
        "-t",
        str(keep_tables).lower(),
    ]

    emit("正在启动 MinerU（首次会下载模型，可能较久）...")
    t0 = time.time()
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=_hf_env(),
        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
    )
    assert proc.stdout is not None
    log_lines: list[str] = []
    for line in proc.stdout:
        line = line.rstrip()
        if not line:
            continue
        log_lines.append(line)
        low = line.lower()
        if "fetching" in low or "downloading" in low or "hf hub" in low:
            emit("正在下载模型（HuggingFace）... " + line[:80])
        elif "layout" in low:
            emit("正在识别版面...")
        elif "table" in low:
            emit("正在处理表格...")
        elif "formula" in low or "equation" in low:
            emit("正在处理公式...")
        elif "ocr" in low:
            emit("正在 OCR...")
        else:
            emit(line[:120])

    code = proc.wait()
    (out_dir / "conversion.log").write_text("\n".join(log_lines), encoding="utf-8")
    if code != 0:
        raise RuntimeError(f"MinerU 退出码 {code}\n" + "\n".join(log_lines[-30:]))

    md = _find_markdown(out_dir, pdf_path.stem)
    if md is None:
        raise RuntimeError("MinerU 未生成 Markdown 文件")

    raw_path = out_dir / f"{pdf_path.stem}.raw.md"
    if md.resolve() != raw_path.resolve():
        shutil.copy2(md, raw_path)
        img_src = md.parent / "images"
        if img_src.is_dir():
            img_dst = out_dir / "images"
            if not img_dst.exists():
                shutil.copytree(img_src, img_dst)
    else:
        # mineru 已直接写到目标名时，仍规范为 .raw.md
        if md.name.endswith(".md") and not md.name.endswith(".raw.md"):
            shutil.copy2(md, raw_path)

    artifacts = out_dir / "images"
    elapsed = time.time() - t0
    emit(f"解析完成，耗时 {elapsed:.1f}s → {raw_path.name}")
    return ConversionResult(
        markdown_path=raw_path,
        parser="mineru",
        artifacts_dir=artifacts if artifacts.exists() else None,
        metadata={"elapsed_sec": elapsed, "keep_formulas": keep_formulas},
    )


def _find_markdown(root: Path, stem: str) -> Path | None:
    candidates = [
        p
        for p in root.rglob("*.md")
        if not p.name.endswith(".raw.md") and not p.name.endswith(".repair.md")
    ]
    if not candidates:
        return None
    for p in candidates:
        if p.stem == stem or stem in p.stem:
            return p
    return candidates[0]
