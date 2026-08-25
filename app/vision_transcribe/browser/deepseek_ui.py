"""DeepSeek 网页 UI：三层定位（见 a2-2.md）

auto 模式优先级：
  1. Playwright DOM Locator（role / text / label）
  2. 截图模板匹配（OpenCV）
  3. 失败 → 由调用方触发 NEEDS_USER（不用固定坐标作为主流程）

固定坐标仅当 click_strategy == \"coord\" 时启用（调试用）。
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np

from app.utils.paths import APP_ROOT
from app.vision_transcribe.browser.profile_utils import (
    DEEPSEEK_SEND_POLL_MS_DEFAULT,
    DEEPSEEK_SEND_POLL_MS_MIN,
    DEEPSEEK_VIEWPORT_HEIGHT,
    DEEPSEEK_VIEWPORT_WIDTH,
)

DEFAULT_UI_CONFIG = APP_ROOT / "data" / "deepseek_ui.json"
DEFAULT_TEMPLATES_DIR = APP_ROOT / "data" / "deepseek_templates"

DomClickFn = Callable[[list, bool], bool]


def load_ui_config(path: Path | None = None) -> dict[str, Any]:
    p = path or DEFAULT_UI_CONFIG
    if not p.exists():
        return _default_config()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return _default_config()


def save_ui_config(data: dict[str, Any], path: Path | None = None) -> Path:
    p = path or DEFAULT_UI_CONFIG
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def _default_config() -> dict[str, Any]:
    return {
        "version": 1,
        "click_strategy": "auto",
        "match_threshold": 0.72,
        "templates": {},
        "clicks": {},
        "recorded_workflow": {"enabled": False, "steps": []},
    }


def has_recorded_workflow(cfg: dict[str, Any] | None = None) -> bool:
    from app.vision_transcribe.browser.dom_replay import workflow_enabled

    return workflow_enabled(cfg or load_ui_config())


def _template_path(cfg: dict, key: str) -> Path | None:
    templates = cfg.get("templates") or {}
    entry = templates.get(key)
    if not entry:
        p = DEFAULT_TEMPLATES_DIR / f"{key}.png"
        return p if p.exists() else None
    if isinstance(entry, str):
        return Path(entry)
    file = entry.get("file") if isinstance(entry, dict) else None
    if not file:
        return None
    path = Path(file)
    if not path.is_absolute():
        path = APP_ROOT / path
    return path if path.exists() else None


def _page_screenshot_bgr(page) -> np.ndarray:
    png = page.screenshot(type="png", animations="disabled")
    arr = np.frombuffer(png, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError("无法截取页面")
    return img


def _crop_screen_roi(
    screen: np.ndarray,
    roi: tuple[float, float, float, float] | list[float],
) -> tuple[np.ndarray, tuple[int, int]]:
    sh, sw = screen.shape[:2]
    rx0, ry0, rx1, ry1 = [float(v) for v in roi]
    x0 = int(max(0, min(sw - 1, sw * rx0)))
    y0 = int(max(0, min(sh - 1, sh * ry0)))
    x1 = int(max(x0 + 8, min(sw, sw * rx1)))
    y1 = int(max(y0 + 8, min(sh, sh * ry1)))
    return screen[y0:y1, x0:x1], (x0, y0)


def _best_template_on_bgr(
    crop: np.ndarray,
    tpl: np.ndarray,
    *,
    offset: tuple[int, int] = (0, 0),
    scales: tuple[float, ...] = (0.85, 0.92, 1.0, 1.08, 1.15),
) -> tuple[float, int, int, int, int] | None:
    """返回最佳匹配（含低于阈值），供诊断日志；无有效结果时 None。"""
    best: tuple[float, int, int, int, int] | None = None
    th0, tw0 = tpl.shape[:2]
    for scale in scales:
        tw = max(8, int(tw0 * scale))
        th = max(8, int(th0 * scale))
        if th > crop.shape[0] or tw > crop.shape[1]:
            continue
        piece = cv2.resize(tpl, (tw, th)) if scale != 1.0 else tpl
        res = cv2.matchTemplate(crop, piece, cv2.TM_CCOEFF_NORMED)
        _min, max_val, _min_loc, max_loc = cv2.minMaxLoc(res)
        if best is None or max_val > best[0]:
            best = (float(max_val), int(max_loc[0]), int(max_loc[1]), tw, th)
    if best is None:
        return None
    score, lx, ly, tw, th = best
    cx = int(offset[0] + lx + tw / 2)
    cy = int(offset[1] + ly + th / 2)
    return score, cx, cy, tw, th


def _match_template_on_bgr(
    crop: np.ndarray,
    tpl: np.ndarray,
    *,
    threshold: float,
    offset: tuple[int, int] = (0, 0),
    scales: tuple[float, ...] = (0.85, 0.92, 1.0, 1.08, 1.15),
) -> tuple[float, int, int, int, int] | None:
    best = _best_template_on_bgr(crop, tpl, offset=offset, scales=scales)
    if best is None or best[0] < threshold:
        return None
    return best


def _probe_template_best(
    page,
    key: str,
    *,
    config: dict | None = None,
    screen: np.ndarray | None = None,
) -> tuple[float, float, bool] | None:
    """探测模板最佳分：返回 (best_score, threshold, hit)。模板缺失时 None。"""
    cfg = config or load_ui_config()
    tpl_path = _template_path(cfg, key)
    if tpl_path is None:
        return None
    tpl = cv2.imread(str(tpl_path))
    if tpl is None:
        return None
    entry = _template_entry(cfg, key)
    threshold = float(entry.get("threshold") or cfg.get("match_threshold", 0.68))
    roi = entry.get("search_roi")
    try:
        bgr = screen if screen is not None else _page_screenshot_bgr(page)
    except Exception:
        return None
    if roi:
        crop, offset = _crop_screen_roi(bgr, roi)
    else:
        crop, offset = bgr, (0, 0)
    best = _best_template_on_bgr(
        crop,
        tpl,
        offset=offset,
        scales=(0.85, 0.92, 1.0, 1.08, 1.15),
    )
    if best is None:
        return 0.0, threshold, False
    return best[0], threshold, best[0] >= threshold


def _send_gray_template_path(cfg: dict[str, Any]) -> Path | None:
    entry = (cfg.get("templates") or {}).get("send") or {}
    if isinstance(entry, dict) and entry.get("gray_file"):
        path = Path(str(entry["gray_file"]))
        if not path.is_absolute():
            path = APP_ROOT / path
        if path.exists():
            return path
    fallback = DEFAULT_TEMPLATES_DIR / "send_gray.png"
    return fallback if fallback.exists() else None


def _send_patch_bgr_metrics(
    screen_bgr: np.ndarray,
    cx: int,
    cy: int,
    tw: int,
    th: int,
) -> tuple[float, float, float] | None:
    """取发送箭头 ROI 的 BGR 统计（b=蓝通道 p70，g/r=均值）。"""
    sh, sw = screen_bgr.shape[:2]
    pad = max(4, min(tw, th) // 6)
    x0 = max(0, cx - tw // 2 - pad)
    x1 = min(sw, cx + tw // 2 + pad)
    y0 = max(0, cy - th // 2 - pad)
    y1 = min(sh, cy + th // 2 + pad)
    patch = screen_bgr[y0:y1, x0:x1]
    if patch.size == 0:
        return None
    b = float(np.percentile(patch[:, :, 0], 70))
    g = float(patch[:, :, 1].mean())
    r = float(patch[:, :, 2].mean())
    return b, g, r


def _patch_looks_like_gray_send(
    screen_bgr: np.ndarray,
    cx: int,
    cy: int,
    tw: int,
    th: int,
) -> bool:
    """禁用发送键：淡紫蓝（send_gray）或中性浅灰，均非可发送的饱和蓝。"""
    if _patch_looks_like_enabled_send(screen_bgr, cx, cy, tw, th):
        return False
    metrics = _send_patch_bgr_metrics(screen_bgr, cx, cy, tw, th)
    if metrics is None:
        return False
    b, g, r = metrics
    spread = max(b, g, r) - min(b, g, r)
    b_minus_r = b - r
    b_minus_g = b - g
    # DeepSeek 禁用态：高 B 但偏粉紫、B-R/B-G 差小（非 send.png 饱和蓝）
    if b >= 160 and b_minus_r <= 72 and b_minus_g <= 58 and spread <= 90:
        return True
    # 空输入时的中性浅灰
    return spread <= 42 and b <= 125 and abs(b - g) <= 18


def _patch_send_state(
    screen_bgr: np.ndarray,
    cx: int,
    cy: int,
    tw: int,
    th: int,
) -> str:
    if _patch_looks_like_enabled_send(screen_bgr, cx, cy, tw, th):
        return "blue"
    if _patch_looks_like_gray_send(screen_bgr, cx, cy, tw, th):
        return "gray"
    return "unknown"


_SEND_STATE_JS = """
([cx, cy, tw, th]) => {
  const parseRgb = (s) => {
    if (!s) return null;
    const m = String(s).match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
    return m ? { r: +m[1], g: +m[2], b: +m[3] } : null;
  };
  const sampleEl = (el) => {
    if (!el) return null;
    const st = getComputedStyle(el);
    for (const k of ['backgroundColor', 'color']) {
      const c = parseRgb(st[k]);
      if (c && (c.r + c.g + c.b) > 30) return c;
    }
    if (el.getAttribute) {
      const c = parseRgb(el.getAttribute('fill')) || parseRgb(el.getAttribute('stroke'));
      if (c) return c;
    }
    return null;
  };
  const samples = [];
  const pts = [
    [0, 0], [-tw * 0.2, 0], [tw * 0.2, 0],
    [0, -th * 0.2], [0, th * 0.2],
  ];
  for (const [dx, dy] of pts) {
    let node = document.elementFromPoint(cx + dx, cy + dy);
    for (let i = 0; i < 7 && node; i++) {
      const c = sampleEl(node);
      if (c) samples.push(c);
      node = node.parentElement;
    }
  }
  if (!samples.length) return 'unknown';
  const b = Math.max(...samples.map((s) => s.b));
  const r = samples.reduce((a, s) => a + s.r, 0) / samples.length;
  const g = samples.reduce((a, s) => a + s.g, 0) / samples.length;
  const bMinusR = b - r;
  const bMinusG = b - g;
  if (b >= 120 && bMinusR >= 75 && bMinusG >= 45 && g <= 175) return 'blue';
  if (b >= 160 && bMinusR <= 72 && bMinusG <= 58) return 'gray';
  const spread = Math.max(b, g, r) - Math.min(b, g, r);
  if (spread <= 42 && b <= 125 && Math.abs(b - g) <= 18) return 'gray';
  return 'unknown';
}
"""


def _send_state_via_page(page, cx: int, cy: int, tw: int, th: int) -> str:
    """不发全页截图，用 DOM 取色判断发送箭头灰/蓝。"""
    try:
        state = page.evaluate(_SEND_STATE_JS, [int(cx), int(cy), int(tw), int(th)])
        if state in ("blue", "gray", "unknown"):
            return str(state)
    except Exception:
        pass
    return "unknown"


def _locate_send_anchor_via_screenshot(
    page,
    templates: list[np.ndarray],
    roi: list[float],
    *,
    locate_threshold: float,
) -> tuple[int, int, int, int] | None:
    screen = _page_screenshot_bgr(page)
    hit = _locate_send_best_template(
        screen, templates, roi, threshold=locate_threshold
    )
    if hit is None:
        return None
    _score, cx, cy, tw, th = hit
    return cx, cy, tw, th


def _poll_send_blue_state(
    page,
    templates: list[np.ndarray],
    roi: list[float],
    *,
    locate_threshold: float,
    anchor: tuple[int, int, int, int] | None,
    anchor_miss: int,
) -> tuple[tuple[int, int, int, int] | None, str, int]:
    """返回 (anchor, state, anchor_miss)。有 anchor 时不再全页截图。"""
    if anchor is not None:
        cx, cy, tw, th = anchor
        state = _send_state_via_page(page, cx, cy, tw, th)
        if state == "unknown":
            try:
                screen = _page_screenshot_bgr(page)
                state = _patch_send_state(screen, cx, cy, tw, th)
            except Exception:
                pass
        if state != "unknown":
            state = _send_state_not_stop_button(page, anchor, state)
            return anchor, state, 0
        anchor_miss += 1
        if anchor_miss < 4:
            return anchor, "unknown", anchor_miss

    located = _locate_send_anchor_via_screenshot(
        page, templates, roi, locate_threshold=locate_threshold
    )
    if located is None:
        return anchor, "unknown", anchor_miss + 1
    cx, cy, tw, th = located
    state = _send_state_via_page(page, cx, cy, tw, th)
    if state == "unknown":
        screen = _page_screenshot_bgr(page)
        state = _patch_send_state(screen, cx, cy, tw, th)
    state = _send_state_not_stop_button(page, (cx, cy, tw, th), state)
    return (cx, cy, tw, th), state, 0


def _send_state_not_stop_button(
    page,
    anchor: tuple[int, int, int, int],
    state: str,
) -> str:
    """蓝色停止钮与发送钮同色：仅当锚点处确认为停止钮才改状态。"""
    if state != "blue":
        return state
    cx, cy, tw, th = anchor
    try:
        from app.vision_transcribe.browser.dom_locator import is_confirmed_stop_at

        if is_confirmed_stop_at(page, float(cx), float(cy)):
            return "generating"
    except Exception:
        pass
    return state


def locate_send_button_on_screen(
    screen_bgr: np.ndarray,
    tpl: np.ndarray,
    roi: tuple[float, float, float, float] | list[float],
    *,
    threshold: float = 0.55,
) -> tuple[int, int, int, int] | None:
    """在截图中定位发送箭头位置（灰色/蓝色均可，用于后续变色检测）。"""
    hit = _locate_send_best_template(screen_bgr, [tpl], roi, threshold=threshold)
    if hit is None:
        return None
    _score, cx, cy, tw, th = hit
    return cx, cy, tw, th


def _locate_send_best_template(
    screen_bgr: np.ndarray,
    templates: list[np.ndarray],
    roi: tuple[float, float, float, float] | list[float],
    *,
    threshold: float = 0.55,
) -> tuple[float, int, int, int, int] | None:
    crop, offset = _crop_screen_roi(screen_bgr, roi)
    best: tuple[float, int, int, int, int] | None = None
    for tpl in templates:
        if tpl is None:
            continue
        hit = _match_template_on_bgr(
            crop,
            tpl,
            threshold=threshold,
            offset=offset,
            scales=(0.90, 0.96, 1.0, 1.06),
        )
        if hit is not None and (best is None or hit[0] > best[0]):
            best = hit
    return best


def _patch_looks_like_enabled_send(
    screen_bgr: np.ndarray,
    cx: int,
    cy: int,
    tw: int,
    th: int,
) -> bool:
    """可发送的饱和蓝（send.png）；淡紫蓝禁用态不算。"""
    metrics = _send_patch_bgr_metrics(screen_bgr, cx, cy, tw, th)
    if metrics is None:
        return False
    b, g, r = metrics
    b_minus_r = b - r
    b_minus_g = b - g
    return b >= 120 and b_minus_r >= 75 and b_minus_g >= 45 and g <= 175


def _send_template_match_scores(
    screen_bgr: np.ndarray,
    cfg: dict[str, Any],
) -> tuple[float, float, tuple[float, int, int, int, int] | None]:
    """分别匹配 send_gray / send 模板，返回 (gray_score, blue_score, best_hit)。"""
    tpl_blue_path, tpl_gray_path, roi, locate_threshold, _poll = _send_template_config(cfg)
    gray_score = 0.0
    blue_score = 0.0
    best_hit: tuple[float, int, int, int, int] | None = None
    for label, path in (("gray", tpl_gray_path), ("blue", tpl_blue_path)):
        if path is None:
            continue
        tpl = cv2.imread(str(path))
        if tpl is None:
            continue
        hit = _locate_send_best_template(
            screen_bgr, [tpl], roi, threshold=locate_threshold
        )
        if hit is None:
            continue
        if label == "gray":
            gray_score = hit[0]
        else:
            blue_score = hit[0]
        if best_hit is None or hit[0] > best_hit[0]:
            best_hit = hit
    return gray_score, blue_score, best_hit


def _send_template_config(
    cfg: dict[str, Any],
) -> tuple[Path | None, Path | None, list[float], float, int]:
    tpl_blue = _template_path(cfg, "send")
    tpl_gray = _send_gray_template_path(cfg)
    entry = (cfg.get("templates") or {}).get("send") or {}
    roi_raw = entry.get("search_roi") if isinstance(entry, dict) else None
    roi = list(roi_raw or [0.62, 0.70, 1.0, 1.0])
    locate_threshold = float(
        entry.get("locate_threshold") if isinstance(entry, dict) and entry.get("locate_threshold") else 0.55
    )
    poll_ms = int(
        entry.get("poll_ms")
        if isinstance(entry, dict) and entry.get("poll_ms")
        else DEEPSEEK_SEND_POLL_MS_DEFAULT
    )
    return tpl_blue, tpl_gray, roi, locate_threshold, max(DEEPSEEK_SEND_POLL_MS_MIN, poll_ms)


def _load_send_template_images(cfg: dict[str, Any]) -> tuple[list[np.ndarray], list[float], float, int]:
    tpl_blue_path, tpl_gray_path, roi, locate_threshold, poll_ms = _send_template_config(cfg)
    templates: list[np.ndarray] = []
    if tpl_gray_path is not None:
        gray = cv2.imread(str(tpl_gray_path))
        if gray is not None:
            templates.append(gray)
    if tpl_blue_path is not None:
        blue = cv2.imread(str(tpl_blue_path))
        if blue is not None:
            templates.append(blue)
    return templates, roi, locate_threshold, poll_ms


def wait_for_send_blue_ready(
    page,
    *,
    config: dict | None = None,
    log=None,
    timeout_ms: int = 180_000,
) -> bool:
    """等发送箭头变蓝（图片上传 + Prompt 就绪的可发送信号）。"""
    cfg = config or load_ui_config()
    templates, roi, locate_threshold, poll_ms = _load_send_template_images(cfg)
    if not templates:
        if log:
            log("[UI L2] 缺少 send_gray.png / send.png 模板")
        return False

    deadline = time.monotonic() + timeout_ms / 1000.0
    poll_s = poll_ms / 1000.0
    anchor: tuple[int, int, int, int] | None = None
    anchor_miss = 0
    last_log = 0.0
    saw_gray = False

    while time.monotonic() < deadline:
        try:
            from app.vision_transcribe.browser.upload_guard import (
                raise_if_upload_server_busy,
            )

            raise_if_upload_server_busy(page, log=log)
        except Exception as e:
            from app.vision_transcribe.browser.base import ServerBusyCooldownError

            if isinstance(e, ServerBusyCooldownError):
                raise
        try:
            from app.vision_transcribe.browser.dom_locator import is_send_button_ready

            if is_send_button_ready(page):
                if log:
                    log("[UI L2] 发送钮已就绪（DOM）")
                return True
        except Exception:
            pass
        anchor, state, anchor_miss = _poll_send_blue_state(
            page,
            templates,
            roi,
            locate_threshold=locate_threshold,
            anchor=anchor,
            anchor_miss=anchor_miss,
        )
        if anchor and state == "blue":
            if log:
                hint = "灰→蓝" if saw_gray else "已变蓝"
                log(f"[UI L2] 发送{hint}，就绪")
            return True
        if state == "gray":
            saw_gray = True

        now = time.monotonic()
        if log and now - last_log > 4.0:
            state_hint = "灰色" if saw_gray else "等待中"
            log(f"[UI L2] 等待发送变蓝（{state_hint}，{int(poll_ms)}ms/拍）")
            last_log = now
        time.sleep(poll_s)

    if log:
        log("[UI L2] 等待发送变蓝超时")
    return False


def wait_and_click_send(
    page,
    *,
    config: dict | None = None,
    log=None,
    timeout_ms: int = 120_000,
) -> bool:
    """灰→蓝后立即点击发送。"""
    cfg = config or load_ui_config()
    templates, roi, locate_threshold, poll_ms = _load_send_template_images(cfg)
    if not templates:
        if log:
            log("[UI L2] 缺少 send_gray.png / send.png 模板")
        return False

    deadline = time.monotonic() + timeout_ms / 1000.0
    poll_s = poll_ms / 1000.0
    anchor: tuple[int, int, int, int] | None = None
    anchor_miss = 0
    last_log = 0.0
    saw_gray = False

    while time.monotonic() < deadline:
        try:
            from app.vision_transcribe.browser.dom_locator import (
                click_send_robust,
                is_send_button_ready,
            )

            if is_send_button_ready(page):
                if log:
                    log("[UI L2] 发送钮已就绪（DOM），立即点击")
                if click_send_robust(page, anchor=anchor, log=log):
                    return True
                anchor = None
                anchor_miss = 0
        except Exception:
            pass
        anchor, state, anchor_miss = _poll_send_blue_state(
            page,
            templates,
            roi,
            locate_threshold=locate_threshold,
            anchor=anchor,
            anchor_miss=anchor_miss,
        )
        if anchor and state == "blue":
            cx, cy, tw, th = anchor
            from app.vision_transcribe.browser.dom_locator import (
                click_send_robust,
                is_confirmed_stop_at,
            )

            if is_confirmed_stop_at(page, float(cx), float(cy)):
                if log:
                    log("[UI L2] 锚点已是停止钮（已在生成）")
                return True
            if log:
                hint = "灰→蓝" if saw_gray else "已就绪"
                log(f"[UI L2] 发送{hint}，DOM 点击（模板锚点 @ {cx},{cy}）")

            for attempt in range(1, 4):
                if click_send_robust(page, anchor=anchor, log=log):
                    return True
                if log:
                    log(f"[UI L2] 发送未成功，重试 {attempt}/3")
                time.sleep(0.35)
            anchor = None
            anchor_miss = 0
        if state == "generating":
            if log:
                log("[UI L2] 锚点为停止钮，等待发送窗口")
            time.sleep(poll_s)
            continue
        if state == "gray":
            saw_gray = True

        now = time.monotonic()
        if log and now - last_log > 4.0:
            state_hint = "灰色" if saw_gray else "定位中"
            log(f"[UI L2] 等待发送变蓝（当前{state_hint}，{int(poll_ms)}ms/拍）")
            last_log = now
        time.sleep(poll_s)

    if log:
        log("[UI L2] 等待发送变蓝超时")
    return False


def match_template_on_page(
    page,
    template_path: Path,
    *,
    threshold: float = 0.72,
    roi: tuple[float, float, float, float] | list[float] | None = None,
    require_blue: bool = False,
    scales: tuple[float, ...] = (0.85, 0.92, 1.0, 1.08, 1.15),
) -> tuple[float, int, int] | None:
    """在页面截图中匹配模板；roi 为归一化 (x0,y0,x1,y1) 搜索区域。"""
    if not template_path.exists():
        return None
    screen = _page_screenshot_bgr(page)
    tpl = cv2.imread(str(template_path))
    if tpl is None:
        return None
    if roi:
        crop, offset = _crop_screen_roi(screen, roi)
    else:
        crop, offset = screen, (0, 0)

    hit = _match_template_on_bgr(
        crop,
        tpl,
        threshold=threshold,
        offset=offset,
        scales=scales,
    )
    if hit is None:
        return None
    score, cx, cy, tw, th = hit
    if require_blue and not _patch_looks_like_enabled_send(screen, cx, cy, tw, th):
        return None
    return score, cx, cy


def click_by_template(
    page,
    key: str,
    *,
    config: dict | None = None,
    log=None,
) -> bool:
    cfg = config or load_ui_config()
    tpl = _template_path(cfg, key)
    if tpl is None:
        return False
    entry = (cfg.get("templates") or {}).get(key) or {}
    if isinstance(entry, dict):
        threshold = float(entry.get("threshold") or cfg.get("match_threshold", 0.72))
        roi = entry.get("search_roi")
        require_blue = bool(entry.get("require_blue"))
    else:
        threshold = float(cfg.get("match_threshold", 0.72))
        roi = None
        require_blue = False
    hit = match_template_on_page(
        page,
        tpl,
        threshold=threshold,
        roi=roi,
        require_blue=require_blue,
    )
    if hit is None:
        if log:
            log(f"[UI L2] 模板未匹配: {key}")
        return False
    score, cx, cy = hit
    from app.vision_transcribe.browser.dom_locator import click_send_robust

    if key == "send" and click_send_robust(page, anchor=(cx, cy, 40, 40), log=log):
        if log:
            log(f"[UI L2] 模板定位发送 @ ({cx},{cy}) score={score:.2f}")
        return True
    page.mouse.move(cx, cy)
    page.mouse.down()
    page.wait_for_timeout(80)
    page.mouse.up()
    if log:
        log(f"[UI L2] 截图模板点击 {key} @ ({cx},{cy}) score={score:.2f}")
    return True


def click_send_by_template(
    page,
    *,
    config: dict | None = None,
    log=None,
    timeout_ms: int = 120_000,
) -> bool:
    """兼容旧调用：走灰→蓝快速轮询点击。"""
    return wait_and_click_send(
        page, config=config, log=log, timeout_ms=timeout_ms
    )


def _template_entry(cfg: dict[str, Any], key: str) -> dict[str, Any]:
    entry = (cfg.get("templates") or {}).get(key) or {}
    return entry if isinstance(entry, dict) else {}


def _match_template_key_on_screen(
    screen_bgr: np.ndarray,
    cfg: dict[str, Any],
    key: str,
) -> tuple[float, int, int] | None:
    tpl_path = _template_path(cfg, key)
    if tpl_path is None:
        return None
    tpl = cv2.imread(str(tpl_path))
    if tpl is None:
        return None
    entry = _template_entry(cfg, key)
    threshold = float(entry.get("threshold") or cfg.get("match_threshold", 0.68))
    roi = entry.get("search_roi")
    if roi:
        crop, offset = _crop_screen_roi(screen_bgr, roi)
    else:
        crop, offset = screen_bgr, (0, 0)
    hit = _match_template_on_bgr(
        crop,
        tpl,
        threshold=threshold,
        offset=offset,
        scales=(0.92, 1.0, 1.08),
    )
    if hit is None:
        return None
    score, cx, cy, _tw, _th = hit
    return score, cx, cy


def is_template_visible(
    page,
    key: str,
    *,
    config: dict | None = None,
) -> bool:
    cfg = config or load_ui_config()
    try:
        screen = _page_screenshot_bgr(page)
        return _match_template_key_on_screen(screen, cfg, key) is not None
    except Exception:
        return False


def match_stop_button_on_page(
    page,
    *,
    config: dict | None = None,
    screen: np.ndarray | None = None,
) -> tuple[float, int, int] | None:
    """图识别：composer 右下角停止钮（蓝圆白方块）。返回 (score, cx, cy)。"""
    cfg = config or load_ui_config()
    try:
        bgr = screen if screen is not None else _page_screenshot_bgr(page)
        return _match_template_key_on_screen(bgr, cfg, "stop")
    except Exception:
        return None


def is_stop_image_confirmed_at(
    page,
    x: float,
    y: float,
    *,
    config: dict | None = None,
    screen: np.ndarray | None = None,
    radius: float = 48.0,
) -> bool:
    """停止图识别须：stop 匹配点靠近坐标，且得分明显高于 send（避免误伤蓝发送键）。"""
    cfg = config or load_ui_config()
    try:
        bgr = screen if screen is not None else _page_screenshot_bgr(page)
        stop_hit = _match_template_key_on_screen(bgr, cfg, "stop")
        if stop_hit is None:
            return False
        stop_score, sx, sy = stop_hit
        stop_entry = _template_entry(cfg, "stop")
        stop_th = float(stop_entry.get("threshold") or 0.72)
        if stop_score < stop_th:
            return False
        dx = float(sx) - float(x)
        dy = float(sy) - float(y)
        if (dx * dx + dy * dy) > float(radius) * float(radius):
            return False
        send_hit = _match_template_key_on_screen(bgr, cfg, "send")
        if send_hit is None:
            return True
        send_score, send_x, send_y = send_hit
        sdx = float(send_x) - float(x)
        sdy = float(send_y) - float(y)
        send_near = (sdx * sdx + sdy * sdy) <= float(radius) * float(radius)
        if send_near and send_score >= stop_score - 0.05:
            return False
        return True
    except Exception:
        return False


def is_stop_button_visible(
    page,
    *,
    config: dict | None = None,
) -> bool:
    """仅图识别可见（不单独用于跳过发送，见 is_stop_image_confirmed_at）。"""
    return match_stop_button_on_page(page, config=config) is not None


def is_stop_button_near(
    page,
    x: float,
    y: float,
    *,
    radius: float = 48.0,
    config: dict | None = None,
    screen: np.ndarray | None = None,
) -> bool:
    """坐标处停止钮图识别（须 stop 得分高于 send）。"""
    return is_stop_image_confirmed_at(
        page, x, y, config=config, screen=screen, radius=radius
    )


def is_continue_generate_visible(
    page,
    *,
    config: dict | None = None,
    allow_template: bool = True,
) -> bool:
    """页面上是否仍显示「继续生成」（未完成则不应点复制）。"""
    cfg = config or load_ui_config()
    for factory in (
        lambda: page.get_by_role("button", name="继续生成"),
        lambda: page.get_by_text("继续生成", exact=True),
        lambda: page.locator("button", has_text="继续生成"),
    ):
        try:
            loc = factory()
            if loc.count() > 0 and loc.last.is_visible():
                return True
        except Exception:
            continue
    if allow_template:
        return is_template_visible(page, "continue_gen", config=cfg)
    return False


_RETRY_TEMPLATE_KEYS: tuple[str, ...] = ("retry_user_bubble", "retry_response")

_UPLOAD_SERVER_BUSY_TEMPLATE_KEYS: tuple[str, ...] = (
    "upload_server_busy",
    "upload_server_busy_text",
)


def is_upload_server_busy_template_visible(
    page,
    *,
    config: dict | None = None,
    log=None,
) -> tuple[bool, str]:
    """图识别 L2：附件缩略图「服务器繁忙」叠层（DOM 未命中时的二层保险）。"""
    cfg = config or load_ui_config()
    for key in _UPLOAD_SERVER_BUSY_TEMPLATE_KEYS:
        if is_template_visible(page, key, config=cfg):
            hint = f"图模板 {key}"
            if log:
                log(f"[UploadGuard L2] 服务器繁忙模板命中: {key}")
            return True, hint
    return False, ""


def is_retry_template_visible(
    page,
    *,
    config: dict | None = None,
    log=None,
) -> bool:
    """图识别 L2：用户气泡橙色重试 / 回答操作栏重试。"""
    cfg = config or load_ui_config()
    for key in _RETRY_TEMPLATE_KEYS:
        if is_template_visible(page, key, config=cfg):
            if log:
                log(f"[UI L2] 重试图标模板命中: {key}")
            return True
    return False


def click_retry_template_if_visible(
    page,
    *,
    config: dict | None = None,
    log=None,
) -> bool:
    cfg = config or load_ui_config()
    for key in _RETRY_TEMPLATE_KEYS:
        if not is_template_visible(page, key, config=cfg):
            continue
        if click_by_template(page, key, config=cfg, log=log):
            if log:
                log(f"[UI L2] 已点击「重试」（图模板 {key}）")
            return True
    return False


def click_retry_user_bubble_if_visible(
    page,
    *,
    config: dict | None = None,
    log=None,
) -> bool:
    """用户气泡橙色圆形「重试」（发送点了但未进入生成时常出现）。"""
    cfg = config or load_ui_config()
    if not is_template_visible(page, "retry_user_bubble", config=cfg):
        return False
    if click_by_template(page, "retry_user_bubble", config=cfg, log=log):
        if log:
            log("[UI L2] 已点击「重试」（用户气泡图模板）")
        return True
    return False


def is_regenerate_retry_visible(
    page,
    *,
    config: dict | None = None,
    allow_template: bool = True,
) -> bool:
    """DeepSeek 生成失败时的「重试」（文字钮或操作栏图标）。"""
    cfg = config or load_ui_config()
    for factory in (
        lambda: page.get_by_role("button", name="重试"),
        lambda: page.get_by_role("button", name="Retry"),
        lambda: page.get_by_text("重试", exact=True),
        lambda: page.get_by_text("Retry", exact=True),
        lambda: page.locator("button", has_text="重试"),
        lambda: page.locator("button", has_text="Retry"),
        lambda: page.locator('[aria-label*="重试"]'),
        lambda: page.locator('[aria-label*="Retry" i]'),
        lambda: page.locator('[title*="重试"]'),
        lambda: page.locator('[title*="Retry" i]'),
    ):
        try:
            loc = factory()
            n = loc.count()
            for i in range(n - 1, -1, -1):
                if loc.nth(i).is_visible():
                    return True
        except Exception:
            continue
    try:
        if page.evaluate(_IS_REGENERATE_RETRY_VISIBLE_JS):
            return True
    except Exception:
        pass
    if allow_template:
        return is_retry_template_visible(page, config=cfg)
    return False


def click_regenerate_retry_if_visible(
    page,
    *,
    config: dict | None = None,
    log=None,
    allow_template: bool = True,
) -> bool:
    """若出现「重试」则点击（DOM 优先，操作栏图标 JS，图模板兜底）。"""
    cfg = config or load_ui_config()
    for factory in (
        lambda: page.get_by_role("button", name="重试"),
        lambda: page.get_by_role("button", name="Retry"),
        lambda: page.get_by_text("重试", exact=True),
        lambda: page.get_by_text("Retry", exact=True),
        lambda: page.locator("button", has_text="重试"),
        lambda: page.locator("button", has_text="Retry"),
        lambda: page.locator('[aria-label*="重试"]'),
        lambda: page.locator('[aria-label*="Retry" i]'),
        lambda: page.locator('[title*="重试"]'),
        lambda: page.locator('[title*="Retry" i]'),
    ):
        try:
            loc = factory()
            n = loc.count()
            for i in range(n - 1, -1, -1):
                btn = loc.nth(i)
                if not btn.is_visible():
                    continue
                btn.scroll_into_view_if_needed(timeout=2000)
                btn.click(timeout=5000)
                if log:
                    log("[UI L2] 已点击「重试」（DOM）")
                return True
        except Exception:
            continue
    try:
        hit = page.evaluate(_CLICK_REGENERATE_RETRY_JS)
        if hit:
            if log:
                log("[UI L2] 已点击「重试」（操作栏/错误区 JS）")
            return True
    except Exception:
        pass
    if allow_template and click_retry_template_if_visible(page, config=cfg, log=log):
        return True
    return False


def click_continue_generate_if_visible(
    page,
    *,
    config: dict | None = None,
    log=None,
    allow_template: bool = True,
) -> bool:
    """若出现「继续生成」则点击（DOM 优先，图识别兜底）。"""
    cfg = config or load_ui_config()
    for factory in (
        lambda: page.get_by_role("button", name="继续生成"),
        lambda: page.get_by_text("继续生成", exact=True),
        lambda: page.locator("button", has_text="继续生成"),
        lambda: page.locator('[aria-label*="继续生成"]'),
    ):
        try:
            loc = factory()
            n = loc.count()
            for i in range(n - 1, -1, -1):
                btn = loc.nth(i)
                if not btn.is_visible():
                    continue
                btn.scroll_into_view_if_needed(timeout=2000)
                btn.click(timeout=5000)
                if log:
                    log("[UI L2] 已点击「继续生成」（DOM）")
                return True
        except Exception:
            continue
    if allow_template and click_by_template(page, "continue_gen", config=cfg, log=log):
        return True
    return False


def _last_assistant_locator(page):
    for sel in (
        '[data-message-author-role="assistant"]',
        ".ds-message",
        ".markdown-body",
        "div[class*='assistant']",
    ):
        try:
            loc = page.locator(sel)
            n = loc.count()
            if n > 0:
                return loc.nth(n - 1)
        except Exception:
            continue
    return None


def looks_like_vision_response(
    text: str,
    *,
    min_chars_without_marker: int = 1500,
    start_page: int | None = None,
    end_page: int | None = None,
) -> bool:
    """剪贴板/回答区内容像 batch 转录结果，而非侧栏历史或截断片段。"""
    t = (text or "").strip()
    if len(t) < 100:
        return False
    try:
        from app.vision_transcribe.clipboard_sanitize import (
            has_clipboard_contamination,
            recover_wait_transcript,
        )

        recovered = recover_wait_transcript(t)
        if recovered.strip():
            t = recovered.strip()
        elif has_clipboard_contamination(t):
            return False
    except Exception:
        pass
    try:
        from app.vision_transcribe.browser.katex_scrap import has_dom_katex_scrap

        if has_dom_katex_scrap(t):
            return False
    except Exception:
        pass
    try:
        from app.vision_transcribe.transcript_quality import (
            looks_truncated_transcript,
            min_chars_for_page_span,
        )

        if looks_truncated_transcript(
            t, start_page=start_page, end_page=end_page
        ):
            return False
    except Exception:
        pass
    if "PDF2MD:PAGE" in t or "<!-- PDF2MD:PAGE:" in t:
        # PAGE 标记前大量侧栏/Prompt 行 → 仍是脏剪贴板
        try:
            from app.vision_transcribe.clipboard_sanitize import first_page_marker_index

            idx = first_page_marker_index(t)
            if idx is not None and idx > 400:
                return False
        except Exception:
            pass
        if start_page is not None and end_page is not None:
            try:
                from app.vision_transcribe.clipboard_sanitize import page_numbers_in_text
                from app.vision_transcribe.transcript_quality import min_chars_for_page_span

                found = set(page_numbers_in_text(t))
                expected = set(range(start_page, end_page + 1))
                if found == expected and len(t) >= min_chars_for_page_span(
                    start_page, end_page
                ):
                    return True
            except Exception:
                pass
        return True
    junk = (
        "开启新对话\n今天",
        "\n昨天\n",
        "\n7 天内\n",
        "\n30 天内\n",
        "Cursor聊天记录",
        "积分极限计算题",
    )
    if any(m in t for m in junk) and "PDF2MD" not in t:
        return False
    # 无 PAGE 标记时须足够长（10 页 batch 通常数千字以上）
    return len(t) >= min_chars_without_marker


_FIND_COPY_BUTTON_JS = """
() => {
  document.querySelectorAll('[data-pdf2md-copy]').forEach((el) => {
    el.removeAttribute('data-pdf2md-copy');
  });
  const vh = window.innerHeight;
  const isCopyish = (el) => {
    const label = (el.getAttribute('aria-label') || el.title || el.innerText || '').trim();
    if (/复制|copy/i.test(label) && !/复制链接|copy link/i.test(label)) return true;
    const svg = el.querySelector && el.querySelector('svg');
    if (!svg) return false;
    const rects = svg.querySelectorAll('rect');
    if (rects.length >= 2) return true;
    return false;
  };
  const candidates = [];
  document.querySelectorAll('button,[role="button"],div,span').forEach((el) => {
    const r = el.getBoundingClientRect();
    if (r.width < 18 || r.width > 56 || r.height < 18 || r.height > 56) return;
    if (r.top < vh * 0.15 || r.top > vh * 0.92) return;
    if (r.left > window.innerWidth * 0.72) return;
    if (!isCopyish(el)) return;
    const st = getComputedStyle(el);
    if (st.visibility === 'hidden' || st.display === 'none' || st.opacity === '0') return;
    candidates.push({ el, y: r.top + r.height / 2, x: r.left + r.width / 2, bottom: r.bottom });
  });
  if (!candidates.length) return null;
  candidates.sort((a, b) => (b.bottom - a.bottom) || (a.x - b.x));
  const best = candidates[0];
  best.el.setAttribute('data-pdf2md-copy', '1');
  return { x: best.x, y: best.y };
}
"""


_RETRY_ERROR_NEEDLES = (
    "生成失败",
    "请重试",
    "出了点问题",
    "服务繁忙",
    "网络异常",
    "网络错误",
    "请稍后再试",
    "failed to generate",
    "something went wrong",
)


def _retry_js_helpers() -> str:
    needles = ", ".join(repr(n) for n in _RETRY_ERROR_NEEDLES)
    return f"""
  const errNeedles = [{needles}];
  const labelOf = (el) =>
    (el.getAttribute('aria-label') || el.title || el.innerText || '').trim();
  const isRetryish = (el) => {{
    const label = labelOf(el);
    if (/重试|重新生成|再试一次|retry|regenerate|try again/i.test(label)) return true;
    return false;
  }};
  const isVisible = (el) => {{
    const r = el.getBoundingClientRect();
    if (r.width < 12 || r.height < 12) return false;
    const st = getComputedStyle(el);
    return st.visibility !== 'hidden' && st.display !== 'none' && st.opacity !== '0';
  }};
  const lastAssistant = () => {{
    const sels = [
      '[data-message-author-role="assistant"]',
      '.ds-message',
      '.markdown-body',
      'div[class*="assistant"]',
    ];
    let best = null;
    let bestY = -1;
    for (const sel of sels) {{
      for (const el of document.querySelectorAll(sel)) {{
        const r = el.getBoundingClientRect();
        if (r.height < 8) continue;
        if (r.top >= bestY) {{
          bestY = r.top;
          best = el;
        }}
      }}
    }}
    return best;
  }};
  const hasErrorContext = () => {{
    const root = lastAssistant();
    if (!root) return false;
    const t = (root.innerText || '').toLowerCase();
    return errNeedles.some((n) => t.includes(String(n).toLowerCase()));
  }};
  const retryCandidates = () => {{
    const vh = window.innerHeight;
    const out = [];
    document.querySelectorAll('button,[role="button"]').forEach((el) => {{
      if (!isVisible(el) || !isRetryish(el)) return;
      const r = el.getBoundingClientRect();
      if (r.top < vh * 0.12 || r.top > vh * 0.95) return;
      out.push({{ el, bottom: r.bottom, x: r.left }});
    }});
    out.sort((a, b) => (b.bottom - a.bottom) || (a.x - b.x));
    return out;
  }};
