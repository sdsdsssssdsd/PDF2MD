"""按 manifest batch id 顺序合并 accepted 批次。"""
from __future__ import annotations

from pathlib import Path

from app.vision_transcribe.manifest import VisionManifest, batch_dir, vision_dir
from app.vision_transcribe.models import BatchStatus


def merge_accepted_batches(output_dir: Path, manifest: VisionManifest) -> Path:
    parts: list[str] = []
    for b in sorted(manifest.get_batches(), key=lambda x: x.id):
        if b.status != BatchStatus.ACCEPTED.value:
            raise RuntimeError(f"batch {b.id} 状态为 {b.status}，不能合并")
        path = batch_dir(output_dir, b.id) / "response.md"
        if not path.exists():
            raise FileNotFoundError(f"缺少 {path}")
        text = path.read_text(encoding="utf-8").strip()
        if text:
            parts.append(text)
    body = "\n\n".join(parts).rstrip() + "\n"
    out = vision_dir(output_dir) / "document.raw.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    return out
