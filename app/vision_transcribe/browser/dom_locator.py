"""DOM 定位描述：从演示录制 → 运行时回放（见 a2-2 语义定位优先）。"""
from __future__ import annotations

import time
from typing import Any, Callable

# 注入页面：点击时生成 locator 描述（Playwright page.evaluate）
_CAPTURE_CLICK_JS = """
() => new Promise((resolve) => {
  const done = (payload) => {
    document.removeEventListener('click', onClick, true);
    resolve(payload);
  };
  const visibleText = (node) => {
    if (!node) return null;
    const t = (node.innerText || node.textContent || '').replace(/\\s+/g, ' ').trim();
    if (!t || t.length > 80) return null;
    return t;
  };
  const implicitRole = (node) => {
    const tag = (node.tagName || '').toLowerCase();
    if (tag === 'button') return 'button';
    if (tag === 'a') return 'link';
    if (tag === 'textarea') return 'textbox';
    if (tag === 'input') {
      const tp = (node.type || 'text').toLowerCase();
      if (tp === 'file') return null;
      return 'textbox';
    }
    return node.getAttribute('role');
  };
  const buildStrategies = (el) => {
    const out = [];
    const seen = new Set();
    const push = (item) => {
      const key = JSON.stringify(item);
      if (seen.has(key)) return;
      seen.add(key);
      out.push(item);
    };
    let node = el;
    for (let depth = 0; node && depth < 6; depth++, node = node.parentElement) {
      const tag = (node.tagName || '').toLowerCase();
      const role = implicitRole(node);
      const aria = (node.getAttribute('aria-label') || '').trim();
      const text = visibleText(node);
      const ph = (node.getAttribute('placeholder') || '').trim();
      const testId = (node.getAttribute('data-testid') || '').trim();
      if (tag === 'input' && (node.type || '').toLowerCase() === 'file') {
        push({ strategy: 'file_input' });
      }
      if (role && aria) push({ strategy: 'role', role, name: aria });
      if (role && text) push({ strategy: 'role', role, name: text });
      if (text) push({ strategy: 'text', text, exact: text.length <= 24 });
      if (ph) push({ strategy: 'placeholder', text: ph });
      if (testId) push({ strategy: 'test_id', value: testId });
    }
    return out;
  };
  const onClick = (e) => {
    const path = (e.composedPath && e.composedPath()) || [e.target];
    const el = path[0] || e.target;
    const strategies = buildStrategies(el);
    done({
      strategies,
      tag: (el.tagName || '').toLowerCase(),
      x: e.clientX,
      y: e.clientY,
    });
  };
  document.addEventListener('click', onClick, true);
})
"""

# 录制 3 步必填；发送钮空内容时灰色，可选第 4 步录蓝色箭头
RECORD_GUIDE_STEPS: list[tuple[str, str, str]] = [
    ("new_chat", "click", "请点击侧栏「开启新对话」"),
    ("vision_mode", "click", "请点击「识图模式」（快速/专家/识图 三按钮最右）"),
    (
        "prompt",
        "click",
        "请点击 Prompt 输入框（仅记录位置；不用打字）",
    ),
]

RECORD_OPTIONAL_STEPS: list[tuple[str, str, str]] = [
    (
        "send",
        "click",
        "先在输入框输入 test 让发送变亮 → 再点右侧蓝色向上箭头",
    ),
]

# 回放时在录制步骤之后自动：填 Prompt -> 上传 -> 等发送可点 -> 发送
RUNTIME_AUTO_STEPS: list[tuple[str, str]] = [
    ("auto_fill_prompt", "fill"),
    ("auto_upload", "upload_files"),
    ("auto_send", "click"),
]


def locator_from_descriptor(page, desc: dict[str, Any]):
    """将单条描述转为 Playwright Locator（可能 count=0）。"""
    strategy = str(desc.get("strategy") or "")
    if strategy == "role":
        return page.get_by_role(
            str(desc.get("role") or ""),
            name=str(desc.get("name") or ""),
            exact=bool(desc.get("exact", True)),
        )
    if strategy == "text":
        return page.get_by_text(
            str(desc.get("text") or ""),
            exact=bool(desc.get("exact", False)),
        )
    if strategy == "placeholder":
        return page.get_by_placeholder(str(desc.get("text") or ""))
    if strategy == "label":
        return page.get_by_label(str(desc.get("text") or ""))
    if strategy == "test_id":
        return page.get_by_test_id(str(desc.get("value") or ""))
    if strategy == "file_input":
        return page.locator('input[type="file"]')
    if strategy == "css":
        return page.locator(str(desc.get("selector") or ""))
    return None


