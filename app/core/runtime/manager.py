"""ResourceRuntime：GPU / CPU / browser / API / daemon 槽位与进程登记。

第一版只做 Semaphore + ResourceLease + process health + cleanup + 有界并发。
不是 Kubernetes 调度器。CLI 与 GUI 共用进程内单例。
"""
from __future__ import annotations

import atexit
import os
import subprocess
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

from app.core.runtime.kinds import (
    ResourceBusy,
    ResourceCancelled,
    ResourceKind,
)
from app.core.runtime.lease import ResourceBag, ResourceLease
from app.core.runtime.model import ModelRuntime

SCHEMA_VERSION = "1.0"

CancelFn = Callable[[], bool]
StopFn = Callable[[], None]


@dataclass
class ResourceLimits:
    gpu_slots: int = 1
    cpu_slots: int = 4
    browser_slots: int = 1
    api_slots: int = 4
    daemon_slots: int = 2
    gpu_vram_mb: int = 0
    acquire_timeout_seconds: float = 120.0

    def capacity(self, kind: str) -> int:
        mapping = {
            ResourceKind.GPU: max(1, int(self.gpu_slots)),
            ResourceKind.CPU: max(1, int(self.cpu_slots)),
            ResourceKind.BROWSER: max(1, int(self.browser_slots)),
            ResourceKind.API: max(1, int(self.api_slots)),
            ResourceKind.DAEMON: max(1, int(self.daemon_slots)),
        }
        if kind not in mapping:
            raise ValueError(f"unknown resource kind: {kind}")
        return mapping[kind]

    def to_dict(self) -> dict[str, Any]:
        return {
            "gpu_slots": self.gpu_slots,
            "cpu_slots": self.cpu_slots,
            "browser_slots": self.browser_slots,
            "api_slots": self.api_slots,
            "daemon_slots": self.daemon_slots,
            "gpu_vram_mb": self.gpu_vram_mb,
            "acquire_timeout_seconds": self.acquire_timeout_seconds,
        }


@dataclass
class TrackedProcess:
    pid: int
    kind: str
    job_id: str | None = None
    owner: str = ""
    survive_shutdown: bool = False
    allow_kill: bool = False
    stop_fn: StopFn | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pid": self.pid,
            "kind": self.kind,
            "job_id": self.job_id,
            "owner": self.owner,
            "survive_shutdown": self.survive_shutdown,
            "allow_kill": self.allow_kill,
            "alive": _pid_alive(self.pid),
        }


_TLS = threading.local()
_RUNTIME: ResourceRuntime | None = None
_RUNTIME_LOCK = threading.Lock()
_ATEXIT_REGISTERED = False


def current_job_id() -> str | None:
    stack = getattr(_TLS, "stack", None)
    if not stack:
        return None
    return stack[-1]


def _push_job_id(job_id: str) -> None:
    stack = getattr(_TLS, "stack", None)
    if stack is None:
        stack = []
        _TLS.stack = stack
    stack.append(job_id)


def _pop_job_id() -> None:
    stack = getattr(_TLS, "stack", None)
    if stack:
        stack.pop()


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        if os.name == "nt":
            import ctypes

            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False
        os.kill(pid, 0)
        return True
    except OSError:
        return False
    except Exception:
        return False


def _kill_pid(pid: int) -> None:
    if pid <= 0:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid), "/T"],
                capture_output=True,
                timeout=5,
                check=False,
            )
        else:
            os.kill(pid, 9)
    except Exception:
        pass


