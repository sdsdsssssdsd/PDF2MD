"""MarkdownArtifact：格式修正 / 日常识图等非 PDF 产物。不是 DocumentIR。"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"
ARTIFACT_KIND_MARKDOWN = "markdown"


@dataclass
class MarkdownArtifact:
    schema_version: str = SCHEMA_VERSION
    kind: str = ARTIFACT_KIND_MARKDOWN
    workflow: str = ""
    source: str = ""
    path: str = ""
    text: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(self.to_dict())
        payload.pop("text", None)
        payload["chars"] = len(self.text or "")
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return path
