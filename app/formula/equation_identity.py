"""EquationIdentity Resolver v2（Phase 5H）。

编号身份在 OCR 前确定；DeepSeek 只负责公式内容。

证据优先级：
  PDF printed label > defining prose Eq.(n) > local order > sequence continuity

低置信 → unresolved（不写编号），禁止猜测。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# 编号本体：1 / 4a / A.1 / A2 / S3 / 3.1
_EQ_LABEL_CORE = r"([A-Za-z]?\d+(?:\.\d+)?[A-Za-z]?|[A-Za-z]\.\d+|[Ss]\d+)"

_EQ_MENTION = re.compile(
    rf"(?:Eq(?:uation)?s?\.?\s*\(\s*{_EQ_LABEL_CORE}\s*\)|"
    rf"公式\s*[（(]\s*{_EQ_LABEL_CORE}\s*[）)])",
    re.I,
)
_PRINTED_LABEL = re.compile(rf"^\(\s*{_EQ_LABEL_CORE}\s*\)$")

NOT_DECODED_RE = re.compile(r"<!--\s*formula-not-decoded(?:\b[^>]*)?\s*-->", re.I)
_NOT_DECODED = NOT_DECODED_RE
_DISPLAY = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)

_DEFINING_CUES = re.compile(
    r"(?:"
    r"defined\s+by|defined\s+as|definition|"
    r"calculated\s+(?:by|using|from|as)|"
    r"computed\s+(?:by|using|from)|"
    r"given\s+(?:by|in|as)|"
    r"expressed\s+(?:by|as)|"
    r"written\s+as|"
    r"shown\s+(?:by|as|below)|"
    r"as\s+follows|"
    r"using\s+(?:the\s+)?(?:following\s+)?"
    r")\s*$",
    re.I,
)
_REFERENCE_CUES = re.compile(
    r"(?:"
    r"\bunlike\b|\bsee\b|cf\.?|\bcompare\b|according\s+to|\bfrom\b|"
    r"in\s+(?:eq|equation)|as\s+(?:in|shown\s+in)|"
    r"demonstrated\s+in|discussed\s+in|described\s+in|"
    r"refer(?:ring)?\s+to|based\s+on|"
    r"\bagainst\b|\bversus\b|\bvs\.?"
    r")\s*$",
    re.I,
)

HIGH_CONFIDENCE = 0.75
PDF_LABEL_SCORE = 1.0
DEFINING_PROSE_SCORE = 0.85
REFERENCE_PROSE_SCORE = 0.30
ORDER_SCORE = 0.35


@dataclass(frozen=True)
class EquationIdentity:
    equation_number: str
    slot_start: int
    slot_end: int
    slot_kind: str  # display | not_decoded
    candidate_id_hint: str = ""
    page: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    confidence: float = 0.0
    source: str = ""
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class FormulaSlot:
    start: int
    end: int
    kind: str


@dataclass(frozen=True)
class EquationMention:
    pos: int
    end: int
    label: str
    kind: str  # defining | reference
    raw: str = ""


@dataclass
class EquationIdentityQA:
    equation_identity_total: int = 0
    identity_high_confidence: int = 0
    identity_unresolved: int = 0
    identity_conflicts: int = 0
    identity_sources: dict[str, int] = field(default_factory=dict)
    identity_precision_note: str = "prefer_precision_over_coverage"

    def to_dict(self) -> dict[str, Any]:
        return {
            "equation_identity_total": self.equation_identity_total,
            "identity_high_confidence": self.identity_high_confidence,
            "identity_unresolved": self.identity_unresolved,
            "identity_conflicts": self.identity_conflicts,
            "identity_sources": dict(self.identity_sources),
            "identity_precision_note": self.identity_precision_note,
        }


def meaningful_context_window(
    markdown: str,
    pos: int,
    *,
    before: bool = True,
    window: int = 400,
    max_scan: int = 2400,
) -> str:
    """取公式槽邻近正文，跳过连续 formula-not-decoded 占位。"""
    if not markdown:
        return ""
    if before:
        scan_start = max(0, pos - max_scan)
        chunk = markdown[scan_start:pos]
    else:
        scan_end = min(len(markdown), pos + max_scan)
        chunk = markdown[pos:scan_end]

    cleaned = NOT_DECODED_RE.sub("\n", chunk)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    parts = [p.strip() for p in re.split(r"\n\s*\n", cleaned) if p.strip()]

    acc: list[str] = []
    total = 0
    seq = reversed(parts) if before else parts
    for p in seq:
        if len(p) < 8 and not re.search(r"[A-Za-z]{3}", p):
            continue
        if before:
            acc.insert(0, p)
        else:
            acc.append(p)
        total += len(p) + 2
        if total >= window:
            break

    text = "\n\n".join(acc)
    if before and len(text) > window:
        return text[-window:]
    if not before and len(text) > window:
        return text[:window]
    return text


def normalize_eq_label(label: str) -> str:
    return re.sub(r"\s+", "", (label or "").strip())


def safe_eq_id_token(label: str) -> str:
    s = normalize_eq_label(label)
    s = re.sub(r"[^A-Za-z0-9.]+", "", s)
    return s or "i"


def iter_formula_slots(markdown: str) -> list[FormulaSlot]:
    slots: list[FormulaSlot] = []
    for m in _NOT_DECODED.finditer(markdown or ""):
        slots.append(FormulaSlot(m.start(), m.end(), "not_decoded"))
    for m in _DISPLAY.finditer(markdown or ""):
        slots.append(FormulaSlot(m.start(), m.end(), "display"))
    slots.sort(key=lambda s: s.start)
    out: list[FormulaSlot] = []
    last_end = -1
    for s in slots:
        if s.start < last_end:
            continue
        out.append(s)
        last_end = s.end
    return out


def classify_equation_mention(*, before: str, after: str, raw: str = "") -> str:
    del raw
    b = (before or "")[-80:]
    a = (after or "")[:40]
    if re.match(r"^\s*[:：]", a):
        return "defining"
    if _REFERENCE_CUES.search(b):
        return "reference"
    if _DEFINING_CUES.search(b):
        return "defining"
    if re.search(r"\busing\b\s*$", b, re.I):
        return "defining"
    if re.search(r"\bby\b\s*$", b, re.I):
        return "defining"
    # TPR Eq. (6) / FPR Eq. (7) 等同句指标+编号列举
    if re.search(
        r"\b(?:TPR|FPR|Precision|Recall|F1|MSE|RMSE|MAE|AUC|ROC|Bias|Variance)\s*$",
        b,
        re.I,
    ):
        return "defining"
    if re.search(r"Eq\.?\s*\(\s*\d+\s*\)\s*,", b, re.I):
        return "defining"
    return "reference"


def iter_equation_mentions(markdown: str) -> list[EquationMention]:
    md = markdown or ""
    out: list[EquationMention] = []
    for m in _EQ_MENTION.finditer(md):
        label = normalize_eq_label(m.group(1) or m.group(2) or "")
        if not label:
            continue
        before = md[max(0, m.start() - 80) : m.start()]
        after = md[m.end() : m.end() + 40]
        kind = classify_equation_mention(before=before, after=after, raw=m.group(0))
        out.append(
            EquationMention(
                pos=m.start(), end=m.end(), label=label, kind=kind, raw=m.group(0)
            )
        )
    return out


def _column_bounds_for_formula(
    page_w: float, fx0: float, fx1: float
) -> tuple[float, float]:
    mid = page_w * 0.5
    fcx = (fx0 + fx1) * 0.5
    if fcx >= mid - 12.0:
        return max(0.0, mid - 8.0), page_w
    return 0.0, min(page_w, mid + 8.0)


def find_pdf_printed_label(
    page: Any,
    formula_bbox: tuple[float, float, float, float],
) -> tuple[str, float, str] | None:
    """公式同行邻域找印刷编号；限制在所属栏内。"""
    try:
        page_w = float(page.rect.width)
        words = page.get_text("words") or []
    except Exception:
        return None
    fx0, fy0, fx1, fy1 = (float(x) for x in formula_bbox)
    col_x0, col_x1 = _column_bounds_for_formula(page_w, fx0, fx1)
    fy_mid = (fy0 + fy1) * 0.5
    band = max(14.0, (fy1 - fy0) * 0.85)

    best: tuple[str, float, str] | None = None
    best_dist = 1e18
    for w in words:
        if len(w) < 5:
            continue
        x0, y0, x1, y1, token = (
            float(w[0]),
            float(w[1]),
            float(w[2]),
            float(w[3]),
            str(w[4]),
        )
        m = _PRINTED_LABEL.match(token.strip())
        if not m:
            continue
        label = normalize_eq_label(m.group(1))
        if not label or label == "0":
            continue
        if x1 < col_x0 - 2 or x0 > col_x1 + 2:
            continue
        cy = (y0 + y1) * 0.5
        if abs(cy - fy_mid) > band:
            continue
        right = x0 >= fx1 - 4.0 and x0 <= col_x1 + 2.0
        left = x1 <= fx0 + 4.0 and x1 >= col_x0 - 2.0
        if not (right or left):
            if x0 >= fx1 - 40.0 and x0 <= fx1 + 80.0 and abs(cy - fy_mid) < band:
                right = True
            else:
                continue
        dist = abs(x0 - fx1) if right else abs(fx0 - x1)
        side = "right" if right else "left"
        if dist < best_dist:
            best_dist = dist
            best = (label, PDF_LABEL_SCORE, f"pdf_{side}_label:({label})")
    return best


def _greedy_one_to_one(
    scores: list[list[float]], *, min_score: float
) -> dict[int, int]:
    n_s = len(scores)
    n_l = len(scores[0]) if scores else 0
    pairs: list[tuple[float, int, int]] = []
    for i in range(n_s):
        for j in range(n_l):
            s = scores[i][j]
            if s >= min_score:
                pairs.append((s, i, j))
    pairs.sort(key=lambda t: (-t[0], t[1], t[2]))
    used_s: set[int] = set()
    used_l: set[int] = set()
    out: dict[int, int] = {}
    for _s, i, j in pairs:
        if i in used_s or j in used_l:
            continue
        used_s.add(i)
        used_l.add(j)
        out[i] = j
    return out


def resolve_equation_identities(
    markdown: str,
    *,
    slot_geometry: dict[int, tuple[int, tuple[float, float, float, float]]] | None = None,
    pdf_doc: Any | None = None,
    high_confidence: float = HIGH_CONFIDENCE,
) -> tuple[dict[int, EquationIdentity], EquationIdentityQA]:
    """slot_start → 高置信 EquationIdentity；低置信不进结果（unresolved）。"""
    md = markdown or ""
    slots = iter_formula_slots(md)
    mentions = iter_equation_mentions(md)
    geom = slot_geometry or {}
    qa = EquationIdentityQA(equation_identity_total=len(slots))

    if not slots:
        return {}, qa

    label_universe: list[str] = []
    label_index: dict[str, int] = {}

    def _lab_i(lab: str) -> int:
        lab = normalize_eq_label(lab)
        if lab not in label_index:
            label_index[lab] = len(label_universe)
            label_universe.append(lab)
        return label_index[lab]

    pdf_hits: dict[int, tuple[str, float, str]] = {}
    if pdf_doc is not None:
        for si, slot in enumerate(slots):
            g = geom.get(slot.start)
            if not g:
                continue
            page_i, bbox = g
            try:
                page = pdf_doc[int(page_i)]
            except Exception:
                continue
            hit = find_pdf_printed_label(page, bbox)
            if hit:
                pdf_hits[si] = hit
                _lab_i(hit[0])

    for m in mentions:
        _lab_i(m.label)

    if not label_universe:
        qa.identity_unresolved = len(slots)
        return {}, qa

    n_s, n_l = len(slots), len(label_universe)
    scores = [[0.0 for _ in range(n_l)] for _ in range(n_s)]
    evidence_map: dict[tuple[int, int], list[str]] = {}
    source_map: dict[tuple[int, int], str] = {}

    def _add(si: int, lab: str, score: float, ev: str, source: str) -> None:
        ji = _lab_i(lab)
        if score >= scores[si][ji]:
            scores[si][ji] = score
            source_map[(si, ji)] = source
        evidence_map.setdefault((si, ji), []).append(ev)

    for si, (lab, sc, ev) in pdf_hits.items():
        _add(si, lab, sc, ev, "pdf_printed_label")

    # defining mentions：给其后槽加分；同句多编号（Eq6, Eq7）给连续槽
    # 若两 mention 之间已有公式槽，不得并入同一簇（否则会跳过中间公式）
    defining = [m for m in mentions if m.kind == "defining"]

    def _formula_between(a_end: int, b_pos: int) -> bool:
        return any(a_end < s.start < b_pos for s in slots)

    consumed_defining = set()
    for cluster_start in range(len(defining)):
        if cluster_start in consumed_defining:
            continue
        cluster = [defining[cluster_start]]
        consumed_defining.add(cluster_start)
        for k in range(cluster_start + 1, len(defining)):
            prev = cluster[-1]
            cur = defining[k]
            if cur.pos - prev.pos >= 120:
                break
            if _formula_between(prev.end, cur.pos):
                break
            cluster.append(cur)
            consumed_defining.add(k)
        first_slot = None
        for si, slot in enumerate(slots):
            if slot.start > cluster[-1].end:
                first_slot = si
                break
        if first_slot is None:
            continue
        for k, m in enumerate(cluster):
            si = first_slot + k
            if si >= n_s:
                break
            gap = slots[si].start - m.end
            if gap > 1200:
                break
            base = DEFINING_PROSE_SCORE
            if gap < 200:
                base = min(0.95, base + 0.08)
            # 簇内第 k 个 mention 也可以绑到 first_slot+k；
            # 若簇在首槽之前（Eq6,Eq7 同句后两槽），用 mention 序对齐
            _add(
                si,
                m.label,
                base,
                f"prose_definition:{m.raw or m.label}",
                "prose_definition",
            )
        # 同句多编号且公式紧跟在簇后：按簇序对齐连续槽
        if len(cluster) >= 2 and first_slot is not None:
            for k, m in enumerate(cluster):
                si = first_slot + k
                if si >= n_s:
                    break
                _add(
                    si,
                    m.label,
                    min(0.95, DEFINING_PROSE_SCORE + 0.08),
                    f"prose_definition_cluster:{m.label}",
                    "prose_definition",
                )

    # reference：弱分，默认不够高置信
    for m in mentions:
        if m.kind != "reference":
            continue
        for si, slot in enumerate(slots):
            if slot.start <= m.pos:
                continue
            gap = slot.start - m.end
            if gap > 600:
                break
            _add(
                si,
                m.label,
                REFERENCE_PROSE_SCORE,
                f"prose_reference:{m.raw or m.label}",
                "prose_reference",
            )
            break

    # 局部顺序弱证据（不够单独过阈值）
    if len(defining) >= 2:
        first_slot = None
        for si, slot in enumerate(slots):
            if slot.start > defining[0].pos:
                first_slot = si
                break
        if first_slot is not None:
            for k, m in enumerate(defining):
                si = first_slot + k
                if si >= n_s:
                    break
                _add(si, m.label, ORDER_SCORE, f"local_order:{m.label}", "local_order")

    assignment = _greedy_one_to_one(scores, min_score=high_confidence)

    by_start: dict[int, EquationIdentity] = {}
    for si, ji in assignment.items():
        slot = slots[si]
        lab = label_universe[ji]
        sc = scores[si][ji]
        if sc < high_confidence:
            continue
        ev = evidence_map.get((si, ji), [])
        src = source_map.get((si, ji), "unknown")
        ev_join = " ".join(ev)
        # 禁止仅靠 order/reference/prior 猜测
        if src in {"local_order", "prose_reference", "prior"} and "pdf_" not in ev_join:
            if "prose_definition" not in ev_join:
                continue
        g = geom.get(slot.start)
        page = int(g[0]) if g else None
        bbox = g[1] if g else None
        ident = EquationIdentity(
            equation_number=lab,
            slot_start=slot.start,
            slot_end=slot.end,
            slot_kind=slot.kind,
            candidate_id_hint=f"eq{safe_eq_id_token(lab)}",
            page=page,
            bbox=bbox,
            confidence=round(sc, 3),
            source=src,
            evidence=tuple(ev),
        )
        by_start[slot.start] = ident
        qa.identity_high_confidence += 1
        qa.identity_sources[src] = qa.identity_sources.get(src, 0) + 1

    qa.identity_unresolved = max(0, len(slots) - len(by_start))
    return by_start, qa


def bind_equation_identities(markdown: str) -> dict[int, EquationIdentity]:
    """兼容旧 API：无 PDF，v2 prose + 一对一。"""
    ids, _qa = resolve_equation_identities(markdown)
    return ids


def bind_equation_identities_v2(
    markdown: str,
    *,
    slot_geometry: dict[int, tuple[int, tuple[float, float, float, float]]] | None = None,
    pdf_doc: Any | None = None,
) -> tuple[dict[int, EquationIdentity], EquationIdentityQA]:
    return resolve_equation_identities(
        markdown, slot_geometry=slot_geometry, pdf_doc=pdf_doc
    )


def equation_number_for_span(
    markdown: str, start: int, identities: dict[int, EquationIdentity] | None = None
) -> str:
    ids = identities if identities is not None else bind_equation_identities(markdown)
    hit = ids.get(start)
    return hit.equation_number if hit else ""