class ResourceRuntime:
    def __init__(self, limits: ResourceLimits | None = None) -> None:
        self.limits = limits or ResourceLimits()
        self.models = ModelRuntime()
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self._used: dict[str, int] = {kind: 0 for kind in ResourceKind.ALL}
        self._leases: dict[str, ResourceLease] = {}
        self._job_leases: dict[str, list[str]] = {}
        self._processes: dict[int, TrackedProcess] = {}
        self._closed = False

    def acquire(
        self,
        kind: str,
        *,
        job_id: str,
        exclusive: bool = True,
        vram_hint_mb: int = 0,
        timeout: float | None = None,
        owner: str = "",
        cancelled: CancelFn | None = None,
    ) -> ResourceLease:
        kind = str(kind)
        job_id = str(job_id or "")
        if not job_id:
            raise ValueError("job_id required")
        cap = self.limits.capacity(kind)
        wait_s = self.limits.acquire_timeout_seconds if timeout is None else float(timeout)
        deadline = time.monotonic() + wait_s if wait_s >= 0 else None
        with self._cond:
            if self._closed:
                raise ResourceBusy("resource_runtime_closed")
            nested = self._nested_lease(job_id, kind)
            if nested is not None:
                nested.refcount += 1
                return nested
            while True:
                if cancelled and cancelled():
                    raise ResourceCancelled("cancelled")
                if self._used[kind] < cap:
                    break
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise ResourceBusy(f"resource_busy:{kind}")
                    self._cond.wait(timeout=min(0.25, remaining))
                else:
                    self._cond.wait(timeout=0.25)
            self._used[kind] += 1
            lease = ResourceLease(
                id=uuid.uuid4().hex[:12],
                kind=kind,
                job_id=job_id,
                exclusive=bool(exclusive),
                vram_hint_mb=int(vram_hint_mb or 0),
                owner=str(owner or ""),
                _runtime=self,
            )
            self._leases[lease.id] = lease
            self._job_leases.setdefault(job_id, []).append(lease.id)
            return lease

    def release(self, lease: ResourceLease) -> None:
        with self._cond:
            if lease.released:
                return
            lease.refcount = max(0, int(lease.refcount) - 1)
            if lease.refcount > 0:
                return
            lease.released = True
            self._used[lease.kind] = max(0, self._used.get(lease.kind, 0) - 1)
            self._leases.pop(lease.id, None)
            ids = self._job_leases.get(lease.job_id) or []
            self._job_leases[lease.job_id] = [i for i in ids if i != lease.id]
            self._cond.notify_all()

    def end_job(self, job_id: str) -> None:
        job_id = str(job_id or "")
        if not job_id:
            return
        stop_list: list[TrackedProcess] = []
        with self._cond:
            for lid in list(self._job_leases.get(job_id) or []):
                lease = self._leases.pop(lid, None)
                if lease is None:
                    continue
                if not lease.released:
                    self._used[lease.kind] = max(0, self._used.get(lease.kind, 0) - 1)
                lease.refcount = 0
                lease.released = True
            self._job_leases.pop(job_id, None)
            for pid, proc in list(self._processes.items()):
                if proc.job_id == job_id and not proc.survive_shutdown:
                    stop_list.append(self._processes.pop(pid))
            self._cond.notify_all()
        for proc in stop_list:
            self._stop_process(proc)

    def register_process(
        self,
        pid: int,
        *,
        kind: str,
        job_id: str | None = None,
        owner: str = "",
        survive_shutdown: bool = False,
        allow_kill: bool = False,
        stop_fn: StopFn | None = None,
    ) -> TrackedProcess:
        pid = int(pid or 0)
        if pid <= 0:
            raise ValueError("pid required")
        proc = TrackedProcess(
            pid=pid,
            kind=str(kind),
            job_id=job_id,
            owner=str(owner or ""),
            survive_shutdown=bool(survive_shutdown),
            allow_kill=bool(allow_kill),
            stop_fn=stop_fn,
        )
        with self._lock:
            self._processes[pid] = proc
        return proc

    def unregister_process(self, pid: int) -> None:
        with self._lock:
            self._processes.pop(int(pid or 0), None)

    def unregister_owner(self, owner: str) -> None:
        owner = str(owner or "")
        if not owner:
            return
        with self._lock:
            for pid, proc in list(self._processes.items()):
                if proc.owner == owner:
                    self._processes.pop(pid, None)

    @contextmanager
    def job_scope(
        self,
        job_id: str,
        kinds: tuple[str, ...] | list[str] = (),
        *,
        cancelled: CancelFn | None = None,
        timeout: float | None = None,
        owner: str = "",
    ) -> Iterator[ResourceBag]:
        job_id = str(job_id)
        _push_job_id(job_id)
        bag = ResourceBag(job_id=job_id, runtime=self)
        try:
            for kind in kinds:
                bag.acquire(kind, cancelled=cancelled, timeout=timeout, owner=owner)
            yield bag
        finally:
            try:
                self.end_job(job_id)
            finally:
                _pop_job_id()

    def health(self) -> dict[str, Any]:
        with self._lock:
            used = dict(self._used)
            leases = [lease.to_dict() for lease in self._leases.values()]
            processes = [proc.to_dict() for proc in self._processes.values()]
        return {
            "schema_version": SCHEMA_VERSION,
            "limits": self.limits.to_dict(),
            "used": used,
            "leases": leases,
            "processes": processes,
            "models": self.models.snapshot(),
        }

    def shutdown(self, *, keep_daemons: bool = True) -> None:
        stop_list: list[TrackedProcess] = []
        with self._cond:
            for lid, lease in list(self._leases.items()):
                if not lease.released:
                    self._used[lease.kind] = max(0, self._used.get(lease.kind, 0) - 1)
                lease.refcount = 0
                lease.released = True
            self._leases.clear()
            self._job_leases.clear()
            for pid, proc in list(self._processes.items()):
                if keep_daemons and proc.survive_shutdown:
                    continue
                stop_list.append(self._processes.pop(pid))
            if not keep_daemons:
                self._closed = True
            self._cond.notify_all()
        for proc in stop_list:
            self._stop_process(proc)
        if not keep_daemons:
            for handle in list(self.models.snapshot()):
                self.models.detach(str(handle.get("provider_id") or ""))

    def _nested_lease(self, job_id: str, kind: str) -> ResourceLease | None:
        for lid in self._job_leases.get(job_id) or []:
            lease = self._leases.get(lid)
            if lease is not None and lease.kind == kind and not lease.released:
                return lease
        return None

    def _stop_process(self, proc: TrackedProcess) -> None:
        ok = False
        if proc.stop_fn is not None:
            try:
                proc.stop_fn()
                ok = True
            except Exception:
                ok = False
        if not ok and proc.allow_kill:
            _kill_pid(proc.pid)


def _atexit_shutdown() -> None:
    runtime = _RUNTIME
    if runtime is None:
        return
    try:
        runtime.shutdown(keep_daemons=True)
    except Exception:
        pass


def get_runtime() -> ResourceRuntime:
    global _RUNTIME, _ATEXIT_REGISTERED
    with _RUNTIME_LOCK:
        if _RUNTIME is None:
            _RUNTIME = ResourceRuntime()
            if not _ATEXIT_REGISTERED:
                atexit.register(_atexit_shutdown)
                _ATEXIT_REGISTERED = True
        return _RUNTIME


def reset_runtime_for_tests(limits: ResourceLimits | None = None) -> ResourceRuntime:
    global _RUNTIME
    with _RUNTIME_LOCK:
        if _RUNTIME is not None:
            try:
                _RUNTIME.shutdown(keep_daemons=False)
            except Exception:
                pass
        _RUNTIME = ResourceRuntime(limits=limits or ResourceLimits())
        return _RUNTIME
