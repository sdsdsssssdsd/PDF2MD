"""批次响应入库。"""
from __future__ import annotations

from pathlib import Path

from app.vision_transcribe.manifest import batch_dir


def strip_wrapping_fence(text: str) -> str:
    """若整篇被 ```markdown ... ``` 包裹则剥掉；内部代码块保留。"""
    s = (text or "").strip()
    if not s.startswith("```"):
        return text or ""
    lines = s.splitlines()
    if len(lines) < 2:
        return text or ""
    first = lines[0].strip().lower()
    if first not in ("```", "```md", "```markdown"):
        return text or ""
    if lines[-1].strip() != "```":
        return text or ""
    return "\n".join(lines[1:-1]).strip() + "\n"


def ingest_raw_response(output_dir: Path, batch_id: int, text: str) -> Path:
    from app.vision_transcribe.clipboard_sanitize import sanitize_vision_clipboard

    d = batch_dir(output_dir, batch_id)
    d.mkdir(parents=True, exist_ok=True)
    raw = d / "response.raw.md"
    cleaned = strip_wrapping_fence(text)
    cleaned = sanitize_vision_clipboard(cleaned)
    raw.write_text(cleaned if cleaned.endswith("\n") else cleaned + "\n", encoding="utf-8")
    return raw


def write_accepted_response(output_dir: Path, batch_id: int, text: str) -> Path:
    d = batch_dir(output_dir, batch_id)
    d.mkdir(parents=True, exist_ok=True)
    path = d / "response.md"
    body = text if text.endswith("\n") else text + "\n"
    path.write_text(body, encoding="utf-8")
    return path


def read_raw_response(output_dir: Path, batch_id: int) -> str | None:
    path = batch_dir(output_dir, batch_id) / "response.raw.md"
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def clear_batch_artifacts(output_dir: Path, batch_id: int) -> None:
    """重跑前清掉旧批次回答，避免 resume 误读脏数据。"""
    d = batch_dir(output_dir, batch_id)
    if not d.is_dir():
        return
    for name in ("response.raw.md", "response.md", "validation.json", "extract_stats.json"):
        p = d / name
        if p.is_file():
            p.unlink()
