"""Provider Registry：按 capability 解析。第三方 entry point 默认识别但不加载。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from app.core.providers.descriptor import (
    ProviderDescriptor,
    ProviderHandle,
    ProviderStatus,
    ResolveConstraints,
)

ENTRY_POINT_GROUP = "pdf2md.providers"

AvailableFn = Callable[[], bool]
FactoryFn = Callable[[], Any]


@dataclass
class _Record:
    descriptor: ProviderDescriptor
    factory: FactoryFn | None = None
    available_fn: AvailableFn | None = None
    health_fn: AvailableFn | None = None
    enabled: bool = True
    installed: bool = True
    instance: Any = field(default=None, repr=False)

    def probe_available(self) -> bool:
        if self.available_fn is None:
            return bool(self.installed)
        try:
            return bool(self.available_fn())
        except Exception:
            return False

    def probe_healthy(self, available: bool) -> bool:
        if self.health_fn is None:
            return available
        try:
            return bool(self.health_fn())
        except Exception:
            return False


class ProviderRegistry:
    def __init__(self) -> None:
        self._records: dict[str, _Record] = {}
        self._order: list[str] = []

    def register(
        self,
        descriptor: ProviderDescriptor,
        *,
        factory: FactoryFn | None = None,
        available_fn: AvailableFn | None = None,
        health_fn: AvailableFn | None = None,
        enabled: bool | None = None,
        installed: bool = True,
    ) -> ProviderDescriptor:
        rec = _Record(
            descriptor=descriptor,
            factory=factory,
            available_fn=available_fn,
            health_fn=health_fn,
            enabled=descriptor.default_enabled if enabled is None else bool(enabled),
            installed=bool(installed),
        )
        if descriptor.id not in self._records:
            self._order.append(descriptor.id)
        self._records[descriptor.id] = rec
        return descriptor

    def get(self, provider_id: str) -> ProviderHandle | None:
        rec = self._records.get(provider_id)
        if rec is None:
            return None
        return self._handle(rec)

    def set_enabled(self, provider_id: str, enabled: bool) -> None:
        rec = self._records.get(provider_id)
        if rec is None:
            raise KeyError(provider_id)
        rec.enabled = bool(enabled)

    def status(self, provider_id: str) -> ProviderStatus | None:
        rec = self._records.get(provider_id)
        if rec is None:
            return None
        return self._status(rec)

    def statuses(self) -> list[ProviderStatus]:
        return [self._status(self._records[i]) for i in self._order]

    def resolve(
        self,
        capability: str,
        constraints: ResolveConstraints | None = None,
    ) -> ProviderHandle | None:
        found = self.resolve_all(capability, constraints)
        return found[0] if found else None

    def resolve_all(
        self,
        capability: str,
        constraints: ResolveConstraints | None = None,
    ) -> list[ProviderHandle]:
        c = constraints or ResolveConstraints(capability=capability)
        cap = c.capability or capability
        ranked: list[tuple[int, int, int, ProviderHandle]] = []
        preferred = {pid: i for i, pid in enumerate(c.preferred_ids)}
        for index, pid in enumerate(self._order):
            rec = self._records[pid]
            d = rec.descriptor
            if cap not in d.capabilities:
                continue
            if c.provider_type and d.provider_type != c.provider_type:
                continue
            if c.input_kind and d.supported_inputs and c.input_kind not in d.supported_inputs:
                continue
            if pid in c.exclude_ids:
                continue
            if not rec.installed:
                continue
            if c.require_enabled and not rec.enabled:
                continue
            if not c.allow_experimental and d.experimental:
                continue
            if c.allow_network is False and d.network_required:
                continue
            if c.runtime and c.runtime not in d.runtime:
                continue
            available = rec.probe_available()
            if c.require_available and not available:
                continue
            handle = self._handle(rec, available=available)
            pref = preferred.get(pid, len(preferred) + 1)
            experimental_rank = 1 if d.experimental else 0
            ranked.append((pref, experimental_rank, index, handle))
        ranked.sort(key=lambda item: (item[0], item[1], item[2]))
        return [item[3] for item in ranked]

    def discover_entry_points(self, *, load: bool = False) -> list[str]:
        """只登记 entry point 名称。默认不 load，因此第三方保持 disabled。"""
        found: list[str] = []
        for ep in _iter_entry_points():
            name = str(getattr(ep, "name", "") or "")
            if not name:
                continue
            found.append(name)
            pid = name if name.startswith("parser.") or "." in name else f"plugin.{name}"
            if pid in self._records:
                continue
            desc = ProviderDescriptor(
                id=pid,
                version="unknown",
                provider_type="plugin",
                capabilities=(),
                experimental=True,
                default_enabled=False,
                source="entry_point",
            )
            self.register(
                desc,
                enabled=False,
                installed=True,
                available_fn=lambda: False,
            )
        if load:
            raise RuntimeError("第三方 Provider 默认禁止加载；需显式 load_entry_points(enabled_ids=...)")
        return found

    def load_entry_points(self, *, enabled_ids: list[str] | tuple[str, ...] = ()) -> list[str]:
        """显式白名单才 load。空名单 = 不加载任何第三方。"""
        allowed = {str(x) for x in enabled_ids}
        if not allowed:
            return []
        loaded: list[str] = []
        for ep in _iter_entry_points():
            name = str(getattr(ep, "name", "") or "")
            pid = name if "." in name else f"plugin.{name}"
            if name not in allowed and pid not in allowed:
                continue
            try:
                obj = ep.load()
            except Exception:
                continue
            descriptor = _descriptor_from_loaded(obj, pid)
            if descriptor is None:
                continue
            factory = obj if callable(obj) else (lambda inst=obj: inst)
            available_fn = getattr(obj, "available", None)
            self.register(
                descriptor,
                factory=factory if callable(factory) else None,
                available_fn=available_fn if callable(available_fn) else None,
                enabled=True,
                installed=True,
            )
            loaded.append(descriptor.id)
        return loaded

    def _status(self, rec: _Record, available: bool | None = None) -> ProviderStatus:
        avail = rec.probe_available() if available is None else available
        healthy = rec.probe_healthy(avail)
        reason = ""
        if not rec.installed:
            reason = "not_installed"
        elif not rec.enabled:
            reason = "disabled"
        elif not avail:
            reason = "unavailable"
        elif not healthy:
            reason = "unhealthy"
        return ProviderStatus(
            descriptor=rec.descriptor,
            installed=rec.installed,
            available=avail,
            enabled=rec.enabled,
            healthy=healthy,
            reason=reason,
        )

    def _handle(self, rec: _Record, available: bool | None = None) -> ProviderHandle:
        status = self._status(rec, available=available)
        provider = rec.instance
        if provider is None and rec.factory is not None:
            try:
                provider = rec.factory()
                rec.instance = provider
            except Exception:
                provider = None
        return ProviderHandle(descriptor=rec.descriptor, status=status, provider=provider)


_REGISTRY: ProviderRegistry | None = None


def get_registry() -> ProviderRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = ProviderRegistry()
        from app.core.providers.builtins import register_internal_providers

        register_internal_providers(_REGISTRY)
        _REGISTRY.discover_entry_points(load=False)
    return _REGISTRY


def reset_registry_for_tests() -> None:
    global _REGISTRY
    _REGISTRY = None


def discover() -> dict[str, bool]:
    """兼容旧接口：id → available。不改变默认启用策略。"""
    return {item.id: item.available for item in get_registry().statuses()}


def _iter_entry_points():
    try:
        from importlib.metadata import entry_points
    except Exception:
        return []
    try:
        eps = entry_points()
    except Exception:
        return []
    try:
        if hasattr(eps, "select"):
            return list(eps.select(group=ENTRY_POINT_GROUP))
        return list(eps.get(ENTRY_POINT_GROUP, []))  # type: ignore[arg-type]
    except Exception:
        return []


def _descriptor_from_loaded(obj: Any, fallback_id: str) -> ProviderDescriptor | None:
    raw = getattr(obj, "DESCRIPTOR", None) or getattr(obj, "descriptor", None)
    if callable(raw) and not isinstance(raw, ProviderDescriptor):
        try:
            raw = raw()
        except Exception:
            raw = None
    if isinstance(raw, ProviderDescriptor):
        return raw
    if raw is None and callable(obj):
        try:
            inst = obj()
        except Exception:
            return None
        inner = getattr(inst, "descriptor", None)
        if isinstance(inner, ProviderDescriptor):
            return inner
    return ProviderDescriptor(
        id=fallback_id,
        version="unknown",
        provider_type="plugin",
        capabilities=(),
        experimental=True,
        default_enabled=False,
        source="entry_point",
    )
