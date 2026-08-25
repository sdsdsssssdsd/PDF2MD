"""保存 CaptureBundle 证据到 batch attempts/（P0）。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.vision_transcribe.capture.models import CaptureBundle, CopyRound
from app.vision_transcribe.manifest import batch_dir


def allocate_attempt_dir(output_dir: Path, batch_id: int) -> Path:
    base = batch_dir(output_dir, batch_id) / "attempts"
    base.mkdir(parents=True, exist_ok=True)
    n = 1
    while (base / f"attempt_{n:03d}").exists():
        n += 1
    d = base / f"attempt_{n:03d}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_text(path: Path, text: str) -> None:
    path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")


def save_capture_bundle(attempt_dir: Path, bundle: CaptureBundle) -> Path:
    attempt_dir.mkdir(parents=True, exist_ok=True)
    for i, rnd in enumerate(bundle.copy_rounds, start=1):
        if rnd.copy_api_text:
            _write_text(attempt_dir / f"copy_api_{i}.md", rnd.copy_api_text)
        if rnd.clipboard_text:
            _write_text(attempt_dir / f"clipboard_{i}.txt", rnd.clipboard_text)
    if bundle.dom_markdown:
        _write_text(attempt_dir / "dom.md", bundle.dom_markdown)
    if bundle.dom_katex:
        _write_text(attempt_dir / "dom_katex.md", bundle.dom_katex)
    if bundle.clipboard_html_md:
        _write_text(attempt_dir / "clipboard_html.md", bundle.clipboard_html_md)
    if bundle.assistant_html:
        _write_text(attempt_dir / "assistant.html", bundle.assistant_html)

    summary: dict[str, Any] = {
        "batch_id": bundle.batch_id,
        "attempt": bundle.attempt,
        "consensus_source": bundle.consensus_source,
        "consensus_stable": bundle.consensus_stable,
        "failure_class": bundle.failure_class,
        "chars": {
            "copy_api": len(bundle.copy_api_selected),
            "clipboard": len(bundle.clipboard_selected),
            "dom_md": len(bundle.dom_markdown),
            "dom_katex": len(bundle.dom_katex),
            "selected": len(bundle.consensus_text),
        },
        "copy_rounds": [
            {
                "round": r.round_index,
                "copy_fired": r.copy_fired,
                "copy_api_chars": len(r.copy_api_text),
                "clipboard_chars": len(r.clipboard_text),
                "generation": r.copy_api_generation,
            }
            for r in bundle.copy_rounds
        ],
        "meta": bundle.meta,
    }
    path = attempt_dir / "capture.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
