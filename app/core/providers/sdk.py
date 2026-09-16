"""Plugin SDK：第三方只登记 Descriptor，默认 disabled，不改 Router。"""
from __future__ import annotations

from app.core.providers.descriptor import (
    Capability,
    IsolationMode,
    ProviderDescriptor,
    ProviderType,
    RuntimeKind,
)
from app.core.providers.promotion import PromotionTrack


def make_experimental_descriptor(
    *,
    provider_id: str,
    provider_type: str = ProviderType.PARSER,
    capabilities: tuple[str, ...] = (Capability.PARSE_TEXT,),
    license_class: str = "unknown",
    version: str = "0.1",
) -> ProviderDescriptor:
    """插件作者入口。登记后仍须过五门晋级，不能凭 benchmark 直接变默认。"""
    return ProviderDescriptor(
        id=provider_id,
        version=version,
        provider_type=provider_type,
        capabilities=capabilities,
        runtime=(RuntimeKind.CPU,),
        isolation_mode=IsolationMode.INPROCESS,
        license_class=license_class,
        experimental=True,
        default_enabled=False,
        source="plugin",
        track=PromotionTrack.EXPERIMENTAL,
    )
