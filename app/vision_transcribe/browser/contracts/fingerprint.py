"""SiteAdapterVersion + DOM contract。大改发 INCOMPATIBLE_SITE，不再无限换 selector。"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

INCOMPATIBLE_SITE = "INCOMPATIBLE_SITE"

# 登录后聊天界面地标。缺光一个可警告；全部缺失才判站点不兼容。
DEEPSEEK_LANDMARKS: tuple[str, ...] = (
    "开启新对话",
    "识图模式",
    "textarea",
    'input[type="file"]',
    '[contenteditable="true"]',
)

DEEPSEEK_SELECTORS: tuple[str, ...] = (
    '[data-message-author-role="assistant"]',
    ".ds-message",
    ".markdown-body",
    'input[type="file"]',
    '[aria-label*="复制"]',
    '[aria-label*="Copy" i]',
)


class IncompatibleSiteError(RuntimeError):
    code = INCOMPATIBLE_SITE

    def __init__(self, message: str = "", *, missing: tuple[str, ...] = ()) -> None:
        text = message or "DeepSeek 页面结构已变化，SiteAdapter 需要更新"
        super().__init__(f"{INCOMPATIBLE_SITE}: {text}")
        self.missing = tuple(missing)


@dataclass(frozen=True)
class SiteAdapterVersion:
    adapter_id: str
    adapter_version: str
    selector_fingerprint: str
    dom_fingerprint: str
    last_verified: str
    site: str = "https://chat.deepseek.com/"

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "selector_fingerprint": self.selector_fingerprint,
            "dom_fingerprint": self.dom_fingerprint,
            "last_verified": self.last_verified,
            "site": self.site,
        }


def fingerprint_selectors(selectors: tuple[str, ...] | list[str]) -> str:
    blob = "\n".join(selectors)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


DEEPSEEK_SITE_ADAPTER = SiteAdapterVersion(
    adapter_id="vision.deepseek_web",
    adapter_version="1.0",
    selector_fingerprint=fingerprint_selectors(DEEPSEEK_SELECTORS),
    dom_fingerprint=fingerprint_selectors(DEEPSEEK_LANDMARKS),
    last_verified="2026-09-16",
)


def _visible(page: Any, factory) -> bool:
    try:
        loc = factory()
        n = loc.count() if hasattr(loc, "count") else 0
        if not isinstance(n, int):
            return False
        if n <= 0:
            return False
        first = loc.first
        if hasattr(first, "is_visible"):
            return bool(first.is_visible())
        return True
    except Exception:
        return False


def landmark_hits(page: Any) -> list[str]:
    if page is None:
        return []
    hits: list[str] = []
    checks = (
        ("开启新对话", lambda: page.get_by_text("开启新对话", exact=True)),
        ("识图模式", lambda: page.get_by_text("识图模式", exact=True)),
        ("textarea", lambda: page.locator("textarea")),
        ("file_input", lambda: page.locator('input[type="file"]')),
        ("contenteditable", lambda: page.locator('[contenteditable="true"]')),
        ("copy", lambda: page.locator('[aria-label*="复制"], [aria-label*="Copy" i], #copyBtn')),
        ("composer", lambda: page.locator("#composer, textarea, [contenteditable='true']")),
    )
    for name, factory in checks:
        if _visible(page, factory):
            hits.append(name)
    return hits


def verify_logged_in_contract(page: Any, *, logged_in: bool) -> list[str]:
    """已登录但聊天地标全无 → INCOMPATIBLE_SITE。未登录交给 NeedsUserError。"""
    if page is None or not logged_in:
        return []
    hits = landmark_hits(page)
    if hits:
        return hits
    raise IncompatibleSiteError(
        "已登录但找不到聊天界面地标（新对话/输入框/识图/复制）",
        missing=DEEPSEEK_LANDMARKS,
    )