def pick_locator(page, descriptors: list[dict[str, Any]] | None):
    """按优先级选第一个可见 locator。"""
    for desc in descriptors or []:
        try:
            loc = locator_from_descriptor(page, desc)
            if loc is None:
                continue
            if loc.count() <= 0:
                continue
            target = loc.first
            if target.is_visible():
                return target
        except Exception:
            continue
    return None


def click_by_descriptors(
    page,
    descriptors: list[dict[str, Any]] | None,
    *,
    log: Callable[[str], None] | None = None,
    timeout_ms: int = 8000,
) -> bool:
    target = pick_locator(page, descriptors)
    if target is None:
        return False
    try:
        target.scroll_into_view_if_needed(timeout=3000)
        target.click(timeout=timeout_ms)
        if log:
            log(f"[录制回放] 点击成功: {_brief_desc(descriptors)}")
        return True
    except Exception as e:
        try:
            target.click(force=True, timeout=timeout_ms)
            if log:
                log(f"[录制回放] 强制点击: {_brief_desc(descriptors)}")
            return True
        except Exception:
            if log:
                log(f"[录制回放] 点击失败: {e}")
            return False


_PROMPT_PLACEHOLDERS: tuple[str, ...] = (
    "给 DeepSeek 发送消息",
    "使用识图模式开始对话",
    "Message DeepSeek",
)


def _composer_locator_factories(page):
    """仅返回可输入的 composer 定位器（避免误点「深度思考」等工具栏）。"""
    for ph in _PROMPT_PLACEHOLDERS:
        yield lambda p=ph: page.get_by_placeholder(p)
    yield lambda: page.locator("textarea:visible")
    yield lambda: page.get_by_role("textbox")
    yield lambda: page.locator('[contenteditable="true"]:visible')


def _pick_composer_locator(page):
    """取页面最靠下的可见输入框（主聊天 composer）。"""
    best = None
    best_y = -1.0
    for selector in ("textarea", '[contenteditable="true"]'):
        try:
            loc = page.locator(selector)
            for i in range(min(loc.count(), 10)):
                el = loc.nth(i)
                if not el.is_visible():
                    continue
                box = el.bounding_box()
                if not box or float(box.get("height", 0)) < 16:
                    continue
                y = float(box.get("y", 0))
                if y >= best_y:
                    best_y = y
                    best = el
        except Exception:
            continue
    for ph in _PROMPT_PLACEHOLDERS:
        try:
            loc = page.get_by_placeholder(ph)
            if loc.count() <= 0 or not loc.first.is_visible():
                continue
            box = loc.first.bounding_box()
            y = float((box or {}).get("y", 0))
            if y >= best_y:
                best_y = y
                best = loc.first
        except Exception:
            continue
    return best


_FILL_REACT_JS = """
(text) => {
  const vh = window.innerHeight;
  const candidates = [...document.querySelectorAll('textarea, [contenteditable="true"]')];
  const visible = candidates.filter((el) => {
    const r = el.getBoundingClientRect();
    return r.height >= 20 && r.top > vh * 0.35 && r.width > 80;
  });
  visible.sort((a, b) => b.getBoundingClientRect().top - a.getBoundingClientRect().top);
  const el = visible[0];
  if (!el) return false;
  el.focus();
  if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {
    const proto = el.tagName === 'TEXTAREA'
      ? window.HTMLTextAreaElement.prototype
      : window.HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
    if (setter) setter.call(el, text);
    else el.value = text;
  } else {
    el.textContent = text;
  }
  el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
  const val = (el.value ?? el.textContent ?? '').toString();
  const need = Math.min(24, text.trim().length);
  return need === 0 || val.includes(text.trim().slice(0, need));
}
"""


def _fill_via_react(page, text: str) -> bool:
    try:
        return bool(page.evaluate(_FILL_REACT_JS, text))
    except Exception:
        return False


def _read_composer_text(page) -> str:
    for factory in _composer_locator_factories(page):
        try:
            loc = factory()
            if loc.count() <= 0:
                continue
            el = loc.first
            if not el.is_visible():
                continue
            try:
                val = el.input_value(timeout=1000)
                if val and val.strip():
                    return val
            except Exception:
                pass
            try:
                val = el.inner_text(timeout=1000)
                if val and val.strip():
                    return val
            except Exception:
                pass
        except Exception:
            continue
    return ""


def prompt_present_in_composer(page, text: str, *, min_chars: int = 24) -> bool:
    """填写后校验：composer 内应包含 Prompt 开头片段。"""
    snippet = (text or "").strip()
    if not snippet:
        return True
    need = min(min_chars, len(snippet))
    probe = snippet[:need]
    return probe in _read_composer_text(page)


