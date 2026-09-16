"""ResourceLease：一次占用的可释放句柄。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ResourceLease:
    id: str
    kind: str
    job_id: str
    exclusive: bool = True
    vram_hint_mb: int = 0
    owner: str = ""
    refcount: int = 1
    released: bool = False
    extra: dict[str, Any] = field(default_factory=dict)
    _runtime: Any = field(default=None, repr=False, compare=False)

    def release(self) -> None:
        runtime = self._runtime
        if runtime is not None:
            runtime.release(self)

    def __enter__(self) -> ResourceLease:
        return self

    def __exit__(self, *_exc) -> None:
        self.release()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "job_id": self.job_id,
            "exclusive": self.exclusive,
            "vram_hint_mb": self.vram_hint_mb,
            "owner": self.owner,
            "refcount": self.refcount,
            "released": self.released,
        }


@dataclass
class ResourceBag:
    """单个 Job 持有的资源集合。"""

    job_id: str
    runtime: Any
    leases: list[ResourceLease] = field(default_factory=list)

    def acquire(self, kind: str, **kwargs) -> ResourceLease:
        lease = self.runtime.acquire(kind, job_id=self.job_id, **kwargs)
        if lease not in self.leases:
            self.leases.append(lease)
        return lease