"""


_IS_REGENERATE_RETRY_VISIBLE_JS = (
    "() => {"
    + _retry_js_helpers()
    + """
  const cands = retryCandidates();
  if (!cands.length) return false;
  if (cands.some((c) => /重试|retry/i.test(labelOf(c.el)))) return true;
  return hasErrorContext();
}
"""
)

_CLICK_REGENERATE_RETRY_JS = (
    "() => {"
    + _retry_js_helpers()
    + """
  const cands = retryCandidates();
  for (const c of cands) {
    c.el.click();
    return true;
  }
  return false;
}
"""
)


_IS_RESPONSE_TOOLBAR_VISIBLE_JS = """
() => {
  // 生成结束后，回答下方会出现复制/重试/赞/踩 等图标行
  const vh = window.innerHeight;
  const icons = [];
  document.querySelectorAll('button,[role="button"],div').forEach((el) => {
    const r = el.getBoundingClientRect();
    if (r.width < 18 || r.width > 56 || r.height < 18 || r.height > 56) return;
    if (r.top < vh * 0.2 || r.top > vh * 0.92) return;
    if (r.left > window.innerWidth * 0.75) return;
    if (!(el.querySelector && el.querySelector('svg'))) return;
    icons.push({ x: r.left, y: r.top });
  });
  // 同一水平线上至少 3 个小图标 → 视为操作栏已出现
  for (const a of icons) {
    let n = 0;
    for (const b of icons) {
      if (Math.abs(a.y - b.y) <= 18 && Math.abs(a.x - b.x) < 280) n += 1;
    }
    if (n >= 3) return true;
  }
  return false;
}
"""


def match_template_hit_on_page(
    page,
    key: str,
    *,
    config: dict | None = None,
    screen: np.ndarray | None = None,
    min_score: float | None = None,
) -> tuple[float, int, int, int, int] | None:
    """返回 (score, cx, cy, tw, th)；用于工具栏/复制联合定位。"""
    cfg = config or load_ui_config()
    tpl_path = _template_path(cfg, key)
    if tpl_path is None:
        return None
    tpl = cv2.imread(str(tpl_path))
    if tpl is None:
        return None
    entry = _template_entry(cfg, key)
    threshold = float(
        min_score
        if min_score is not None
        else (entry.get("threshold") or cfg.get("match_threshold", 0.68))
    )
    roi = entry.get("search_roi")
    try:
        bgr = screen if screen is not None else _page_screenshot_bgr(page)
    except Exception:
        return None
    if roi:
        crop, offset = _crop_screen_roi(bgr, roi)
    else:
        crop, offset = bgr, (0, 0)
    hit = _match_template_on_bgr(
        crop,
        tpl,
        threshold=threshold,
        offset=offset,
        scales=(0.85, 0.92, 1.0, 1.08, 1.15),
    )
    return hit


def match_action_toolbar_on_page(
    page,
    *,
    config: dict | None = None,
    screen: np.ndarray | None = None,
) -> tuple[float, int, int, int, int] | None:
    """图识别：回答下方复制/重试/赞/踩/分享一整行。"""
    if screen is None:
        _wait_chat_scroll_settled(page, timeout_ms=500)
    return match_template_hit_on_page(
        page, "action_toolbar", config=config, screen=screen
    )


def locate_copy_via_toolbar_image(
    page,
    *,
    config: dict | None = None,
    log=None,
) -> tuple[int, int] | None:
    """先识别整行操作栏，再在栏内最左侧点复制（或再匹配 copy 模板）。"""
    cfg = config or load_ui_config()
    _wait_chat_scroll_settled(page, timeout_ms=600)
    try:
        screen = _page_screenshot_bgr(page)
    except Exception as e:
        if log:
            log(f"[UI L2] 复制图识别：截图失败 {e}")
        return None

    # 诊断：操作栏 / 复制 最佳分（无论是否过阈值）
    tb_probe = _probe_template_best(
        page, "action_toolbar", config=cfg, screen=screen
    )
    cp_probe = _probe_template_best(
        page, "copy_response", config=cfg, screen=screen
    )
    if log:
        if tb_probe is None:
            log("[UI L2] 复制图识别：缺少 action_toolbar.png 模板")
        else:
            sc, th, hit = tb_probe
            log(
                f"[UI L2] 操作栏模板 best={sc:.2f} 阈值={th:.2f} "
                f"{'命中' if hit else '未过阈值'}"
            )
        if cp_probe is None:
            log("[UI L2] 复制图识别：缺少 copy_response.png 模板")
        else:
            sc, th, hit = cp_probe
            log(
                f"[UI L2] 复制图标模板 best={sc:.2f} 阈值={th:.2f} "
                f"{'命中' if hit else '未过阈值'}"
            )

    toolbar = match_action_toolbar_on_page(page, config=cfg, screen=screen)
    if toolbar is None:
        # 仅有复制小图标时也可
        copy_hit = match_template_hit_on_page(
            page, "copy_response", config=cfg, screen=screen
        )
        if copy_hit is None and cp_probe is not None:
            sc, th, hit = cp_probe
            if not hit and sc >= max(0.40, th - 0.12):
                copy_hit = match_template_hit_on_page(
                    page,
                    "copy_response",
                    config=cfg,
                    screen=screen,
                    min_score=max(0.40, th - 0.12),
                )
                if copy_hit and log:
                    log(
                        f"[UI L2] 复制图标软匹配 score={copy_hit[0]:.2f} "
                        f"（阈值放宽至 {max(0.40, th - 0.12):.2f}）"
                    )
        if copy_hit is None:
            if log:
                log("[UI L2] 图识别未找到操作栏/复制图标")
            return None
        _s, cx, cy, _tw, _th = copy_hit
        if log:
            log(f"[UI L2] 仅匹配到复制图标 score={_s:.2f} @ ({cx},{cy})")
        return cx, cy

    _score, tcx, tcy, tw, th = toolbar
    # 工具栏命中框：以中心向外扩半宽半高
    x0 = max(0, tcx - tw // 2)
    y0 = max(0, tcy - th // 2)
    x1 = x0 + tw
    y1 = y0 + th
    band = screen[y0:y1, x0:x1]
    if band.size == 0:
        if log:
            log("[UI L2] 操作栏命中区为空，放弃图识别")
        return None

    # 在工具栏带内再匹配复制图标
    tpl_path = _template_path(cfg, "copy_response")
    copy_cx = copy_cy = None
    if tpl_path is not None:
        tpl = cv2.imread(str(tpl_path))
        if tpl is not None:
            entry = _template_entry(cfg, "copy_response")
            th_copy = float(entry.get("threshold") or 0.50)
            hit = _match_template_on_bgr(
                band,
                tpl,
                threshold=th_copy,
                offset=(x0, y0),
                scales=(0.9, 1.0, 1.1),
            )
            if hit is not None:
                _s, copy_cx, copy_cy, _cw, _ch = hit
                if log:
                    log(f"[UI L2] 工具栏内复制图标 score={_s:.2f}")

    if copy_cx is None:
        # 复制在工具栏最左侧约 1/5 处
        copy_cx = int(x0 + max(12, tw * 0.10))
        copy_cy = int(tcy)
        if log:
            log("[UI L2] 工具栏内未匹配复制图标，改用最左 10% 估计点")

    if log:
        log(
            f"[UI L2] 操作栏命中 score={_score:.2f}，复制目标 @ ({copy_cx},{copy_cy})"
        )
    return int(copy_cx), int(copy_cy)


def is_send_composer_gray(
    page,
    *,
    config: dict | None = None,
) -> bool:
    """发送键再次变灰（生成结束、输入区空闲）。"""
    cfg = config or load_ui_config()
    tpl_blue_path, tpl_gray_path, roi, locate_threshold, _poll = _send_template_config(cfg)
    if tpl_gray_path is None and tpl_blue_path is None:
        # DOM：可发送=蓝；不可发送且非停止 → 视为灰
        try:
            from app.vision_transcribe.browser.dom_locator import (
                is_ai_generating,
                is_send_button_ready,
            )

            if is_ai_generating(page):
                return False
            return not is_send_button_ready(page)
        except Exception:
            return False
    try:
        from app.vision_transcribe.browser.dom_locator import (
            is_ai_generating,
            is_confirmed_stop_at,
        )

        if is_ai_generating(page):
            return False

        screen = _page_screenshot_bgr(page)
        gray_score, blue_score, hit = _send_template_match_scores(screen, cfg)
        score_margin = 0.06
        if gray_score >= locate_threshold and gray_score >= blue_score + score_margin:
            return True
        if blue_score >= locate_threshold and blue_score > gray_score + score_margin:
            if hit is not None:
                _score, cx, cy, _tw, _th = hit
                if is_confirmed_stop_at(page, float(cx), float(cy)):
                    return False
            return False

        if hit is None:
            return not is_ai_generating(page)
        _score, cx, cy, tw, th = hit
        state = _send_state_via_page(page, cx, cy, tw, th)
        if state == "unknown":
            state = _patch_send_state(screen, cx, cy, tw, th)
        if state == "gray":
            return True
        if state == "blue":
            if is_confirmed_stop_at(page, float(cx), float(cy)):
                return False
            return False
        # unknown：灰模板分不低于蓝模板时视为禁用
        if gray_score >= blue_score and gray_score >= locate_threshold * 0.85:
            return True
        return False
    except Exception:
        return False


_SCROLL_CHAT_CONTAINER_JS = """
() => {
  let best = null;
  let bestScore = 0;
  for (const el of document.querySelectorAll('*')) {
    try {
      const st = getComputedStyle(el);
      if (!['auto', 'scroll', 'overlay'].includes(st.overflowY)) continue;
      const extra = el.scrollHeight - el.clientHeight;
      if (extra < 60) continue;
      const r = el.getBoundingClientRect();
      if (r.width < 180 || r.height < 120) continue;
      if (r.left > window.innerWidth * 0.35) continue;
      const score = extra * r.width * r.height;
      if (score > bestScore) {
        bestScore = score;
        best = el;
      }
    } catch (e) {}
  }
  if (!best) return { found: false, atBottom: false, top: 0, max: 0 };
  best.scrollTop = best.scrollHeight;
  const max = Math.max(0, best.scrollHeight - best.clientHeight);
  return {
    found: true,
    atBottom: best.scrollTop >= max - 4,
    top: best.scrollTop,
    max,
    tag: best.tagName,
  };
}
"""


_SCROLL_CHAT_READ_JS = """
() => {
  let best = null;
  let bestScore = 0;
  for (const el of document.querySelectorAll('*')) {
    try {
      const st = getComputedStyle(el);
      if (!['auto', 'scroll', 'overlay'].includes(st.overflowY)) continue;
      const extra = el.scrollHeight - el.clientHeight;
      if (extra < 60) continue;
      const r = el.getBoundingClientRect();
      if (r.width < 180 || r.height < 120) continue;
      if (r.left > window.innerWidth * 0.35) continue;
      const score = extra * r.width * r.height;
      if (score > bestScore) {
        bestScore = score;
        best = el;
      }
    } catch (e) {}
  }
  if (!best) return { found: false, top: 0, max: 0, atBottom: true };
  const max = Math.max(0, best.scrollHeight - best.clientHeight);
  return {
    found: true,
    top: best.scrollTop,
    max,
    atBottom: best.scrollTop >= max - 6,
  };
}
"""


def _wait_chat_scroll_settled(page, *, timeout_ms: int = 1200) -> None:
    """等主聊天区滚到底且 scrollTop 不再跳动（避免回弹后立刻截图）。"""
    deadline = time.monotonic() + timeout_ms / 1000.0
    stable_since: float | None = None
    last_top: float | None = None
    while time.monotonic() < deadline:
        try:
            st = page.evaluate(_SCROLL_CHAT_READ_JS)
        except Exception:
            page.wait_for_timeout(80)
            continue
        if not isinstance(st, dict):
            page.wait_for_timeout(80)
            continue
        top = float(st.get("top") or 0)
        at_bottom = bool(st.get("atBottom"))
        if last_top is not None and abs(top - last_top) <= 2 and at_bottom:
            if stable_since is None:
                stable_since = time.monotonic()
            elif (time.monotonic() - stable_since) * 1000 >= 280:
                return
        else:
            stable_since = None
        last_top = top
        if not at_bottom:
            try:
                page.evaluate(_SCROLL_CHAT_CONTAINER_JS)
            except Exception:
                pass
        page.wait_for_timeout(90)
    page.wait_for_timeout(150)


def scroll_chat_to_bottom(page, *, log=None) -> None:
    """滚到对话底部：只滚主聊天容器，不用 End/滚轮/scroll_into_view（防回弹）。"""
    try:
        page.evaluate(_SCROLL_CHAT_CONTAINER_JS)
        page.wait_for_timeout(200)
        page.evaluate(_SCROLL_CHAT_CONTAINER_JS)
        _wait_chat_scroll_settled(page, timeout_ms=1400)
        if log:
            log("[UI L2] 对话已滚到底（已等滚动稳定，避免回弹）")
    except Exception as e:
        if log:
            log(f"[UI L2] 滚到底失败: {e}")


def is_response_action_toolbar_visible(page, *, config: dict | None = None) -> bool:
    """回答下方操作栏：优先图识别整行，DOM 簇为辅。"""
    if match_action_toolbar_on_page(page, config=config) is not None:
        return True
    try:
        return bool(page.evaluate(_IS_RESPONSE_TOOLBAR_VISIBLE_JS))
    except Exception:
        return False


def is_generation_fully_done(
    page,
    *,
    config: dict | None = None,
    scroll_first: bool = True,
    log=None,
) -> bool:
    """结束特征（须先滚到底）：
    1) 发送键再次变灰
    2) 无「继续生成」
    3) 出现操作栏/复制按钮
    """
    from app.vision_transcribe.browser.dom_locator import is_ai_generating

    cfg = config or load_ui_config()
    if scroll_first:
        scroll_chat_to_bottom(page, log=log)
        _wait_chat_scroll_settled(page, timeout_ms=800)

    generating = is_ai_generating(page)
    if generating:
        if log:
            log("[UI L2] 结束判定：仍在生成中")
        return False
    cont = is_continue_generate_visible(
        page, config=cfg, allow_template=False
    )
    if cont:
        if log:
            log("[UI L2] 结束判定：仍有「继续生成」")
        return False
    send_gray = is_send_composer_gray(page, config=cfg)
    # 操作栏或复制图标
    toolbar = match_action_toolbar_on_page(page, config=cfg) is not None
    copy_icon = match_template_hit_on_page(
        page, "copy_response", config=cfg
    ) is not None
    dom_bar = is_response_action_toolbar_visible(page, config=cfg)
    has_toolbar = toolbar or copy_icon or dom_bar
    if not send_gray:
        if has_toolbar and not generating:
            if log:
                log(
                    "[UI L2] 结束判定：操作栏已现、发送色未确认"
                    "（淡紫蓝禁用态）→ 放宽通过"
                )
            send_gray = True
        else:
            if log:
                log("[UI L2] 结束判定：发送键未变灰")
            return False
    ok = has_toolbar
    if log:
        log(
            f"[UI L2] 结束判定：发送灰={'是' if send_gray else '否'}，继续生成=否，"
            f"操作栏图={'有' if toolbar else '无'}，"
            f"复制图={'有' if copy_icon else '无'}，"
            f"DOM栏={'有' if dom_bar else '无'} → {'通过' if ok else '未通过'}"
        )
    return ok


def click_copy_response_button(
    page,
    *,
    config: dict | None = None,
    log=None,
) -> bool:
    """先滚到底 → 图识别整行操作栏 → 再点最左复制（最多 3 轮）。"""
    cfg = config or load_ui_config()
    for attempt in range(3):
        if log and attempt > 0:
            log(f"[UI L2] 复制按钮重试 ({attempt + 1}/3)…")
        if _click_copy_response_once(page, config=cfg, log=log):
            return True
        page.wait_for_timeout(450)
    if log:
        log("[UI L2] 未找到复制按钮（图识别/DOM/模板均失败）")
    return False


def _click_copy_response_once(
    page,
    *,
    config: dict | None = None,
    log=None,
) -> bool:
    cfg = config or load_ui_config()
    if log:
        log("[UI L2] 开始定位复制按钮…")
    scroll_chat_to_bottom(page, log=log)

    # 1) 联合图识别：工具栏 → 复制
    pt = locate_copy_via_toolbar_image(page, config=cfg, log=log)
    if pt is not None:
        cx, cy = pt
        page.mouse.move(cx, cy)
        page.wait_for_timeout(40)
        page.mouse.click(cx, cy, delay=70)
        if log:
            log(f"[UI L2] 已点击复制（图识别 @ {cx},{cy}）")
        return True

    if log:
        log("[UI L2] 图识别失败，尝试 DOM 双矩形图标…")
    # 2) JS 双矩形图标
    try:
        hit = page.evaluate(_FIND_COPY_BUTTON_JS)
        if isinstance(hit, dict) and hit.get("x") is not None:
            x, y = float(hit["x"]), float(hit["y"])
            page.mouse.click(x, y, delay=70)
            if log:
                log(f"[UI L2] 已点击复制（DOM 图标 @ {int(x)},{int(y)}）")
            return True
        if log:
            log("[UI L2] DOM 图标未找到复制候选")
    except Exception as e:
        if log:
            log(f"[UI L2] DOM 图标查找异常: {e}")

    if log:
        log("[UI L2] 尝试回答区 aria-label「复制」…")
    last = _last_assistant_locator(page)
    if last is not None:
        try:
            last.hover(timeout=3000)
            page.wait_for_timeout(200)
        except Exception:
            pass
        scoped: list = [
            last.get_by_role("button", name="复制"),
            last.locator('[aria-label*="复制"]'),
            last.locator('[aria-label*="Copy" i]'),
        ]
        for loc in scoped:
            try:
                n = loc.count()
                for i in range(n - 1, -1, -1):
                    btn = loc.nth(i)
                    if not btn.is_visible():
                        continue
                    box = btn.bounding_box()
                    if box:
                        page.mouse.click(
                            box["x"] + box["width"] / 2,
                            box["y"] + box["height"] / 2,
                            delay=70,
                        )
                    else:
                        btn.click(timeout=5000)
                    if log:
                        log("[UI L2] 已点击复制（回答区 DOM）")
                    return True
            except Exception:
                continue

    if log:
        log("[UI L2] 尝试整页 copy_response 模板点击…")
    soft = match_template_hit_on_page(
        page, "copy_response", config=cfg, min_score=0.40
    )
    if soft is not None:
        _s, cx, cy, _tw, _th = soft
        page.mouse.click(cx, cy, delay=70)
        if log:
            log(f"[UI L2] 已点击复制（软阈值模板 @ {cx},{cy} score={_s:.2f}）")
        return True
    if click_by_template(page, "copy_response", config=cfg, log=log):
        return True
    return False


def wait_copy_icon_cycle(
    page,
    *,
    config: dict | None = None,
    log=None,
    timeout_ms: int = 60_000,
) -> bool:
    """等待复制完成：对号可选；复制图标再次出现即视为成功（动效很快时易漏检对号）。"""
    cfg = config or load_ui_config()
    if log:
        log("[UI L2] 等待复制动效（对号或复制键恢复）…")
    deadline = time.monotonic() + timeout_ms / 1000.0
    poll_s = 0.035
    started = time.monotonic()
    saw_done = False
    saw_not_copy = False  # 见过对号，或复制图标短暂消失
    copy_back_hits = 0
    last_log = 0.0

    while time.monotonic() < deadline:
        try:
            screen = _page_screenshot_bgr(page)
        except Exception:
            time.sleep(poll_s)
            continue

        has_copy = _match_template_key_on_screen(screen, cfg, "copy_response") is not None
        has_done = _match_template_key_on_screen(screen, cfg, "copy_done") is not None
        elapsed_ms = (time.monotonic() - started) * 1000.0

        if has_done:
            if not saw_done and log:
                log("[UI L2] 已见到复制对号")
            saw_done = True
            saw_not_copy = True
            copy_back_hits = 0
        elif not has_copy:
            saw_not_copy = True
            copy_back_hits = 0
        elif has_copy and not has_done:
            # 点击后须过最短防抖，避免把「点击前仍是复制键」误判为完成
            if elapsed_ms < 90:
                copy_back_hits = 0
            elif saw_done or saw_not_copy:
                copy_back_hits += 1
                if copy_back_hits >= 2:
                    if log:
                        hint = "对号已恢复为复制图标" if saw_done else "复制键已恢复"
                        log(f"[UI L2] 复制完成（{hint}）")
                    page.wait_for_timeout(120)
                    return True
            elif elapsed_ms >= 450:
                # 极快动效：整段 copy→对号→copy 落在两帧之间，超时后复制键稳定也算完成
                copy_back_hits += 1
                if copy_back_hits >= 2:
                    if log:
                        log("[UI L2] 复制完成（复制键稳定，未捕获对号）")
                    page.wait_for_timeout(120)
                    return True
        else:
            copy_back_hits = 0

        now = time.monotonic()
        if log and now - last_log > 4.0:
            log(
                f"[UI L2] 复制动效轮询… 复制键={'有' if has_copy else '无'} "
                f"对号={'有' if has_done else '无'} "
                f"已过{int(elapsed_ms)}ms"
            )
            last_log = now
        time.sleep(poll_s)

    if log:
        log("[UI L2] 复制动效等待超时")
    return False


def _read_clipboard_when_stable(
    read_fn: Callable[[], str],
    *,
    log=None,
    timeout_ms: int = 12_000,
    stable_ms: int = 400,
) -> str:
    """动效结束后轮询剪贴板，长度稳定后再取。"""
    deadline = time.monotonic() + timeout_ms / 1000.0
    text = ""
    last_len = -1
    stable_since: float | None = None
    last_log = 0.0
    while time.monotonic() < deadline:
        text = read_fn()
        n = len((text or "").strip())
        now = time.monotonic()
        if log and now - last_log > 2.0:
            log(f"[UI L2] 剪贴板轮询中… 当前 {n} 字")
            last_log = now
        if n > 0:
            if n == last_len:
                if stable_since is None:
                    stable_since = now
                elif (now - stable_since) * 1000 >= stable_ms:
                    break
            else:
                stable_since = None
                last_len = n
        time.sleep(0.12)
    return text


def extract_via_copy_button(
    page,
    *,
    config: dict | None = None,
    log=None,
    read_clipboard: Callable[[], str] | None = None,
    timeout_ms: int = 60_000,
    start_page: int | None = None,
    end_page: int | None = None,
) -> str:
    """点复制 → 等动效走完（复制→对号→复制）→ 再读剪贴板。"""
    cfg = config or load_ui_config()
    if is_continue_generate_visible(page, config=cfg):
        if log:
            log("[UI L2] 仍有「继续生成」，跳过复制")
        return ""

    if log:
        log("[UI L2] 进入复制抽取…")
    if not click_copy_response_button(page, config=cfg, log=log):
        if log:
            log("[UI L2] 复制点击失败，无法读剪贴板")
        return ""

    read_fn = read_clipboard or (lambda: "")
    cycle_ok = wait_copy_icon_cycle(
        page, config=cfg, log=log, timeout_ms=timeout_ms
    )
    if not cycle_ok:
        # 复制键仍可见时勿卡死：动效过快未截到对号，仍读剪贴板并由 DOM 兜底
        try:
            screen = _page_screenshot_bgr(page)
            copy_vis = _match_template_key_on_screen(screen, cfg, "copy_response") is not None
        except Exception:
            copy_vis = False
        if copy_vis:
            if log:
                log("[UI L2] 动效未确认但复制键可见，继续读剪贴板…")
        elif log:
            log("[UI L2] 复制动效未完整结束，暂不读剪贴板")
            return ""

    if log:
        log("[UI L2] 动效已完成，读取复制内容…")
    text = _read_clipboard_when_stable(read_fn, log=log)

    def _clip_ok(s: str) -> bool:
        return looks_like_vision_response(
            s, start_page=start_page, end_page=end_page
        )

    if text.strip() and not _clip_ok(text):
        try:
            from app.vision_transcribe.browser.clipboard_html import read_system_clipboard_html
            from app.vision_transcribe.browser.html_to_markdown import html_fragment_to_markdown
            from app.vision_transcribe.vision_structure_repair import markdown_lacks_structure

            if markdown_lacks_structure(text):
                html_raw = read_system_clipboard_html()
                html_md = html_fragment_to_markdown(html_raw)
                if html_md.strip() and _clip_ok(html_md):
                    if log:
                        log(f"[UI L2] 纯文本扁平，已用 HTML 剪贴板还原（{len(html_md)} 字）")
                    text = html_md
        except Exception:
            pass

    if text.strip() and not _clip_ok(text):
        if log:
            log(
                f"[UI L2] 剪贴板内容不像转录结果（{len(text.strip())} 字，"
                "可能误复制侧栏或截断），丢弃"
            )
        return ""
    if log and text.strip():
        log(f"[UI L2] 已从剪贴板读取 {len(text)} 字符")
    elif log:
        log("[UI L2] 剪贴板最终仍为空")
    return text


def _page_viewport_size(page) -> tuple[int, int]:
    try:
        vp = page.viewport_size
        if vp:
            return int(vp["width"]), int(vp["height"])
    except Exception:
        pass
    try:
        size = page.evaluate(
            "() => ({ width: window.innerWidth, height: window.innerHeight })"
        )
        return int(size["width"]), int(size["height"])
    except Exception:
        pass
    return DEEPSEEK_VIEWPORT_WIDTH, DEEPSEEK_VIEWPORT_HEIGHT


def click_by_coord(
    page,
    key: str,
    *,
    config: dict | None = None,
    log=None,
) -> bool:
    """仅 click_strategy=coord 时使用，不作为 auto 主流程（a2-2）。"""
    cfg = config or load_ui_config()
    clicks = cfg.get("clicks") or {}
    pt = clicks.get(key)
    if not pt:
        return False
    vw, vh = _page_viewport_size(page)
    if isinstance(pt, dict):
        x, y = pt.get("x"), pt.get("y")
        if pt.get("normalized"):
            cx, cy = int(float(x) * vw), int(float(y) * vh)
        else:
            cx, cy = int(x), int(y)
    elif isinstance(pt, (list, tuple)) and len(pt) >= 2:
        cx, cy = int(pt[0]), int(pt[1])
        if 0 <= cx <= 1 and 0 <= cy <= 1:
            cx, cy = int(cx * vw), int(cy * vh)
    else:
        return False
    page.mouse.click(cx, cy)
    if log:
        log(f"[UI coord] 固定坐标点击 {key} @ ({cx},{cy})")
    return True


def smart_click(
    page,
    key: str,
    *,
    dom_factories: list,
    config: dict | None = None,
    log=None,
    dom_click_fn: DomClickFn | None = None,
) -> bool:
    """三层定位：DOM → 截图模板 →（仅 coord 策略）坐标。"""
    cfg = config or load_ui_config()
    strategy = str(cfg.get("click_strategy", "auto"))
    # recorded = 提交走录制回放；单步 smart_click 仍允许 DOM + 模板兜底
    dom_ok = strategy in ("auto", "dom", "recorded")
    tpl_ok = strategy in ("auto", "template", "recorded")

    # L1: DOM
    if dom_ok and dom_click_fn:
        try:
            if dom_click_fn(dom_factories, strategy == "auto"):
                if log:
                    log(f"[UI L1] DOM 点击成功: {key}")
                return True
        except Exception as e:
            if log:
                log(f"[UI L1] DOM 失败 {key}: {e}")
        if strategy == "dom":
            return False

    # L2: 截图模板
    if tpl_ok:
        if click_by_template(page, key, config=cfg, log=log):
            return True
        if strategy == "template":
            return False

    # 固定坐标：仅调试策略
    if strategy == "coord":
        return click_by_coord(page, key, config=cfg, log=log)

    if log:
        log(f"[UI L3] {key} DOM+模板均失败，需人工处理")
    return False