def fill_batch_prompt(
    page,
    text: str,
    *,
    recorded_locators: list[dict[str, Any]] | None = None,
    log: Callable[[str], None] | None = None,
) -> bool:
    """填写 batch Prompt：优先真实输入框，填写后校验内容。"""
    snippet = (text or "").strip()
    if not snippet:
        if log:
            log("[录制回放] Prompt 为空，跳过填写")
        return True

    if is_ai_generating(page):
        if log:
            log("[录制回放] AI 生成中，不触碰输入框")
        return True

    def _ok(where: str) -> bool:
        if log:
            log(f"[录制回放] 已填写 Prompt（{len(text)} 字符，{where}，已校验）")
        return True

    def _try_fill(target, where: str) -> bool:
        try:
            target.scroll_into_view_if_needed(timeout=3000)
            target.click(timeout=5000)
            target.fill(text, timeout=15_000)
            if prompt_present_in_composer(page, text):
                return _ok(where)
        except Exception:
            pass
        try:
            target.click(timeout=5000)
            page.keyboard.press("Control+A")
            page.keyboard.insert_text(text)
            if prompt_present_in_composer(page, text):
                return _ok(f"{where}+键入")
        except Exception:
            pass
        return False

    if _fill_via_react(page, text) and prompt_present_in_composer(page, text):
        return _ok("React")

    composer = _pick_composer_locator(page)
    if composer is not None and _try_fill(composer, "composer"):
        return True

    for factory in _composer_locator_factories(page):
        try:
            loc = factory()
            if loc.count() > 0 and loc.first.is_visible() and _try_fill(loc.first, "输入框"):
                return True
        except Exception:
            continue

    for desc in recorded_locators or []:
        if str(desc.get("strategy") or "") not in ("placeholder", "css", "test_id"):
            continue
        try:
            loc = locator_from_descriptor(page, desc)
            if loc is None or loc.count() <= 0:
                continue
            if not loc.first.is_visible():
                continue
            if _try_fill(loc.first, "录制定位"):
                return True
        except Exception:
            continue

    if log:
        cur = _read_composer_text(page)
        preview = (cur[:60] + "…") if len(cur) > 60 else cur
        log(f"[录制回放] 填写 Prompt 失败（当前框内: {preview!r}）")
    return False


def ensure_batch_prompt(
    page,
    text: str,
    *,
    recorded_locators: list[dict[str, Any]] | None = None,
    log: Callable[[str], None] | None = None,
) -> bool:
    """先填 Prompt；若已存在则跳过。"""
    if prompt_present_in_composer(page, text):
        if log:
            log("[录制回放] Prompt 已在输入框内")
        return True
    return fill_batch_prompt(page, text, recorded_locators=recorded_locators, log=log)


def fill_by_descriptors(
    page,
    descriptors: list[dict[str, Any]] | None,
    text: str,
    *,
    log: Callable[[str], None] | None = None,
    timeout_ms: int = 8000,
) -> bool:
    del timeout_ms  # 保留签名；实际走 fill_batch_prompt
    return fill_batch_prompt(page, text, recorded_locators=descriptors, log=log)


def upload_files_by_descriptors(
    page,
    file_paths: list[str],
    descriptors: list[dict[str, Any]] | None,
    *,
    log: Callable[[str], None] | None = None,
) -> bool:
    """运行时上传：优先 set_input_files（仅触发上传，完成需 wait_for_upload_settled）。"""
    if not file_paths:
        return False
    # 1) 直接找 file input
    try:
        inputs = page.locator('input[type="file"]')
        if inputs.count() > 0:
            inputs.first.set_input_files(file_paths)
            if log:
                log(f"[录制回放] 已选择 {len(file_paths)} 张（等发送变蓝=上传完成）")
            return True
    except Exception:
        pass
    # 2) 录制时点的附件按钮 → file chooser
    target = pick_locator(page, descriptors)
    if target is None:
        return False
    try:
        with page.expect_file_chooser(timeout=8000) as fc:
            target.click(timeout=8000)
        fc.value.set_files(file_paths)
        if log:
            log(f"[录制回放] 已选择 {len(file_paths)} 张（等发送变蓝=上传完成）")
        return True
    except Exception as e:
        if log:
            log(f"[录制回放] 上传失败: {e}")
        return False


def wait_for_upload_settled(
    page,
    expected_files: int,
    *,
    log: Callable[[str], None] | None = None,
    timeout_ms: int = 180_000,
    config: dict | None = None,
) -> bool:
    """上传完成：以发送箭头灰→蓝为准（不再数缩略图）。"""
    from app.vision_transcribe.browser.deepseek_ui import (
        load_ui_config,
        wait_for_send_blue_ready,
    )

    _ = expected_files  # 兼容旧调用
    cfg = config or load_ui_config()
    ok = wait_for_send_blue_ready(
        page,
        config=cfg,
        log=log,
        timeout_ms=timeout_ms,
    )
    if ok and log:
        log("[录制回放] 上传就绪（发送键已变蓝）")
    elif not ok and log:
        log("[录制回放] 等待发送变蓝超时（继续尝试发送）")
    return ok


