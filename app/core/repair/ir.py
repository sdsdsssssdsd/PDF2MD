"""IR-first Repair：阅读顺序 / 图注 / 重复块 / 公式关系 / 表结构。幂等。"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Callable

from app.core.domain.document import (
    BLOCK_FIGURE,
    BLOCK_FORMULA,
    BLOCK_TABLE,
    BLOCK_TEXT,
    DocumentIR,
    Provenance,
    RelationIR,
)
from app.core.repair import RepairTrace

IrRepairFn = Callable[[DocumentIR], DocumentIR]

_CAPTION_RE = re.compile(
    r"^(?:Figure|Fig\.|Table|Tab\.|图|表)\s*[\d一二三四五六七八九十]+",
    re.I,
)
_TAG_RE = re.compile(r"\\tag\{|^\s*\(\d+[a-z]?\)\s*$")


@dataclass(frozen=True)
class IrRepairRule:
    id: str
    phase: str
    deterministic: bool
    enabled: bool
    fn: IrRepairFn


def _normalize_reading_order(document: DocumentIR) -> DocumentIR:
    for index, block in enumerate(document.blocks):
        block.reading_order = index
    return document


def _collapse_duplicate_blocks(document: DocumentIR) -> DocumentIR:
    kept = []
    for block in document.blocks:
        if (
            kept
            and kept[-1].type == block.type
            and kept[-1].page == block.page
            and (kept[-1].content or "").strip() == (block.content or "").strip()
            and (kept[-1].content or "").strip()
        ):
            continue
        kept.append(block)
    document.blocks = kept
    return document


def _associate_captions(document: DocumentIR) -> DocumentIR:
    seen = {(r.kind, r.source_id, r.target_id) for r in document.relations}
    for index, block in enumerate(document.blocks):
        if block.type not in {BLOCK_FIGURE, BLOCK_TABLE}:
            continue
        if index + 1 >= len(document.blocks):
            continue
        nxt = document.blocks[index + 1]
        if nxt.type != BLOCK_TEXT:
            continue
        if not _CAPTION_RE.search((nxt.content or "").strip()):
            continue
        key = ("caption_of", nxt.id, block.id)
        if key in seen:
            continue
        document.relations.append(
            RelationIR(kind="caption_of", source_id=nxt.id, target_id=block.id)
        )
        seen.add(key)
    return document


def _associate_formula_tags(document: DocumentIR) -> DocumentIR:
    seen = {(r.kind, r.source_id, r.target_id) for r in document.relations}
    for index, block in enumerate(document.blocks):
        if block.type != BLOCK_FORMULA:
            continue
        if index + 1 >= len(document.blocks):
            continue
        nxt = document.blocks[index + 1]
        if nxt.type != BLOCK_TEXT:
            continue
        if not _TAG_RE.search((nxt.content or "").strip()):
            continue
        key = ("formula_tag", nxt.id, block.id)
        if key in seen:
            continue
        document.relations.append(
            RelationIR(kind="formula_tag", source_id=nxt.id, target_id=block.id)
        )
        seen.add(key)
    return document


def _mark_inconsistent_tables(document: DocumentIR) -> DocumentIR:
    for block in document.blocks:
        if block.type != BLOCK_TABLE:
            continue
        lines = [ln for ln in (block.content or "").splitlines() if ln.strip().startswith("|")]
        widths = [ln.count("|") for ln in lines]
        if len(set(widths)) > 1:
            block.attributes["table_inconsistent"] = True
        else:
            block.attributes.pop("table_inconsistent", None)
    return document


IR_RULES: tuple[IrRepairRule, ...] = (
    IrRepairRule("duplicate_block", "ir", True, True, _collapse_duplicate_blocks),
    IrRepairRule("reading_order", "ir", True, True, _normalize_reading_order),
    IrRepairRule("caption_association", "ir", True, True, _associate_captions),
    IrRepairRule("formula_relation", "ir", True, True, _associate_formula_tags),
    IrRepairRule("table_structure", "ir", True, True, _mark_inconsistent_tables),
)


def iter_ir_rules(*, enabled_only: bool = True) -> tuple[IrRepairRule, ...]:
    if enabled_only:
        return tuple(r for r in IR_RULES if r.enabled)
    return IR_RULES


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def apply_ir_rules(document: DocumentIR) -> tuple[DocumentIR, tuple[RepairTrace, ...]]:
    traces: list[RepairTrace] = []
    for rule in iter_ir_rules():
        before = _sha(document.to_json())
        document = rule.fn(document)
        after = _sha(document.to_json())
        traces.append(
            RepairTrace(
                rule_id=rule.id,
                before_hash=before,
                after_hash=after,
                changed=before != after,
            )
        )
    if not any(p.stage == "ir_repair" for p in document.provenance):
        document.provenance.append(Provenance(provider="pdf2md.repair.ir", stage="ir_repair"))
    return document, tuple(traces)


def ir_rules_are_idempotent(document: DocumentIR) -> bool:
    once, _ = apply_ir_rules(document)
    twice, _ = apply_ir_rules(once)
    return once.to_json() == twice.to_json()
