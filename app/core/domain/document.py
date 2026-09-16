"""统一 Document IR：文本 / 公式 / 表格 / 图片 / bbox / 顺序 / 置信度 / provenance。"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

IR_VERSION = "1.0"
SCHEMA_VERSION = "1.0"

BLOCK_TEXT = "text"
BLOCK_HEADING = "heading"
BLOCK_FORMULA = "formula"
BLOCK_TABLE = "table"
BLOCK_FIGURE = "figure"
BLOCK_CODE = "code"


@dataclass
class BBox:
    x0: float = 0.0
    y0: float = 0.0
    x1: float = 0.0
    y1: float = 0.0
    page: int | None = None


@dataclass
class Provenance:
    provider: str = ""
    stage: str = ""
    source: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class BlockIR:
    id: str
    type: str
    content: str = ""
    page: int | None = None
    bbox: BBox | None = None
    reading_order: int = 0
    raw_content: str = ""
    confidence: float | None = None
    provider: str = ""
    provenance: Provenance = field(default_factory=Provenance)
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class PageIR:
    number: int
    width: float | None = None
    height: float | None = None
    text_layer: bool | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class RelationIR:
    kind: str
    source_id: str
    target_id: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class ArtifactIR:
    kind: str
    path: str
    page: int | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class DocumentIR:
    schema_version: str = SCHEMA_VERSION
    version: str = IR_VERSION
    source: str = ""
    title: str = ""
    pages: list[PageIR] = field(default_factory=list)
    blocks: list[BlockIR] = field(default_factory=list)
    relations: list[RelationIR] = field(default_factory=list)
    artifacts: list[ArtifactIR] = field(default_factory=list)
    provenance: list[Provenance] = field(default_factory=list)
    qa: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["schema_version"] = self.schema_version or SCHEMA_VERSION
        data.pop("qa", None)  # 评价只进 qa.json
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n"

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")
        return path

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DocumentIR:
        pages = [PageIR(**_subset(p, PageIR)) for p in data.get("pages") or []]
        blocks: list[BlockIR] = []
        for raw in data.get("blocks") or []:
            item = dict(raw)
            bbox = item.get("bbox")
            if isinstance(bbox, dict):
                item["bbox"] = BBox(**_subset(bbox, BBox))
            prov = item.get("provenance")
            if isinstance(prov, dict):
                item["provenance"] = Provenance(**_subset(prov, Provenance))
            blocks.append(BlockIR(**_subset(item, BlockIR)))
        relations = [RelationIR(**_subset(r, RelationIR)) for r in data.get("relations") or []]
        artifacts = [ArtifactIR(**_subset(a, ArtifactIR)) for a in data.get("artifacts") or []]
        provenance = [Provenance(**_subset(p, Provenance)) for p in data.get("provenance") or []]
        return cls(
            schema_version=str(data.get("schema_version") or data.get("version") or SCHEMA_VERSION),
            version=str(data.get("version") or data.get("schema_version") or IR_VERSION),
            source=str(data.get("source") or ""),
            title=str(data.get("title") or ""),
            pages=pages,
            blocks=blocks,
            relations=relations,
            artifacts=artifacts,
            provenance=provenance,
            qa=dict(data.get("qa") or {}),
            extra=dict(data.get("extra") or {}),
        )

    @classmethod
    def load(cls, path: Path) -> DocumentIR:
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def to_markdown(self) -> str:
        parts: list[str] = []
        for block in sorted(self.blocks, key=lambda b: b.reading_order):
            if block.type == BLOCK_HEADING:
                level = int(block.attributes.get("level") or 1)
                parts.append("#" * max(1, min(6, level)) + " " + block.content.strip())
            elif block.type == BLOCK_FORMULA:
                body = block.content.strip()
                parts.append("$$\n" + body + "\n$$")
            elif block.type == BLOCK_FIGURE:
                alt = str(block.attributes.get("alt") or "Figure")
                src = str(block.attributes.get("src") or block.content)
                parts.append(f"![{alt}]({src})")
            else:
                parts.append(block.content.rstrip())
        text = "\n\n".join(p for p in parts if p is not None)
        if text and not text.endswith("\n"):
            text += "\n"
        return text


def _subset(data: dict[str, Any], cls: type) -> dict[str, Any]:
    names = getattr(cls, "__dataclass_fields__", {})
    return {k: v for k, v in data.items() if k in names}


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_IMAGE_RE = re.compile(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$")
_TABLE_LINE_RE = re.compile(r"^\s*\|")
_FENCE_RE = re.compile(r"^```")
_PAGE_LINE_RE = re.compile(r"^(?:PAGE\s+(\d+)|<!--\s*PAGE\s+(\d+)\s*-->)\s*$", re.I)


def document_from_markdown(
    markdown: str,
    *,
    source: str = "",
    provider: str = "",
    page_count: int | None = None,
) -> DocumentIR:
    """从现有 Markdown 产物构造 IR（best-effort，不丢正文）。"""
    text = markdown or ""
    lines = text.splitlines()
    blocks: list[BlockIR] = []
    order = 0
    i = 0
    n = len(lines)
    current_page: int | None = None

    def _add(kind: str, content: str, **attrs: Any) -> None:
        nonlocal order
        blocks.append(
            BlockIR(
                id=f"b-{order:04d}-{kind}",
                type=kind,
                content=content,
                page=current_page,
                reading_order=order,
                provider=provider,
                provenance=Provenance(provider=provider, stage="import", source=source),
                attributes=dict(attrs),
            )
        )
        order += 1

    while i < n:
        line = lines[i]
        page_mark = _PAGE_LINE_RE.match(line.strip())
        if page_mark:
            current_page = int(page_mark.group(1) or page_mark.group(2))
            _add(BLOCK_TEXT, line.strip(), page_marker=True)
            i += 1
            continue
        heading = _HEADING_RE.match(line)
        if heading:
            _add(BLOCK_HEADING, heading.group(2), level=len(heading.group(1)))
            i += 1
            continue
        img = _IMAGE_RE.match(line.strip())
        if img:
            _add(BLOCK_FIGURE, img.group(2), alt=img.group(1), src=img.group(2))
            i += 1
            continue
        if line.strip() == "$$":
            body: list[str] = []
            i += 1
            while i < n and lines[i].strip() != "$$":
                body.append(lines[i])
                i += 1
            if i < n:
                i += 1
            _add(BLOCK_FORMULA, "\n".join(body), display=True)
            continue
        if _FENCE_RE.match(line.strip()):
            fence = [line]
            i += 1
            while i < n:
                fence.append(lines[i])
                if _FENCE_RE.match(lines[i].strip()):
                    i += 1
                    break
                i += 1
            _add(BLOCK_CODE, "\n".join(fence))
            continue
        if _TABLE_LINE_RE.match(line):
            table: list[str] = [line]
            i += 1
            while i < n and _TABLE_LINE_RE.match(lines[i]):
                table.append(lines[i])
                i += 1
            _add(BLOCK_TABLE, "\n".join(table))
            continue
        para: list[str] = []
        while i < n:
            cur = lines[i]
            if (
                not cur.strip()
                or _HEADING_RE.match(cur)
                or _IMAGE_RE.match(cur.strip())
                or cur.strip() == "$$"
                or _FENCE_RE.match(cur.strip())
                or _TABLE_LINE_RE.match(cur)
                or _PAGE_LINE_RE.match(cur.strip())
            ):
                break
            para.append(cur)
            i += 1
        if para:
            _add(BLOCK_TEXT, "\n".join(para))
        elif i < n and not lines[i].strip():
            i += 1

    pages = [PageIR(number=p) for p in range(1, (page_count or 0) + 1)]
    return DocumentIR(
        source=source,
        pages=pages,
        blocks=blocks,
        provenance=[Provenance(provider=provider, stage="import", source=source)],
    )
