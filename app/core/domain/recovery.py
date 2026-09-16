"""RecoveryRequest：QA 驱动的局部恢复，不是整篇换 parser。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.domain.document import BlockIR


class RecoveryScope:
    DOCUMENT = "document"
    PAGE = "page"
    BLOCK = "block"


class ProblemType:
    FORMULA_UNRESOLVED = "formula_unresolved"
    FORMULA_STRUCTURAL = "formula_structural"
    TABLE_STRUCTURE = "table_structure"
    PAGE_COVERAGE = "page_coverage"
    TEXT_LAYER = "text_layer"
    PLACEHOLDER = "placeholder"


class RecoveryStatus:
    PENDING = "pending"
    RESOLVED = "resolved"
    SKIPPED = "skipped"
    EXHAUSTED = "exhausted"
    REFUSED = "refused"


@dataclass
class RecoveryRequest:
    id: str
    scope: str
    required_capability: str
    problem_type: str
    page: int | None = None
    block_ids: tuple[str, ...] = ()
    evidence: dict[str, Any] = field(default_factory=dict)
    budget: int = 1
    attempts: int = 0
    status: str = RecoveryStatus.PENDING
    provider_id: str | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "scope": self.scope,
            "page": self.page,
            "block_ids": list(self.block_ids),
            "problem_type": self.problem_type,
            "required_capability": self.required_capability,
            "budget": self.budget,
            "attempts": self.attempts,
            "status": self.status,
            "provider_id": self.provider_id,
            "reason": self.reason,
            "evidence": dict(self.evidence),
        }


@dataclass
class RecoveryPatch:
    request_id: str
    provider_id: str
    blocks: list[BlockIR] = field(default_factory=list)
    markdown_replacements: dict[str, str] = field(default_factory=dict)
    rebuild_markdown: bool = False


@dataclass
class RecoveryOutcome:
    requests: list[RecoveryRequest]
    document: Any
    markdown: str
    quality: Any
    changed: bool = False
