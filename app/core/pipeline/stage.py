"""Stage 协议：prepare / execute / validate / commit。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


@dataclass
class StageResult:
    name: str
    status: str = "ok"  # ok | failed | skipped
    artifacts: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    retryable: bool = False
    provenance: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.status in {"ok", "skipped"}


class Stage(Protocol):
    name: str

    def execute(self, context: dict[str, Any]) -> StageResult: ...


@dataclass
class CallableStage:
    name: str
    fn: Callable[[dict[str, Any]], StageResult | dict[str, Any] | None]

    def execute(self, context: dict[str, Any]) -> StageResult:
        out = self.fn(context)
        if isinstance(out, StageResult):
            if not out.name:
                out.name = self.name
            return out
        if out is None:
            return StageResult(name=self.name, status="ok")
        if isinstance(out, dict):
            context.update(out)
            return StageResult(name=self.name, status="ok", artifacts=dict(out))
        return StageResult(name=self.name, status="ok", artifacts={"value": out})