_IS_AI_GENERATING_JS = """
() => {
  const vh = window.innerHeight;
  const isStopIcon = (el) => {
    if (!el) return false;
    const label = (el.getAttribute('aria-label') || el.innerText || '').trim();
    if (/停止|stop/i.test(label)) return true;
    const svg = el.querySelector && el.querySelector('svg');
    if (!svg) return false;
    const rect = svg.querySelector('rect');
    if (!rect) return false;
    const rr = rect.getBoundingClientRect();
    const er = el.getBoundingClientRect();
    if (rr.width < 4 || rr.height < 4) return false;
    if (rr.width > er.width * 0.55 || rr.height > er.height * 0.55) return false;
    const rcx = rr.left + rr.width / 2;
    const rcy = rr.top + rr.height / 2;
    const ecx = er.left + er.width / 2;
    const ecy = er.top + er.height / 2;
    if (Math.abs(rcx - ecx) > er.width * 0.22) return false;
    if (Math.abs(rcy - ecy) > er.height * 0.22) return false;
    return er.top > vh * 0.52;
  };
  const nodes = document.querySelectorAll('button,[role="button"],div,span');
  for (const el of nodes) {
    const r = el.getBoundingClientRect();
    if (r.width < 20 || r.top < vh * 0.52) continue;
    if (isStopIcon(el)) return true;
  }
  return false;
}
"""


_IS_STOP_CONTROL_AT_JS = """
([x, y]) => {
  const vh = window.innerHeight;
  const isStopIcon = (el) => {
    if (!el) return false;
    const label = (el.getAttribute('aria-label') || el.innerText || '').trim();
    if (/停止|stop/i.test(label)) return true;
    const svg = el.querySelector && el.querySelector('svg');
    if (!svg) return false;
    const rect = svg.querySelector('rect');
    if (!rect) return false;
    const rr = rect.getBoundingClientRect();
    const er = el.getBoundingClientRect();
    if (rr.width < 4 || rr.height < 4) return false;
    if (rr.width > er.width * 0.55 || rr.height > er.height * 0.55) return false;
    const rcx = rr.left + rr.width / 2;
    const rcy = rr.top + rr.height / 2;
    const ecx = er.left + er.width / 2;
    const ecy = er.top + er.height / 2;
    if (Math.abs(rcx - ecx) > er.width * 0.22) return false;
    if (Math.abs(rcy - ecy) > er.height * 0.22) return false;
    return er.top > vh * 0.52;
  };
  let node = document.elementFromPoint(x, y);
  for (let i = 0; i < 8 && node; i++) {
    if (isStopIcon(node)) return true;
    node = node.parentElement;
  }
  return false;
}
"""


def is_ai_generating(page) -> bool:
    """DeepSeek 正在输出：composer 右下角为「停止」钮，不可再点发送/输入框。"""
    try:
        if page.evaluate(_IS_AI_GENERATING_JS):
            return True
    except Exception:
        pass
    for factory in (
        lambda: page.get_by_role("button", name="停止生成"),
        lambda: page.get_by_role("button", name="停止"),
        lambda: page.get_by_role("button", name="Stop"),
        lambda: page.get_by_text("停止生成", exact=False),
        lambda: page.locator('[aria-label*="停止"]'),
    ):
        try:
            loc = factory()
            if loc.count() > 0 and loc.first.is_visible():
                return True
        except Exception:
            continue
    return False


def is_confirmed_stop_at(page, x: float, y: float) -> bool:
    """仅在坐标处确认为停止钮（发送阶段勿用全页 is_ai_generating 误判）。"""
    try:
        if page.evaluate(_IS_STOP_CONTROL_AT_JS, [float(x), float(y)]):
            return True
    except Exception:
        pass
    try:
        from app.vision_transcribe.browser.deepseek_ui import is_stop_image_confirmed_at

        return is_stop_image_confirmed_at(page, x, y)
    except Exception:
        return False


def is_stop_composer_control(page, x: float, y: float) -> bool:
    """坐标处是否为生成中的「停止」钮（非发送箭头）。"""
    return is_confirmed_stop_at(page, x, y)


