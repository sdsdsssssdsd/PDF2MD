"""ModelRuntime：daemon / 本地模型生命周期登记。不负责具体推理。"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable


class ModelState:
    UNLOADED = "unloaded"
    LOADING = "loading"
    READY = "ready"
    IDLE = "idle"
    UNHEALTHY = "unhealthy"


HealthFn = Callable[[], dict[str, Any]]
VoidFn = Callable[[], None]


@dataclass
class ModelHandle:
    provider_id: str
    state: str = ModelState.UNLOADED
    pid: int | None = None
    survive_gui_exit: bool = True
    healthcheck: HealthFn | None = field(default=None, repr=False)
    restart: VoidFn | None = field(default=None, repr=False)
    shutdown: VoidFn | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "state": self.state,
            "pid": self.pid,
            "survive_gui_exit": self.survive_gui_exit,
        }


class ModelRuntime:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._models: dict[str, ModelHandle] = {}

    def attach(
        self,
        provider_id: str,
        *,
        pid: int | None = None,
        state: str = ModelState.READY,
        survive_gui_exit: bool = True,
        healthcheck: HealthFn | None = None,
        restart: VoidFn | None = None,
        shutdown: VoidFn | None = None,
    ) -> ModelHandle:
        provider_id = str(provider_id)
        with self._lock:
            handle = self._models.get(provider_id) or ModelHandle(provider_id=provider_id)
            handle.pid = pid if pid is not None else handle.pid
            handle.state = state
            handle.survive_gui_exit = bool(survive_gui_exit)
            if healthcheck is not None:
                handle.healthcheck = healthcheck
            if restart is not None:
                handle.restart = restart
            if shutdown is not None:
                handle.shutdown = shutdown
            self._models[provider_id] = handle
            return handle

    def mark(self, provider_id: str, state: str, *, pid: int | None = None) -> None:
        with self._lock:
            handle = self._models.get(provider_id)
            if handle is None:
                handle = ModelHandle(provider_id=str(provider_id), state=state, pid=pid)
                self._models[provider_id] = handle
                return
            handle.state = state
            if pid is not None:
                handle.pid = pid

    def detach(self, provider_id: str) -> None:
        with self._lock:
            self._models.pop(str(provider_id), None)

    def get(self, provider_id: str) -> ModelHandle | None:
        with self._lock:
            return self._models.get(str(provider_id))

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [h.to_dict() for h in self._models.values()]
