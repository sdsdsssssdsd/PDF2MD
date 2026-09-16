"""Provider 自描述：capability / runtime / 许可 / 隔离。不含具体模型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class Capability:
    PARSE_STRUCTURE = "parse.structure"
    PARSE_TEXT = "parse.text"
    FORMULA_RECOGNITION = "formula.recognition"
    TABLE_STRUCTURE = "table.structure"
    LAYOUT_DETECTION = "layout.detection"
    READING_ORDER = "reading_order"
    VISION_PAGE = "vision.page"
    VISION_REGION = "vision.region"


class RuntimeKind:
    CPU = "cpu"
    CUDA = "cuda"
    BROWSER = "browser"
    API = "api"


class IsolationMode:
    INPROCESS = "inprocess"
    SUBPROCESS = "subprocess"
    DAEMON = "daemon"
    BROWSER = "browser"
    API = "api"


class ProviderType:
    PARSER = "parser"
    FORMULA = "formula"
    VISION = "vision"
    TABLE = "table"
    LAYOUT = "layout"


class ProviderState:
    """四种正交状态，不是线性状态机。"""

    INSTALLED = "installed"
    AVAILABLE = "available"
    ENABLED = "enabled"
    HEALTHY = "healthy"


@dataclass(frozen=True)
class ProviderDescriptor:
    id: str
    version: str
    provider_type: str
    capabilities: tuple[str, ...] = ()
    runtime: tuple[str, ...] = (RuntimeKind.CPU,)
    network_required: bool = False
    dependencies: tuple[str, ...] = ()
    supported_languages: tuple[str, ...] = ("en", "zh")
    supported_inputs: tuple[str, ...] = ("pdf",)
    output_contract: str = "markdown"
    isolation_mode: str = IsolationMode.INPROCESS
    license_class: str = "unknown"
    experimental: bool = False
    default_enabled: bool = True
    source: str = "internal"
    track: str = "supported"

    def has_capability(self, capability: str) -> bool:
        return capability in self.capabilities

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "version": self.version,
            "provider_type": self.provider_type,
            "capabilities": list(self.capabilities),
            "runtime": list(self.runtime),
            "network_required": self.network_required,
            "dependencies": list(self.dependencies),
            "supported_languages": list(self.supported_languages),
            "supported_inputs": list(self.supported_inputs),
            "output_contract": self.output_contract,
            "isolation_mode": self.isolation_mode,
            "license_class": self.license_class,
            "experimental": self.experimental,
            "default_enabled": self.default_enabled,
            "source": self.source,
            "track": self.track,
        }


@dataclass(frozen=True)
class ResolveConstraints:
    capability: str
    runtime: str | None = None
    allow_experimental: bool = False
    allow_network: bool | None = None
    require_enabled: bool = True
    require_available: bool = True
    preferred_ids: tuple[str, ...] = ()
    exclude_ids: tuple[str, ...] = ()
    input_kind: str | None = "pdf"
    provider_type: str | None = None


@dataclass(frozen=True)
class ProviderStatus:
    descriptor: ProviderDescriptor
    installed: bool
    available: bool
    enabled: bool
    healthy: bool
    reason: str = ""

    @property
    def id(self) -> str:
        return self.descriptor.id

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.descriptor.id,
            "installed": self.installed,
            "available": self.available,
            "enabled": self.enabled,
            "healthy": self.healthy,
            "reason": self.reason,
            "experimental": self.descriptor.experimental,
            "source": self.descriptor.source,
            "track": self.descriptor.track,
            "capabilities": list(self.descriptor.capabilities),
        }


@dataclass
class ProviderHandle:
    descriptor: ProviderDescriptor
    status: ProviderStatus
    provider: Any = None

    @property
    def id(self) -> str:
        return self.descriptor.id

    @property
    def short_name(self) -> str:
        ident = self.descriptor.id
        if "." in ident:
            return ident.split(".", 1)[1]
        return ident