_COMPOSER_SEND_TARGET_JS = """
() => {
  const vh = window.innerHeight;
  const skip = /^(深度思考|智能搜索|DeepThink|Search)$/i;
  const isStopIcon = (el) => {
    const label = (el.getAttribute('aria-label') || el.innerText || '').trim();
    if (/停止|stop/i.test(label)) return true;
    const svg = el.querySelector && el.querySelector('svg');
    if (!svg) return false;
    const rect = svg.querySelector('rect');
    if (!rect) return false;
    const hasPath = !!svg.querySelector('path');
    // 停止钮：居中小方块；发送箭头常带 path，勿一律排除
    if (hasPath) return false;
    const rr = rect.getBoundingClientRect();
    const er = el.getBoundingClientRect();
    if (rr.width < 4 || rr.height < 4) return false;
    if (rr.width > er.width * 0.55 || rr.height > er.height * 0.55) return false;
    return true;
  };
  const ph = document.querySelector(
    'textarea,[placeholder*="DeepSeek"],[placeholder*="识图"],[contenteditable="true"]'
  );
  let root = ph;
  for (let i = 0; i < 12 && root; i++) {
    if (
      root.querySelector &&
      root.querySelector('textarea,[contenteditable="true"]') &&
      (root.querySelector('button') ||
        root.querySelector('[role="button"]') ||
        root.querySelector('svg'))
    ) {
      break;
    }
    root = root.parentElement;
  }
  const scope = root || document.body;
  document.querySelectorAll('[data-pdf2md-send]').forEach((el) => {
    el.removeAttribute('data-pdf2md-send');
  });

  const score = (el) => {
    const r = el.getBoundingClientRect();
    if (r.width < 20 || r.height < 20) return null;
    if (r.top < vh * 0.52) return null;
    if (isStopIcon(el)) return null;
    const label = (el.innerText || el.getAttribute('aria-label') || '').trim();
    if (skip.test(label)) return null;
    if (label.length > 10 && !/send|发送/i.test(label)) return null;
    if (el.disabled || el.getAttribute('aria-disabled') === 'true') return null;
    const st = getComputedStyle(el);
    if (st.pointerEvents === 'none' || st.visibility === 'hidden' || st.display === 'none') {
      return null;
    }
    const op = parseFloat(st.opacity || '1');
    if (op < 0.45) return null;
    const hasSvg = !!el.querySelector('svg');
    const compact = r.width <= 64 && r.height <= 64;
    const sendish = hasSvg && compact;
    let s = r.right * 10;
    if (sendish) s += 8000;
    if (/send|发送/i.test(label)) s += 4000;
    if (compact) s += 1500;
    return { el, r, s, op, sendish };
  };

  const nodes = new Set();
  scope.querySelectorAll('button,[role="button"]').forEach((el) => nodes.add(el));
  scope.querySelectorAll('div, span').forEach((el) => {
    const r = el.getBoundingClientRect();
    if (r.width < 24 || r.width > 64 || r.height < 24 || r.height > 64) return;
    if (r.top < vh * 0.52) return;
    if (!el.querySelector('svg')) return;
    if (isStopIcon(el)) return;
    const label = (el.innerText || el.getAttribute('aria-label') || '').trim();
    if (skip.test(label)) return;
    nodes.add(el);
  });

  const cand = [...nodes].map(score).filter(Boolean).sort((a, b) => b.s - a.s);
  if (!cand.length) return null;
  const best = cand[0];
  best.el.setAttribute('data-pdf2md-send', '1');
  return {
    x: best.r.left + best.r.width / 2,
    y: best.r.top + best.r.height / 2,
    ready: best.sendish && best.op >= 0.75,
    opacity: best.op,
    sendish: best.sendish,
  };
}
"""


def _get_composer_send_target(page) -> dict[str, Any] | None:
    try:
        hit = page.evaluate(_COMPOSER_SEND_TARGET_JS)
        if isinstance(hit, dict) and hit.get("x") is not None:
            return hit
    except Exception:
        pass
    return None


def _mouse_click_send_xy(
    page,
    x: float,
    y: float,
    *,
    log=None,
    label: str = "坐标",
) -> bool:
    """真实鼠标点击（React 对 force/dispatch 常无响应）。"""
    try:
        if is_confirmed_stop_at(page, float(x), float(y)):
            if log:
                log(f"[录制回放] {label} 落在停止钮，跳过")
            return False
        page.mouse.move(float(x), float(y))
        page.wait_for_timeout(40)
        page.mouse.click(float(x), float(y), delay=80)
        if log:
            log(f"[录制回放] 发送（{label} mouse @ {int(x)},{int(y)}）")
        return True
    except Exception as e:
        if log:
            log(f"[录制回放] mouse 点击失败: {e}")
        return False


def _click_composer_send_target(page, hit: dict[str, Any], *, log=None) -> bool:
    """优先真实鼠标点发送箭头坐标；DOM force 仅作兜底。"""
    if hit.get("x") is not None and hit.get("y") is not None:
        if _mouse_click_send_xy(
            page, float(hit["x"]), float(hit["y"]), log=log, label="蓝色箭头"
        ):
            return True
    try:
        marked = page.locator('[data-pdf2md-send="1"]')
        if marked.count() > 0 and marked.first.is_visible():
            box = marked.first.bounding_box()
            if box:
                cx = box["x"] + box["width"] / 2
                cy = box["y"] + box["height"] / 2
                if _mouse_click_send_xy(page, cx, cy, log=log, label="DOM 盒心"):
                    return True
            try:
                marked.first.click(timeout=5000, delay=80)
                if log:
                    log("[录制回放] 发送（DOM locator）")
                return True
            except Exception:
                pass
    except Exception:
        pass
    return False


