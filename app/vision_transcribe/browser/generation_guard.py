"""生成完成 / DOM 稳定检测（MutationObserver + BATCH_END）。"""
from __future__ import annotations

import time
from typing import Any

MUTATION_HOOK_JS = """
(() => {
  if (window.__PDF2MD_MUTATION__) return;
  window.__PDF2MD_MUTATION__ = { count: 0, last: Date.now() };
  const bump = () => {
    const s = window.__PDF2MD_MUTATION__;
    s.count += 1;
    s.last = Date.now();
  };
  const attach = (root) => {
    if (!root || root.__pdf2md_obs__) return;
    try {
      const obs = new MutationObserver(bump);
      obs.observe(root, { childList: true, subtree: true, characterData: true });
      root.__pdf2md_obs__ = obs;
    } catch (e) {}
  };
  const tryAttach = () => {
    const nodes = document.querySelectorAll(
      '[data-message-author-role="assistant"], .ds-message, .markdown-body'
    );
    nodes.forEach(attach);
    if (nodes.length) return;
    attach(document.body);
  };
  tryAttach();
  setInterval(tryAttach, 1200);
})();
"""


def install_mutation_observer(context) -> None:
    try:
        context.add_init_script(MUTATION_HOOK_JS)
    except Exception:
        pass


def inject_mutation_observer(page) -> None:
    try:
        page.evaluate(MUTATION_HOOK_JS)
    except Exception:
        pass


def mutation_state(page) -> dict[str, Any]:
    try:
        raw = page.evaluate(
            "() => window.__PDF2MD_MUTATION__ || {count:0,last:0}"
        )
        return raw if isinstance(raw, dict) else {"count": 0, "last": 0}
    except Exception:
        return {"count": 0, "last": 0}


def dom_quiet_ms(page, *, quiet_ms: int = 2500) -> bool:
    state = mutation_state(page)
    try:
        last = float(state.get("last") or 0)
    except (TypeError, ValueError):
        last = 0.0
    if last <= 0:
        return False
    return (time.time() * 1000 - last) >= quiet_ms


def text_has_batch_end(text: str, batch_id: int | None) -> bool:
    if not (text or "").strip():
        return False
    if "<!-- PDF2MD:BATCH_END:" in text or "PDF2MD:BATCH_END:" in text:
        if batch_id is None:
            return True
        token = f"BATCH_END:{batch_id:04d}"
        return token in text
    return False
