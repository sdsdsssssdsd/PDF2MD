"""定位最后一条 assistant 回答根节点（P3）。"""
from __future__ import annotations

_ASSISTANT_ROOT_JS = """
() => {
  const promptNeedles = ['你正在执行 PDF', '本批次为 PAGE', '高保真内容转录任务'];
  const isUserPrompt = (t) => {
    if (!t) return true;
    let hits = 0;
    for (const s of promptNeedles) if (t.includes(s)) hits++;
    if (hits >= 2 && t.length < 4500) return true;
    if (t.includes('开启新对话') && t.length < 1200) return true;
    return false;
  };
  const sels = [
    '[data-message-author-role="assistant"]',
    '.ds-message',
    '.markdown-body',
    'div[class*="assistant"]',
  ];
  let best = null;
  let bestY = -1;
  for (const sel of sels) {
    for (const el of document.querySelectorAll(sel)) {
      const t = el.innerText || '';
      if (isUserPrompt(t) || t.trim().length < 40) continue;
      const r = el.getBoundingClientRect();
      if (r.height < 8) continue;
      if (r.top >= bestY) {
        bestY = r.top;
        best = el;
      }
    }
  }
  return best ? best.innerText || '' : '';
}
"""


def assistant_text_from_root(page) -> str:
    try:
        t = page.evaluate(_ASSISTANT_ROOT_JS)
        return str(t or "")
    except Exception:
        return ""