_CLICK_ELEMENT_AT_POINT_JS = """
([x, y]) => {
  const target = document.elementFromPoint(x, y);
  if (!target) return false;
  const fire = (node, type) => {
    const opts = {
      bubbles: true,
      cancelable: true,
      view: window,
      clientX: x,
      clientY: y,
      pointerId: 1,
      pointerType: 'mouse',
      isPrimary: true,
      button: 0,
      buttons: type === 'pointerdown' ? 1 : 0,
    };
    node.dispatchEvent(new PointerEvent(type, opts));
    node.dispatchEvent(new MouseEvent(type, opts));
  };
  let node = target;
  for (let i = 0; i < 8 && node; i++) {
    const r = node.getBoundingClientRect();
    const hasSvg = !!(node.querySelector && node.querySelector('svg'));
    const compact =
      r.width >= 18 && r.width <= 84 && r.height >= 18 && r.height <= 84;
    if (hasSvg && compact) {
      try {
        node.scrollIntoView({ block: 'center', inline: 'center' });
      } catch (e) {}
      fire(node, 'pointerdown');
      fire(node, 'pointerup');
      fire(node, 'click');
      if (typeof node.click === 'function') node.click();
      return true;
    }
    node = node.parentElement;
  }
  if (typeof target.click === 'function') {
    target.click();
    return true;
  }
  return false;
}
"""


def _click_element_at_point(
    page,
    x: float,
    y: float,
    *,
    log=None,
    label: str = "坐标",
) -> bool:
    """在页面坐标处找到可点元素并触发完整 pointer/click 事件。"""
    try:
        ok = page.evaluate(_CLICK_ELEMENT_AT_POINT_JS, [x, y])
        if ok:
            if log:
                log(f"[录制回放] 发送（{label} elementFromPoint @ {int(x)},{int(y)}）")
            return True
    except Exception:
        pass
    try:
        page.mouse.move(x, y)
        page.mouse.down()
        page.wait_for_timeout(100)
        page.mouse.up()
        if log:
            log(f"[录制回放] 发送（{label} mouse press @ {int(x)},{int(y)}）")
        return True
    except Exception:
        return False


def _verify_send_dispatched(page) -> bool:
    """点击后是否已进入发送/生成（停止钮出现，或发送键不再可点）。"""
    time.sleep(0.25)
    deadline = time.monotonic() + 2.5
    while time.monotonic() < deadline:
        if is_ai_generating(page):
            return True
        for factory in (
            lambda: page.get_by_role("button", name="停止生成"),
            lambda: page.get_by_role("button", name="停止"),
            lambda: page.locator("button", has_text="停止"),
            lambda: page.locator('[aria-label*="停止"]'),
        ):
            try:
                loc = factory()
                if loc.count() > 0 and loc.first.is_visible():
                    return True
            except Exception:
                continue
        hit = _get_composer_send_target(page)
        if hit is None:
            # 发送钮消失（变停止）也算成功
            if is_ai_generating(page):
                return True
        elif hit:
            op = float(hit.get("opacity") or 0)
            if hit.get("sendish") and op < 0.72:
                return True
            if not hit.get("ready") and op < 0.65:
                return True
        time.sleep(0.15)
    return False


def click_send_robust(
    page,
    *,
    anchor: tuple[int, int, int, int] | None = None,
    log=None,
) -> bool:
    """定位后用真实鼠标点击；必须确认进入生成才算成功。"""
    attempts: list[str] = []

    hit = _get_composer_send_target(page)
    if hit and hit.get("x") is not None:
        if _mouse_click_send_xy(
            page, float(hit["x"]), float(hit["y"]), log=log, label="蓝色箭头"
        ):
            attempts.append("mouse")
            if _verify_send_dispatched(page):
                if log:
                    log("[录制回放] 发送已确认（进入生成）")
                return True
            if log:
                log("[录制回放] 已点发送但未进入生成，继续尝试…")
            from app.vision_transcribe.browser.deepseek_ui import (
                click_retry_user_bubble_if_visible,
            )

            if click_retry_user_bubble_if_visible(page, log=log):
                attempts.append("retry-user-bubble")
                time.sleep(0.45)
                if _verify_send_dispatched(page):
                    if log:
                        log("[录制回放] 用户气泡重试后已进入生成")
                    return True

    if anchor is not None:
        cx, cy, _tw, _th = anchor
        if is_confirmed_stop_at(page, float(cx), float(cy)):
            if log:
                log("[录制回放] 锚点已是停止钮")
            return True
        if _mouse_click_send_xy(page, float(cx), float(cy), log=log, label="模板锚点"):
            attempts.append("anchor")
            if _verify_send_dispatched(page):
                if log:
                    log("[录制回放] 发送已确认（锚点）")
                return True

    hit = _get_composer_send_target(page)
    if hit and _click_composer_send_target(page, hit, log=log):
        attempts.append("dom")
        if _verify_send_dispatched(page):
            return True

    if _try_keyboard_send(page, log=log):
        attempts.append("keyboard")
        if _verify_send_dispatched(page):
            return True
        # Enter 有时也延迟生效，再等一轮
        time.sleep(0.6)
        if _verify_send_dispatched(page):
            return True

    from app.vision_transcribe.browser.deepseek_ui import (
        click_regenerate_retry_if_visible,
    )

    if click_regenerate_retry_if_visible(page, log=log):
        attempts.append("retry-template")
        time.sleep(0.45)
        if _verify_send_dispatched(page):
            if log:
                log("[录制回放] 图识别重试后已进入生成")
            return True

    if log:
        hint = "/".join(attempts) if attempts else "无"
        log(f"[录制回放] 发送未确认（已试: {hint}）")
    return False


