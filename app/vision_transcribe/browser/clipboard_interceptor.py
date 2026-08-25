"""在 DeepSeek 页面挂钩 Clipboard API，捕获复制按钮真正写入的内容。

隔离模式（__PDF2MD_CLIPBOARD_ISOLATE__=true）：
  记录 writeText/write 内容，但不调用原始 API → 不污染用户系统剪贴板。
"""
from __future__ import annotations

from typing import Any

CLIPBOARD_HOOK_JS = """
(() => {
  if (window.__PDF2MD_CLIPBOARD_HOOK__) return;
  window.__PDF2MD_CLIPBOARD_HOOK__ = true;
  window.__PDF2MD_CLIPBOARD_ISOLATE__ = true;
  window.__PDF2MD_COPY_CAPTURE__ = { generation: 0, items: [] };

  function record(type, text) {
    const cap = window.__PDF2MD_COPY_CAPTURE__;
    cap.generation += 1;
    const item = {
      id: cap.generation,
      type: type,
      chars: (text || '').length,
      text: text || '',
      ts: Date.now(),
    };
    cap.items.push(item);
    if (cap.items.length > 12) cap.items.shift();
    cap.last = item;
  }

  function isolated() {
    return !!window.__PDF2MD_CLIPBOARD_ISOLATE__;
  }

  if (navigator.clipboard && navigator.clipboard.writeText) {
    const origWriteText = navigator.clipboard.writeText.bind(navigator.clipboard);
    navigator.clipboard.writeText = async (text) => {
      record('writeText', text);
      if (isolated()) return;
      return origWriteText(text);
    };
  }
  if (navigator.clipboard && navigator.clipboard.write) {
    const origWrite = navigator.clipboard.write.bind(navigator.clipboard);
    navigator.clipboard.write = async (items) => {
      let merged = '';
      let html = '';
      try {
        for (const it of items || []) {
          if (it.types && it.types.includes('text/plain')) {
            merged += await it.getType('text/plain').then(r => r.text());
          }
          if (it.types && it.types.includes('text/html')) {
            html += await it.getType('text/html').then(r => r.text());
          }
        }
      } catch (e) {}
      record('write', merged);
      if (html) {
        const cap = window.__PDF2MD_COPY_CAPTURE__;
        if (cap.last) cap.last.html = html;
        cap.lastHtml = html;
      }
      if (isolated()) return;
      return origWrite(items);
    };
  }
  document.addEventListener('copy', (e) => {
    try {
      const sel = window.getSelection && window.getSelection().toString();
      if (sel) record('copy-event', sel);
      if (isolated() && e && e.clipboardData) {
        // 拦截 Ctrl+C / execCommand('copy') 路径，避免写入系统剪贴板
        const text = sel || (e.clipboardData.getData('text/plain') || '');
        if (text) {
          e.clipboardData.setData('text/plain', text);
          e.preventDefault();
          record('copy-event-isolated', text);
        }
      }
    } catch (err) {}
  }, true);
})();
"""


def install_clipboard_interceptor(context) -> None:
    """在 BrowserContext 上注册 init script（新页面自动生效）。"""
    try:
        context.add_init_script(CLIPBOARD_HOOK_JS)
    except Exception:
        pass


def inject_clipboard_interceptor(page) -> None:
    """对已打开页面补注入。"""
    try:
        page.evaluate(CLIPBOARD_HOOK_JS)
    except Exception:
        pass


def set_clipboard_isolate(page, enabled: bool = True) -> None:
    """开启/关闭隔离：隔离时页面 clipboard.write* 不写 OS。"""
    try:
        page.evaluate(
            "(on) => { window.__PDF2MD_CLIPBOARD_ISOLATE__ = !!on; }",
            bool(enabled),
        )
    except Exception:
        pass


def get_copy_capture_state(page) -> dict[str, Any]:
    try:
        raw = page.evaluate(
            "() => window.__PDF2MD_COPY_CAPTURE__ || {generation:0,items:[]}"
        )
        return raw if isinstance(raw, dict) else {"generation": 0, "items": []}
    except Exception:
        return {"generation": 0, "items": []}


def latest_copy_api_text(page) -> str:
    state = get_copy_capture_state(page)
    items = state.get("items") or []
    for item in reversed(items):
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "")
        if text.strip():
            return text
    return ""


def latest_copy_api_html(page) -> str:
    state = get_copy_capture_state(page)
    html = str(state.get("lastHtml") or "")
    if html.strip():
        return html
    items = state.get("items") or []
    for item in reversed(items):
        if not isinstance(item, dict):
            continue
        h = str(item.get("html") or "")
        if h.strip():
            return h
    return ""


def copy_generation(page) -> int:
    state = get_copy_capture_state(page)
    try:
        return int(state.get("generation") or 0)
    except (TypeError, ValueError):
        return 0
