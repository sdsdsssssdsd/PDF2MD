"""Browser 横切：SiteAdapter 契约。实现仍在 vision_transcribe.browser。"""
from app.vision_transcribe.browser.contracts.fingerprint import (
    DEEPSEEK_SITE_ADAPTER,
    INCOMPATIBLE_SITE,
    IncompatibleSiteError,
    SiteAdapterVersion,
    verify_logged_in_contract,
)
from app.vision_transcribe.browser.policies.cooldown import (
    ServerBusyCooldownError,
    server_busy_from_response,
)

__all__ = [
    "DEEPSEEK_SITE_ADAPTER",
    "INCOMPATIBLE_SITE",
    "IncompatibleSiteError",
    "ServerBusyCooldownError",
    "SiteAdapterVersion",
    "server_busy_from_response",
    "verify_logged_in_contract",
]