def is_send_button_ready(page) -> bool:
    """发送箭头已变亮可点（排除深度思考/智能搜索等工具栏按钮）。"""
    hit = _get_composer_send_target(page)
    if not hit:
        return False
    if hit.get("sendish") and float(hit.get("opacity") or 0) >= 0.75:
        return True
    return bool(hit.get("ready"))


def wait_for_send_ready(
    page,
    *,
    log: Callable[[str], None] | None = None,
    timeout_ms: int = 120_000,
) -> bool:
    """轮询直到发送钮变亮（图片+文字都就绪后）。"""
    deadline = time.monotonic() + timeout_ms / 1000.0
    last_log = 0.0
    while time.monotonic() < deadline:
        if is_send_button_ready(page):
            if log:
                log("[录制回放] 发送按钮已就绪")
            return True
        now = time.monotonic()
        if log and now - last_log > 3.0:
            log("[录制回放] 等待发送按钮变亮（图片可能仍在上传）…")
            last_log = now
        time.sleep(0.5)
    if log:
        log("[录制回放] 等待发送就绪超时")
    return False


def capture_click_descriptor(page, *, timeout_ms: int = 120_000) -> dict[str, Any]:
    """等待用户在页面点一次，返回 strategies 描述。"""
    try:
        page.set_default_timeout(int(timeout_ms))
        return page.evaluate(_CAPTURE_CLICK_JS)
    finally:
        try:
            page.set_default_timeout(30_000)
        except Exception:
            pass


def inject_record_banner(page, *, step_id: str, hint: str) -> None:
    """在页面顶部显示当前录制步骤提示。"""
    page.evaluate(
        """([stepId, hint]) => {
          const id = '__pdf2md_record_banner__';
          let el = document.getElementById(id);
          if (!el) {
            el = document.createElement('div');
            el.id = id;
            el.style.cssText = [
              'position:fixed','top:0','left:0','right:0','z-index:2147483647',
              'background:#1a56db','color:#fff','padding:10px 16px',
              'font:14px/1.4 \"Microsoft YaHei UI\",sans-serif',
              'box-shadow:0 2px 8px rgba(0,0,0,.25)','pointer-events:none'
            ].join(';');
            document.documentElement.appendChild(el);
          }
          el.textContent = `[录制 ${stepId}] ${hint} — 请点击目标元素`;
        }""",
        [step_id, hint],
    )


def click_new_chat_fallback(page, *, log=None) -> bool:
    for factory in (
        lambda: page.get_by_text("开启新对话", exact=True),
        lambda: page.get_by_role("button", name="开启新对话"),
        lambda: page.get_by_text("新建对话", exact=False),
    ):
        try:
            loc = factory()
            if loc.count() > 0 and loc.first.is_visible():
                loc.first.click(timeout=8000)
                if log:
                    log("[录制回放] 兜底: 开启新对话")
                return True
        except Exception:
            continue
    return False


def click_vision_mode_tab(page, *, log=None) -> bool:
    """点击「识图模式」标签（优先精确匹配，避免误点专家/快速）。"""
    labels = ("识图模式", "图片理解", "图像理解", "识图")
    for label in labels:
        for role in ("tab", "radio", "button"):
            try:
                loc = page.get_by_role(role, name=label)
                for i in range(min(loc.count(), 8)):
                    el = loc.nth(i)
                    if not el.is_visible():
                        continue
                    box = el.bounding_box()
                    if not box or float(box.get("width", 0)) < 16:
                        continue
                    el.scroll_into_view_if_needed(timeout=3000)
                    el.click(timeout=8000)
                    if log:
                        log(f"[识图模式] 已点击 {role}: {label}")
                    return True
            except Exception:
                continue
        try:
            loc = page.get_by_text(label, exact=True)
            for i in range(min(loc.count(), 10)):
                el = loc.nth(i)
                if not el.is_visible():
                    continue
                box = el.bounding_box()
                if not box or float(box.get("width", 0)) < 16:
                    continue
                el.scroll_into_view_if_needed(timeout=3000)
                el.click(timeout=8000)
                if log:
                    log(f"[识图模式] 已点击文本: {label}")
                return True
        except Exception:
            continue
    return False


