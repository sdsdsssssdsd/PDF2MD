# -*- coding: utf-8 -*-
"""Gold-only 紧裁图：去掉页眉 / 邻式，供评测 Recognition-only。

硬约束：
- 不得被 pipeline / writeback / Lean 生产几何引用
- 不得改写 benchmarks/crops/ 下的生产 crop（只写入 crops/tight/）
- 不得改写 gold 记录里的 bbox_pdf / crop_path（生产对照）
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from app.formula.crop_cache import (
    CROP_SCALE,
    page_index_candidates,
    render_formula_crop,
    resolve_pdf,
    write_crop_png,
)
from app.utils.paths import K5_CROPS_DIR

try:
    from app.utils.paths import K5_TIGHT_CROPS_DIR
except ImportError:  # github-submit 可能尚未同步该常量
    K5_TIGHT_CROPS_DIR = K5_CROPS_DIR / "tight"

# 紧裁后的小 padding。显著小于生产 CROP_PAD_X/Y（0.10 / 0.12）。
GOLD_PAD_X_PT = 4.0
GOLD_PAD_Y_PT = 3.5
GOLD_PAD_X_RATIO = 0.02
GOLD_PAD_Y_RATIO = 0.05
# 生产框只读；Gold 可在同一栏内补全被 seed 切掉的左半式。窜栏靠 detect_text_column。
GOLD_MAX_X_EXPAND_PT = 5.0
_MATH_FRAG = re.compile(r"[=∑∫√±×÷^_βγαζσμℓ·⋅]|\\[a-zA-Z]|[+\-*/()]")

_HEADER_RE = re.compile(
    r"(Received\s*:|Revised\s*:|Accepted\s*:|Available\s+online|"
    r"All rights reserved|收稿日期|修回日期|录用日期|©\s*\d{4})",
    re.I,
)
_PROSE_HINT_RE = re.compile(
    r"\b(where|which|that|this|using|known as|can be|calculated|"
    r"from Eq|the model|true target)\b",
    re.I,
)
_EQ_REF_RE = re.compile(r"\bEq(?:uation)?\.?\s*[\(（]", re.I)
# 编号只认 (n) / (1a)。大写后缀会把 11^T、W_s 收成假编号。
_TRAILING_EQ_RE = re.compile(r"[\(（]\s*(\d{1,3}[a-z]?)\s*[\)）]\s*$")
_STANDALONE_EQ_RE = re.compile(r"^[\(（]?\s*(\d{1,3}[a-z]?)\s*[\)）]?$")
_EQ_ONLY_RE = re.compile(r"^[\(（]\s*\d{1,3}[a-z]?\s*[\)）]$")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_WORD_RE = re.compile(r"[A-Za-z\u4e00-\u9fff]{3,}")
_SECTION_RE = re.compile(r"^[A-Z0-9][A-Z0-9 \-/&]{2,}$")


@dataclass(frozen=True)
class PageLine:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def bbox(self) -> list[float]:
        return [self.x0, self.y0, self.x1, self.y1]

    @property
    def cy(self) -> float:
        return 0.5 * (self.y0 + self.y1)

    @property
    def width(self) -> float:
        return max(0.0, self.x1 - self.x0)

    @property
    def height(self) -> float:
        return max(0.0, self.y1 - self.y0)


def iter_page_lines(page: Any) -> list[PageLine]:
    out: list[PageLine] = []
    raw = page.get_text("dict")
    for block in raw.get("blocks") or []:
        if block.get("type") != 0:
            continue
        for line in block.get("lines") or []:
            text = "".join(s.get("text") or "" for s in line.get("spans") or [])
            bbox = line.get("bbox") or (0, 0, 0, 0)
            x0, y0, x1, y1 = (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
            if x1 <= x0 or y1 <= y0:
                continue
            out.append(PageLine(text=text, x0=x0, y0=y0, x1=x1, y1=y1))
    return out


def line_eq_number(text: str) -> str:
    t = (text or "").strip()
    if not t or _EQ_REF_RE.search(t):
        return ""
    m = _TRAILING_EQ_RE.search(t)
    if m:
        return m.group(1)
    if len(t) <= 8:
        # 只认 (n)。裸 9 / 3 会把求和上下标、小节号当成邻式。
        m = re.fullmatch(r"[\(（]\s*(\d{1,3}[a-z]?)\s*[\)）]", t)
        if m:
            return m.group(1)
    return ""


def looks_like_section_header(text: str) -> bool:
    t = (text or "").strip()
    return bool(t) and len(t) >= 4 and bool(_SECTION_RE.fullmatch(t))


def looks_like_prose(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if looks_like_section_header(t):
        return True
    # step_num / warmup_steps 是公式标识符，不能拆成两个英文词。
    if re.search(r"[A-Za-z]_[A-Za-z]", t) and re.search(r"[=\(\)]", t):
        return False
    words = _WORD_RE.findall(t)
    if len(words) >= 8:
        return True
    if _PROSE_HINT_RE.search(t) and len(t) > 32:
        return True
    # 中文双栏正文通常无空格，不能按英文词数判断。
    cjk = len(_CJK_RE.findall(t))
    if cjk >= 8 and (cjk / max(len(t), 1) >= 0.28 or "=" not in t):
        return True
    return False


def looks_like_math_fragment(text: str) -> bool:
    """短数学碎片：`)V`、`+`、求和上下标。散文仍排除。"""
    t = (text or "").strip()
    if not t or looks_like_prose(t):
        return False
    if looks_like_formula_line(t):
        return True
    if line_eq_number(t) and len(t) <= 8:
        return True
    return len(t) <= 48 and bool(_MATH_FRAG.search(t))


def detect_text_column(page: Any, seed: list[float]) -> tuple[float, float]:
    """Gold 扩框用的栏边界。单栏论文允许越过生产 seed 去补全整式。"""
    page_w = float(page.rect.width)
    page_h = float(page.rect.height)
    lines = [
        ln
        for ln in iter_page_lines(page)
        if ln.y0 > page_h * 0.07 and ln.y1 < page_h * 0.93 and ln.width > 20.0
    ]
    def _label_only(ln: PageLine) -> bool:
        return bool(_EQ_ONLY_RE.fullmatch((ln.text or "").strip()))

    wide = [ln for ln in lines if ln.width >= 0.48 * page_w]
    if len(wide) >= 3:
        return max(0.0, min(ln.x0 for ln in wide) - 8.0), min(page_w, max(ln.x1 for ln in wide) + 8.0)
    cx = 0.5 * (float(seed[0]) + float(seed[2]))
    # 孤立 (n) 不是右栏证据，否则单栏论文会把编号残片当成整栏。
    right = [ln for ln in lines if ln.x0 > page_w * 0.40 and not _label_only(ln)]
    left = [ln for ln in lines if ln.x1 < page_w * 0.58]
    if cx >= page_w * 0.48 and right:
        return max(0.0, min(ln.x0 for ln in right) - 8.0), min(page_w, max(ln.x1 for ln in right) + 8.0)
    if left:
        return max(0.0, min(ln.x0 for ln in left) - 8.0), min(page_w, max(ln.x1 for ln in left) + 8.0)
    return max(0.0, float(seed[0]) - 80.0), min(page_w, float(seed[2]) + 24.0)


def looks_like_formula_line(text: str) -> bool:
    t = (text or "").strip()
    if not t or looks_like_prose(t):
        return False
    if line_eq_number(t):
        return True
    if any(ch in t for ch in "=∑∫√±×÷^_·⋅"):
        return True
    if re.search(r"\\[a-zA-Z]+", t):
        return True
    if len(t) <= 28 and re.search(r"[+\-*/=<>]", t):
        return True
    if len(t) <= 160 and _MATH_FRAG.search(t) and ("(" in t or ")" in t):
        return True
    return False


def detect_running_header_ymax(page: Any, siblings: Iterable[Any] | None = None) -> float:
    """页眉带下沿（PDF pt）。无页眉返回 0。"""
    page_h = float(page.rect.height)
    page_w = float(page.rect.width)
    band = page_h * 0.14
    lines = [ln for ln in iter_page_lines(page) if ln.y0 < band]
    if not lines:
        return 0.0

    sib_texts: set[str] = set()
    for sib in siblings or []:
        for ln in iter_page_lines(sib):
            t = ln.text.strip()
            if ln.y0 < band and len(t) >= 8:
                sib_texts.add(t)

    header_hits = [
        ln
        for ln in lines
        if _HEADER_RE.search(ln.text)
        or (
            ln.text.strip() in sib_texts
            and len(ln.text.strip()) >= 8
            and not looks_like_formula_line(ln.text)
        )
        or (
            re.fullmatch(r"\d{1,4}", ln.text.strip())
            and ln.x0 > page_w * 0.72
        )
    ]
    if not header_hits:
        return 0.0
    bottom = max(ln.y1 for ln in header_hits)
    for ln in lines:
        if ln.y0 < bottom + 3.0 and ln.y0 < page_h * 0.12:
            bottom = max(bottom, ln.y1)
    return bottom + 1.5


def _h_overlap(a: list[float], b: list[float]) -> float:
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0]))


def _v_overlap(a: list[float], b: list[float]) -> float:
    return max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def _area(b: list[float]) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _v_gap(a: PageLine, b: PageLine) -> float:
    if a.y1 < b.y0:
        return b.y0 - a.y1
    if b.y1 < a.y0:
        return a.y0 - b.y1
    return 0.0


def x_hits_seed(ln: PageLine, seed: list[float], slop: float = 4.0) -> bool:
    overlap = min(ln.x1, seed[2] + slop) - max(ln.x0, seed[0] - slop)
    if overlap <= 0:
        return False
    need = min(6.0, 0.2 * max(1.0, ln.width))
    return overlap >= need


def split_y_against_neighbors(
    seed: list[float],
    neighbors: list[list[float]],
) -> list[float]:
    x0, y0, x1, y1 = [float(v) for v in seed[:4]]
    cy = 0.5 * (y0 + y1)
    for nb in neighbors:
        if len(nb) < 4:
            continue
        if _h_overlap([x0, y0, x1, y1], nb) < 12.0:
            continue
        iy0, iy1 = max(y0, nb[1]), min(y1, nb[3])
        if iy1 - iy0 < 6.0:
            continue
        ncy = 0.5 * (nb[1] + nb[3])
        mid = 0.5 * (iy0 + iy1)
        if cy <= ncy:
            y1 = min(y1, mid)
        else:
            y0 = max(y0, mid)
    if y1 <= y0 + 4.0:
        return [float(v) for v in seed[:4]]
    return [x0, y0, x1, y1]


def crop_quality_tags(
    seed: list[float],
    header_ymax: float,
    neighbors: list[list[float]],
) -> list[str]:
    tags: list[str] = []
    if header_ymax > 0 and seed[1] < header_ymax - 0.5:
        tags.append("header_overlap")
    seed_area = _area(seed) or 1.0
    for nb in neighbors:
        if _h_overlap(seed, nb) < 12.0:
            continue
        inter = _h_overlap(seed, nb) * _v_overlap(seed, nb)
        if inter / seed_area >= 0.12:
            tags.append("neighbor_eq")
            break
    return tags


def _union(boxes: list[list[float]]) -> list[float]:
    return [
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    ]


def _apply_gold_pad(
    core: list[float],
    seed: list[float],
    page_rect: Any,
    column: tuple[float, float] | None = None,
    *,
    formula_only: bool = False,
) -> list[float]:
    x0, y0, x1, y1 = core
    w, h = max(1.0, x1 - x0), max(1.0, y1 - y0)
    px = min(GOLD_PAD_X_PT, max(2.0, w * GOLD_PAD_X_RATIO))
    py = min(GOLD_PAD_Y_PT, max(2.0, h * GOLD_PAD_Y_RATIO))
    x0 = max(0.0, x0 - px)
    y0 = max(0.0, y0 - py)
    x1 = min(float(page_rect.width), x1 + px)
    y1 = min(float(page_rect.height), y1 + py)
    if formula_only:
        # cluster 已按栏/邻式过滤；再夹 column 或 seed 会切掉编号或左半式
        pass
    elif column is not None:
        x0 = max(x0, float(column[0]))
        x1 = min(x1, float(column[1]))
    else:
        x0 = max(x0, seed[0] - GOLD_MAX_X_EXPAND_PT)
        x1 = min(x1, seed[2] + GOLD_MAX_X_EXPAND_PT)
    if x1 - x0 < 8.0 or y1 - y0 < 8.0:
        if formula_only:
            x0 = max(0.0, min(x0, core[0] - 4.0))
            y0 = max(0.0, min(y0, core[1] - 4.0))
            x1 = min(float(page_rect.width), max(x1, core[2] + 4.0))
            y1 = min(float(page_rect.height), max(y1, core[3] + 4.0))
            if column is not None:
                x0 = max(x0, float(column[0]))
                x1 = min(x1, float(column[1]))
            return [x0, y0, x1, y1]
        return [float(v) for v in seed[:4]]
    return [x0, y0, x1, y1]


def _x_close(ln: PageLine, box: list[float], slop: float = 28.0) -> bool:
    if _h_overlap(ln.bbox, box) > 0:
        return True
    return min(abs(ln.x1 - box[0]), abs(ln.x0 - box[2])) <= slop


def grow_equation_cluster(
    lines: list[PageLine],
    target: PageLine,
    *,
    seed: list[float],
    equation_number: str,
    column: tuple[float, float],
) -> list[PageLine]:
    """从编号行向外并入同一 display 的数学碎片，不并散文、不并邻式。"""
    eq = str(equation_number or "").strip()
    others = [
        ln
        for ln in lines
        if eq and line_eq_number(ln.text) and line_eq_number(ln.text) != eq
    ]
    cluster = [target]
    changed = True
    while changed:
        changed = False
        box = _union([ln.bbox for ln in cluster])
        for ln in lines:
            if ln in cluster:
                continue
            if not looks_like_math_fragment(ln.text):
                continue
            if ln.x0 > target.x1 + 8.0:
                continue
            other = line_eq_number(ln.text)
            if other and eq and other != eq:
                continue
            d_me = min(_v_gap(ln, m) for m in cluster)
            if d_me > 24.0:
                continue
            if others:
                d_ot = min(_v_gap(ln, o) for o in others)
                if d_ot + 1.0 < d_me:
                    continue
            if not (_x_close(ln, box) or x_hits_seed(ln, seed, slop=8.0)):
                continue
            if ln.x1 < column[0] - 1.0 or ln.x0 > column[1] + 1.0:
                continue
            cluster.append(ln)
            changed = True
    # 同一基线、编号左侧的非散文（补 lrate / Attention / ν(t,t') 被 seed 切掉的情况）
    seen = {id(ln) for ln in cluster}
    for ln in lines:
        if id(ln) in seen:
            continue
        if looks_like_prose(ln.text):
            continue
        if ln.x0 > target.x1 + 8.0:
            continue
        if abs(ln.cy - target.cy) > 16.0:
            continue
        if ln.x1 < column[0] - 1.0 or ln.x0 > column[1] + 1.0:
            continue
        other = line_eq_number(ln.text)
        if other and eq and other != eq:
            continue
        cluster.append(ln)
    return cluster


def cluster_is_label_only(cluster: list[PageLine]) -> bool:
    if len(cluster) == 1:
        return bool(_EQ_ONLY_RE.fullmatch((cluster[0].text or "").strip()))
    return False


def infer_equation_number(
    lines: list[PageLine],
    seed: list[float],
    page_w: float,
) -> tuple[str, PageLine | None]:
    """无编号 seed：找同一竖直带里最靠近的右侧 (n)。"""
    cy = 0.5 * (float(seed[1]) + float(seed[3]))
    band = max(36.0, 0.65 * max(8.0, float(seed[3]) - float(seed[1])))
    ranked: list[tuple[float, str, PageLine]] = []
    for ln in lines:
        eq = line_eq_number(ln.text)
        if not eq:
            continue
        if abs(ln.cy - cy) > band:
            continue
        if not (x_hits_seed(ln, seed, slop=24.0) or (seed[1] - 8.0 <= ln.cy <= seed[3] + 8.0)):
            continue
        score = abs(ln.cy - cy)
        if ln.x0 >= page_w * 0.52 and _EQ_ONLY_RE.fullmatch((ln.text or "").strip()):
            score -= 24.0
        ranked.append((score, eq, ln))
    if not ranked:
        return "", None
    ranked.sort(key=lambda item: item[0])
    return ranked[0][1], ranked[0][2]


def formula_lines_in_band(
    lines: list[PageLine],
    seed: list[float],
    column: tuple[float, float],
    *,
    y_pad: float = 10.0,
) -> list[PageLine]:
    y0, y1 = float(seed[1]) - y_pad, float(seed[3]) + y_pad
    hits: list[PageLine] = []
    for ln in lines:
        if ln.y1 < y0 or ln.y0 > y1:
            continue
        if ln.x1 < column[0] - 1.0 or ln.x0 > column[1] + 1.0:
            continue
        if looks_like_prose(ln.text):
            continue
        if looks_like_formula_line(ln.text) or looks_like_math_fragment(ln.text):
            hits.append(ln)
    return hits


def tight_bbox_for_equation(
    page: Any,
    seed_bbox: list[float],
    *,
    equation_number: str = "",
    neighbor_bboxes: list[list[float]] | None = None,
    header_ymax: float | None = None,
    siblings: Iterable[Any] | None = None,
) -> list[float]:
    """由生产 seed bbox 收出 Gold 评测框。不修改调用方传入的 seed。"""
    seed = [float(v) for v in seed_bbox[:4]]
    neighbors = [list(map(float, n[:4])) for n in (neighbor_bboxes or [])]
    if header_ymax is None:
        header_ymax = detect_running_header_ymax(page, siblings=siblings)
    clipped = list(seed)
    if header_ymax > 0:
        clipped[1] = max(clipped[1], header_ymax)
    if clipped[3] <= clipped[1] + 4.0:
        clipped = list(seed)
        if header_ymax > 0:
            clipped[1] = max(clipped[1], header_ymax)
    split = split_y_against_neighbors(clipped, neighbors)

    column = detect_text_column(page, seed)
    lines = [
        ln
        for ln in iter_page_lines(page)
        if ln.y1 > (header_ymax or 0) + 0.2
    ]
    eq = str(equation_number or "").strip()
    mine = [
        ln
        for ln in lines
        if eq and line_eq_number(ln.text) == eq and (x_hits_seed(ln, seed) or _x_close(ln, seed))
    ]
    if not mine:
        mine = [ln for ln in lines if eq and line_eq_number(ln.text) == eq]
    if not mine:
        inferred, target_ln = infer_equation_number(lines, split, float(page.rect.width))
        if target_ln is not None:
            eq = inferred or eq
            mine = [target_ln]

    core: list[float] | None = None
    formula_only = False
    if mine:
        target = min(mine, key=lambda ln: abs(ln.cy - 0.5 * (split[1] + split[3])))
        cluster = grow_equation_cluster(
            lines, target, seed=seed, equation_number=eq, column=column
        )
        if not cluster_is_label_only(cluster):
            core = _union([ln.bbox for ln in cluster])
            core[1] = max(core[1], header_ymax or 0.0)
            if core[3] > core[1] + 6.0:
                formula_only = True
            else:
                core = None

    if core is None:
        seed_h = float(split[3]) - float(split[1])
        band = formula_lines_in_band(lines, split, column) if seed_h <= 52.0 else []
        if band:
            core = _union([ln.bbox for ln in band])
            core[1] = max(core[1], header_ymax or 0.0)
            formula_only = True
        else:
            core = split
            if eq and mine:
                target = min(mine, key=lambda ln: abs(ln.cy - 0.5 * (split[1] + split[3])))
                half = max(14.0, target.height + 6.0)
                core = [
                    max(column[0], min(split[0], target.x0 - 8.0)),
                    max(split[1], header_ymax or 0.0, target.y0 - half),
                    min(column[1], max(split[2], target.x1 + 8.0)),
                    min(split[3], target.y1 + half),
                ]

    return _apply_gold_pad(core, seed, page.rect, column=column, formula_only=formula_only)


def text_in_bbox(page: Any, bbox: list[float]) -> str:
    import pymupdf

    return page.get_textbox(pymupdf.Rect(*[float(v) for v in bbox[:4]]))


def render_gold_tight_crop(
    pdf_path: Path,
    page: int,
    bbox: list[float],
    *,
    scale: float = CROP_SCALE,
) -> tuple[Any, int]:
    """紧框已含 gold pad，这里强制 pad=0，避免再套生产 10%/12%。"""
    return render_formula_crop(
        pdf_path,
        page,
        bbox,
        scale=scale,
        pad_x=0.0,
        pad_y=0.0,
    )


def tight_rel_path(pdf_id: str, record_id: str) -> str:
    return f"tight/{pdf_id}/{record_id}.png".replace("\\", "/")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def preserve_tight_fields(rows: list[dict[str, Any]], existing_path: Path) -> list[dict[str, Any]]:
    """重导 gold 时保留已有紧裁字段，避免把评测图路径冲掉。"""
    old = {r.get("id"): r for r in load_jsonl(existing_path)}
    keys = ("bbox_pdf_tight", "crop_path_tight", "crop_quality")
    for row in rows:
        prev = old.get(row.get("id")) or {}
        for k in keys:
            if prev.get(k) and not row.get(k):
                row[k] = prev[k]
    return rows


def preserve_verified_fields(rows: list[dict[str, Any]], existing_path: Path) -> list[dict[str, Any]]:
    """重导骨架时不得冲掉已人工核验的 Gold。"""
    old = {r.get("id"): r for r in load_jsonl(existing_path)}
    keep = (
        "gold_latex_raw",
        "gold_latex_canonical",
        "verified",
        "notes",
        "tags",
        "equation_number",
        "crop_quality",
    )
    for row in rows:
        prev = old.get(row.get("id")) or {}
        if not prev.get("verified") or not str(prev.get("gold_latex_raw") or "").strip():
            if prev.get("crop_quality") and not row.get("crop_quality"):
                row["crop_quality"] = prev["crop_quality"]
            if prev.get("notes") and "human" in str(prev.get("notes")):
                row["notes"] = prev["notes"]
            continue
        for k in keep:
            if prev.get(k) not in (None, "", []):
                row[k] = prev[k]
    return rows


def _resolve_page(doc: Any, page_field: int, eq: str, seed: list[float]) -> tuple[int, Any]:
    n = len(doc)
    chosen: tuple[int, Any] | None = None
    for idx in page_index_candidates(int(page_field), n):
        page = doc[idx]
        if eq:
            hits = [
                ln
                for ln in iter_page_lines(page)
                if line_eq_number(ln.text) == eq and x_hits_seed(ln, seed)
            ]
            if hits:
                return idx, page
        if chosen is None:
            chosen = (idx, page)
    if chosen is None:
        raise RuntimeError(f"no_page:{page_field}")
    return chosen


def _tight_dest(pdf_id: str, record_id: str, dest_root: Path) -> tuple[Path, str]:
    """返回 (写入路径, 相对 K5_CROPS_DIR 或 dest_root 的 rel)。"""
    name = f"{record_id}.png"
    dest = dest_root / pdf_id / name
    if dest_root.resolve() == K5_TIGHT_CROPS_DIR.resolve():
        return dest, tight_rel_path(pdf_id, record_id)
    return dest, f"{pdf_id}/{name}".replace("\\", "/")


def build_gold_tight_crops(
    records: list[dict[str, Any]],
    *,
    out_dir: Path | None = None,
    scale: float = CROP_SCALE,
    update_records: bool = True,
    write_manifest: bool = True,
    manifest_name: str = "manifest.json",
) -> dict[str, Any]:
    """为 gold/skeleton 记录切紧图。生产 crop 目录只读。"""
    dest_root = out_dir or K5_TIGHT_CROPS_DIR
    dest_root.mkdir(parents=True, exist_ok=True)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in records:
        grouped.setdefault(str(row.get("pdf_id") or ""), []).append(row)

    built: list[dict[str, Any]] = []
    import pymupdf

    for pdf_id, rows in grouped.items():
        if not pdf_id:
            continue
        pdf = resolve_pdf(pdf_id)
        if pdf is None:
            for row in rows:
                row.setdefault("crop_quality", ["pdf_missing"])
            continue
        doc = pymupdf.open(str(pdf))
        try:
            page_groups: dict[int, list[dict[str, Any]]] = {}
            for row in rows:
                page_groups.setdefault(int(row.get("page") or 0), []).append(row)
            for page_field, page_rows in page_groups.items():
                neighbor_map = {
                    str(r.get("id") or ""): [float(x) for x in (r.get("bbox_pdf") or [])[:4]]
                    for r in page_rows
                    if isinstance(r.get("bbox_pdf"), list) and len(r.get("bbox_pdf") or []) >= 4
                }
                for row in page_rows:
                    seed = [float(x) for x in (row.get("bbox_pdf") or [])[:4]]
                    if len(seed) < 4:
                        row["crop_quality"] = ["missing_bbox"]
                        continue
                    eq = str(row.get("equation_number") or "")
                    try:
                        idx, page = _resolve_page(doc, page_field, eq, seed)
                    except Exception as e:
                        row["crop_quality"] = [f"page_fail:{type(e).__name__}"]
                        continue
                    siblings = []
                    if idx > 0:
                        siblings.append(doc[idx - 1])
                    if idx + 1 < len(doc):
                        siblings.append(doc[idx + 1])
                    header_ymax = detect_running_header_ymax(page, siblings=siblings)
                    neighbors = [
                        bbox
                        for rid, bbox in neighbor_map.items()
                        if rid != str(row.get("id") or "") and len(bbox) == 4
                    ]
                    quality = crop_quality_tags(seed, header_ymax, neighbors)
                    tight = tight_bbox_for_equation(
                        page,
                        seed,
                        equation_number=eq,
                        neighbor_bboxes=neighbors,
                        header_ymax=header_ymax,
                        siblings=siblings,
                    )
                    if _area(tight) + 1.0 < 0.55 * _area(seed):
                        if "tightened" not in quality:
                            quality.append("tightened")
                    if tight[0] < seed[0] - 2.0:
                        if "left_completed" not in quality:
                            quality.append("left_completed")
                    dest, rel = _tight_dest(pdf_id, str(row.get("id") or "slot"), dest_root)
                    rec = {
                        "id": row.get("id"),
                        "pdf_id": pdf_id,
                        "page": page_field,
                        "page_index": idx,
                        "bbox_pdf": seed,
                        "bbox_pdf_tight": tight,
                        "crop_path_tight": rel,
                        "crop_quality": quality,
                        "equation_number": eq,
                        "crop_ok": False,
                        "error": "",
                    }
                    try:
                        image, used_idx = render_gold_tight_crop(pdf, page_field, tight, scale=scale)
                        rec["page_index"] = used_idx
                        w, h, digest = write_crop_png(image, dest)
                        rec.update({"width": w, "height": h, "sha256": digest, "crop_ok": True})
                    except Exception as e:
                        rec["error"] = f"{type(e).__name__}:{e}"
                    if update_records:
                        row["bbox_pdf_tight"] = tight
                        row["crop_path_tight"] = rel
                        row["crop_quality"] = quality
                    built.append(rec)
        finally:
            doc.close()

    manifest = {
        "scale": scale,
        "gold_only": True,
        "production_bbox_unchanged": True,
        "pad_x_pt": GOLD_PAD_X_PT,
        "pad_y_pt": GOLD_PAD_Y_PT,
        "n": len(built),
        "ok": sum(1 for r in built if r.get("crop_ok")),
        "failed": sum(1 for r in built if not r.get("crop_ok")),
        "crops": built,
    }
    if write_manifest:
        (dest_root / manifest_name).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return manifest