def click_vision_mode_fallback(page, *, log=None) -> bool:
    if click_vision_mode_tab(page, log=log):
        return True
    labels = ("识图模式", "专家模式", "快速模式")
    visible: list[tuple[float, object]] = []
    for label in labels:
        try:
            loc = page.get_by_text(label, exact=True)
            for i in range(min(loc.count(), 5)):
                el = loc.nth(i)
                if not el.is_visible():
                    continue
                box = el.bounding_box()
                if box and box.get("width", 0) >= 20:
                    visible.append((float(box["x"]), el))
        except Exception:
            continue
    if not visible:
        return False
    visible.sort(key=lambda t: t[0])
    target = visible[-1]
    try:
        target[1].click(timeout=8000)
        if log:
            log("[录制回放] 兜底: 识图模式（最右）")
        return True
    except Exception:
        return False


def click_send_fallback(
    page,
    *,
    log=None,
    timeout_ms: int = 90_000,
    config: dict | None = None,
) -> bool:
    """发送：图识别等变蓝 → DOM 实点（非裸坐标）→ Enter。"""
    from app.vision_transcribe.browser.deepseek_ui import (
        load_ui_config,
        wait_and_click_send,
    )

    cfg = config or load_ui_config()
    if wait_and_click_send(page, config=cfg, log=log, timeout_ms=timeout_ms):
        return True

    if click_send_robust(page, log=log):
        return True

    if log:
        log("[录制回放] 发送失败（可重校准 send.png）")
    return False


def _click_send_by_composer_arrow(page, *, log=None) -> bool:
    """点输入区最右侧蓝色向上箭头（兼容 div+svg）。"""
    hit = _get_composer_send_target(page)
    if not hit:
        return False
    return _click_composer_send_target(page, hit, log=log)


def _try_keyboard_send(page, *, log=None) -> bool:
    """聚焦输入框后 Enter / Ctrl+Enter。"""
    if is_ai_generating(page):
        return False
    try:
        for factory in (
            lambda: page.get_by_placeholder("使用识图模式开始对话"),
            lambda: page.get_by_placeholder("给 DeepSeek 发送消息"),
            lambda: page.locator("textarea"),
            lambda: page.locator('[contenteditable="true"]'),
        ):
            loc = factory()
            if loc.count() == 0:
                continue
            box = loc.first
            if not box.is_visible():
                continue
            box.click(timeout=3000)
            for key in ("Enter", "Control+Enter"):
                page.keyboard.press(key)
                time.sleep(0.35)
            if log:
                log("[录制回放] 发送（Enter / Ctrl+Enter）")
            return True
    except Exception:
        pass
    return False


def click_send_when_ready(
    page,
    step: dict[str, Any] | None = None,
    *,
    log=None,
    timeout_ms: int = 120_000,
) -> bool:
    """等图片+Prompt 就绪、发送变亮后再点（可多次轮询）。"""
    locators = list((step or {}).get("locators") or [])
    if locators:
        target = pick_locator(page, locators)
        if target is not None:
            deadline = time.monotonic() + timeout_ms / 1000.0
            while time.monotonic() < deadline:
                if not is_send_button_ready(page):
                    time.sleep(0.5)
                    continue
                try:
                    if target.is_visible() and target.is_enabled():
                        target.click(timeout=5000, delay=100, force=True)
                        if log:
                            log("[录制回放] 发送（录制定位）")
                        if _verify_send_dispatched(page):
                            return True
                        if log:
                            log("[录制回放] 录制定位点击未确认，改用 DOM 发送")
                except Exception:
                    pass
                if click_send_robust(page, log=log) and _verify_send_dispatched(page):
                    return True
                time.sleep(0.5)
    return click_send_fallback(page, log=log, timeout_ms=timeout_ms)


def fill_prompt_fallback(page, text: str, *, log=None) -> bool:
    return fill_batch_prompt(page, text, log=log)


def _brief_desc(descriptors: list[dict[str, Any]] | None) -> str:
    if not descriptors:
        return "?"
    d0 = descriptors[0]
    s = d0.get("strategy")
    if s == "role":
        return f"role={d0.get('role')} name={d0.get('name')}"
    if s == "text":
        return f"text={d0.get('text')}"
    return str(s)
