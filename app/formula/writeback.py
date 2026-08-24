"""Phase 4C — Controlled Writeback：按 candidate_id 精确替换，可 rollback。

禁止：markdown.replace / regex 全文搜 / 按 Eq.(n) 猜位置 / 写回未 Gate accept 的结果。
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from app.formula.config import FormulaConfig
from app.formula.release_gate import check_release
from app.formula.types import DocumentQuality


def content_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


@dataclass
class FormulaBlockRef:
    """文档内可写回的公式块定位（注册时记录，禁止事后文本搜索）。"""

    candidate_id: str
    start: int
    end: int
    original_inner: str
    original_full: str  # 含 $$ 或 $ 包裹
    content_hash: str
    wrap: str = "display"  # display | inline
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


ALLOWED_WRITEBACK_MODES = frozenset(
    {"formula", "formula_batch", "page", "page_reuse", ""}
)
HIGH_CONFIDENCE_MARKERS = frozenset(
    {"gain_accept", "accept_despite_insufficient_context"}
)


def normalize_latex_signature(latex: str) -> str:
    """粗归一：去空白与 $，便于同页重复检测。"""
    import re

    s = (latex or "").strip()
    s = s.replace("$$", "").replace("$", "")
    s = re.sub(r"\s+", "", s)
    s = s.replace("\\left", "").replace("\\right", "")
    return s.lower()


def latex_signature_similarity(a: str, b: str) -> float:
    from difflib import SequenceMatcher

    sa, sb = normalize_latex_signature(a), normalize_latex_signature(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return float(SequenceMatcher(None, sa, sb).ratio())


def _latex_lhs_key(sig: str) -> str:
    """取归一化后 '=' 左侧（如 mathrm{fpr}），用于区分 TPR/FPR。"""
    s = (sig or "").strip()
    if "=" not in s:
        return ""
    return s.split("=", 1)[0]


def candidate_eq_ambiguous(candidate_id: str, eq_number: str | None = None) -> bool:
    """无明确 Eq.(n) 时视为对齐弱（eqi / 空编号）。"""
    cid = candidate_id or ""
    if "_eqi" in cid.lower():
        return True
    eq = (eq_number or "").strip()
    if not eq:
        # page6_eq1 → 有数字不算 ambiguous
        import re

        m = re.search(r"_eq(\d+)$", cid, re.I)
        if m:
            return False
        m2 = re.search(r"_eq([A-Za-z].*)$", cid, re.I)
        if m2 and not m2.group(1).isdigit():
            return True
        return "_eq" not in cid.lower()
    return not eq.isdigit()


def find_multi_formula_alignment_conflicts(
    items: list["RecoveryWritebackItem"],
    *,
    similarity_threshold: float = 0.9,
) -> set[str]:
    """同页多个「编号模糊」且恢复结果高度重复/冲突 → 候选对（可能含两侧）。"""
    from collections import defaultdict

    by_page: dict[int | None, list[RecoveryWritebackItem]] = defaultdict(list)
    for it in items:
        if not it.gate_accepted or not it.would_replace:
            continue
        if not (it.recovered_latex or "").strip():
            continue
        page = page_from_candidate_id(it.candidate_id, it.page)
        by_page[page].append(it)

    conflicted: set[str] = set()
    for _page, group in by_page.items():
        weak = [it for it in group if candidate_eq_ambiguous(it.candidate_id)]
        if len(weak) < 2:
            continue
        for i in range(len(weak)):
            for j in range(i + 1, len(weak)):
                a, b = weak[i].recovered_latex, weak[j].recovered_latex
                sa, sb = normalize_latex_signature(a), normalize_latex_signature(b)
                sim = latex_signature_similarity(a, b)
                same = sa == sb
                same_lhs = bool(_latex_lhs_key(sa) and _latex_lhs_key(sa) == _latex_lhs_key(sb))
                if same or (sim >= similarity_threshold and same_lhs):
                    conflicted.add(weak[i].candidate_id)
                    conflicted.add(weak[j].candidate_id)
    return conflicted


_PLACEHOLDER_ORIGINALS = frozenset(
    {
        r"\quad\quad\quadgarbage",
        "garbage1",
        "garbage2",
        "<!--formula-not-decoded-->",
    }
)


def _is_placeholder_original(original: str) -> bool:
    import re

    o = re.sub(r"\s+", "", (original or "").strip().lower())
    if not o:
        return True
    if o in _PLACEHOLDER_ORIGINALS:
        return True
    if "formula-not-decoded" in o:
        return True
    if o.startswith(r"\quad") and len(o) < 48:
        return True
    return False


def _context_recovery_score(context_before: str, recovered: str) -> float:
    """占位原文时用邻近正文与 OCR 结果对齐（O-003 eqi 拆槽）。"""
    import re

    from app.formula.tokens import (
        extract_math_tokens,
        extract_symbol_signature,
        interesting,
        symbol_overlap_ratio,
    )

    rec = (recovered or "").strip()
    ctx = (context_before or "")[-420:]
    if not rec or not ctx.strip():
        return 0.0
    rt = interesting(extract_math_tokens(rec))
    ct = interesting(extract_math_tokens(ctx))
    score = 0.0
    if rt and ct:
        score = len(rt & ct) / max(1, len(rt | ct))
    else:
        score = symbol_overlap_ratio(
            extract_symbol_signature(ctx), extract_symbol_signature(rec)
        )
    ctx_l = ctx.lower()
    rec_l = rec.lower()
    if re.search(r"(?<![a-z])vi\b", ctx_l) and "vi(" in rec_l.replace(" ", ""):
        score += 0.35
    if re.search(r"(?<![a-z])vl\b", ctx_l) and "vl(" in rec_l.replace(" ", ""):
        score += 0.35
    if "f1" in ctx_l and "f1" in rec_l:
        score += 0.25
    if "brier" in ctx_l and "brier" in rec_l:
        score += 0.25
    if re.search(r"eq\.\s*\(\s*6", ctx_l) and "tpr" in rec_l:
        score += 0.4
    if re.search(r"eq\.\s*\(\s*7", ctx_l) and "fpr" in rec_l:
        score += 0.4
    return min(1.0, score)


def _original_recovery_score(
    original: str,
    recovered: str,
    *,
    context_before: str = "",
) -> float:
    """原文与 OCR 结果的符号/词元重合度，用于同页重复 OCR 拆槽。"""
    import re

    from app.formula.tokens import (
        extract_math_tokens,
        extract_symbol_signature,
        interesting,
        symbol_overlap_ratio,
    )

    rec = (recovered or "").strip()
    if not rec:
        return 0.0
    if _is_placeholder_original(original):
        return _context_recovery_score(context_before, rec)

    orig = re.sub(r"\s+", "", (original or "").strip())
    if not orig:
        return 0.0
    ot = interesting(extract_math_tokens(orig))
    rt = interesting(extract_math_tokens(rec))
    score = 0.0
    if ot and rt:
        score = len(ot & rt) / max(1, len(ot | rt))
    else:
        score = symbol_overlap_ratio(
            extract_symbol_signature(orig), extract_symbol_signature(rec)
        )
    if re.search(r"p_\{?t\+1|pt\+1", orig, re.I) and re.search(
        r"p_\{?t\+1|mathbf\{p\}_\{t\+1\}", rec, re.I
    ):
        score += 0.45
    if re.search(r"(?<![A-Za-z])Q(?![A-Za-z])", orig) and re.search(
        r"(?<![A-Za-z])Q(?![A-Za-z])", rec
    ):
        score += 0.25
    if re.search(r"e\s*\^|exp", original or "", re.I) and re.search(
        r"e\s*\^|exp", rec, re.I
    ):
        score += 0.45
    if re.search(r"p_\{?t\+1|pt\+1", orig, re.I) and not re.search(
        r"e\s*\^|exp", rec, re.I
    ):
        score += 0.1
    return min(1.0, score)


def resolve_multi_formula_alignment_conflicts(
    items: list["RecoveryWritebackItem"],
    *,
    similarity_threshold: float = 0.9,
    score_margin: float = 0.06,
) -> set[str]:
    """同页重复 OCR：只封与原文匹配更差的一侧；无法区分则仍双封（O-018 FPR）。"""
    from collections import defaultdict

    pairs = find_multi_formula_alignment_conflicts(
        items, similarity_threshold=similarity_threshold
    )
    if not pairs:
        return set()

    by_page: dict[int | None, list[RecoveryWritebackItem]] = defaultdict(list)
    for it in items:
        if it.candidate_id not in pairs:
            continue
        if not it.gate_accepted or not it.would_replace:
            continue
        by_page[page_from_candidate_id(it.candidate_id, it.page)].append(it)

    blocked: set[str] = set()
    for group in by_page.values():
        clusters: dict[str, list[RecoveryWritebackItem]] = defaultdict(list)
        for it in group:
            sig = normalize_latex_signature(it.recovered_latex or "")
            clusters[sig].append(it)
        for cluster in clusters.values():
            if len(cluster) < 2:
                continue
            scored = [
                (
                    it,
                    _original_recovery_score(
                        it.original or "",
                        it.recovered_latex or "",
                        context_before=it.context_before or "",
                    ),
                )
                for it in cluster
            ]
            scored.sort(key=lambda x: x[1], reverse=True)
            best = scored[0][1]
            if best <= 0.0:
                blocked.update(it.candidate_id for it, _ in scored)
                continue
            winners = [it for it, sc in scored if sc >= best - score_margin]
            if len(winners) != 1:
                blocked.update(it.candidate_id for it, _ in scored)
                continue
            winner_id = winners[0].candidate_id
            blocked.update(it.candidate_id for it, _ in scored if it.candidate_id != winner_id)
    return blocked


def find_monotonic_eq_order_conflicts(
    items: list["RecoveryWritebackItem"],
    *,
    min_group: int = 2,
) -> set[str]:
    """同页按 bbox 纵坐标排序后，印刷编号须单调不减；否则整组拒写。"""
    from collections import defaultdict

    by_page: dict[int | None, list[RecoveryWritebackItem]] = defaultdict(list)
    for it in items:
        if not it.gate_accepted or not it.would_replace:
            continue
        if not (it.recovered_latex or "").strip():
            continue
        lab = equation_label_from_candidate_id(it.candidate_id)
        if not lab.isdigit():
            continue
        page = page_from_candidate_id(it.candidate_id, it.page)
        by_page[page].append(it)

    conflicted: set[str] = set()
    for _page, group in by_page.items():
        if len(group) < min_group:
            continue
        ordered = sorted(
            group,
            key=lambda it: (
                float(it.bbox[1]) if it.bbox and len(it.bbox) >= 2 else 10**9,
                page_from_candidate_id(it.candidate_id, it.page) or 0,
            ),
        )
        eq_nums = [
            int(equation_label_from_candidate_id(it.candidate_id))
            for it in ordered
        ]
        if eq_nums != sorted(eq_nums):
            conflicted.update(it.candidate_id for it in ordered)
    return conflicted


def classify_gate_decision(*, gate_accepted: bool, gate_reason: str) -> str:
    """初版置信度：仅 gain_accept → ACCEPT_HIGH_CONFIDENCE。"""
    if not gate_accepted:
        return "REJECT"
    parts = {p.strip() for p in (gate_reason or "").split(",") if p.strip()}
    if parts & HIGH_CONFIDENCE_MARKERS and "ocr_context_conflict" not in parts:
        return "ACCEPT_HIGH_CONFIDENCE"
    if gate_accepted:
        return "ACCEPT_BORDERLINE"
    return "REJECT"


def page_from_candidate_id(candidate_id: str, explicit_page: int | None = None) -> int | None:
    if explicit_page is not None:
        return int(explicit_page)
    m = re.search(r"page[_-]?(\d+)", candidate_id or "", re.I)
    if m:
        return int(m.group(1))
    return None


@dataclass
class RecoveryWritebackItem:
    """Executor/Shadow 结构化写回请求。"""

    candidate_id: str
    recovered_latex: str
    gate_accepted: bool = False
    would_replace: bool = False
    gate_reason: str = ""
    original: str = ""
    error: str = ""
    scheduler_mode: str = ""
    page: int | None = None
    gate_decision: str = ""
    unresolved: bool = False
    eq_number: str = ""
    context_before: str = ""
    context_after: str = ""
    bbox: tuple[float, float, float, float] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WritebackEntry:
    candidate_id: str
    original: str = ""
    replacement: str = ""
    accepted: bool = False
    gate_reason: str = ""
    gate_decision: str = ""
    writeback_applied: bool = False
    dry_run: bool = True
    rollback_reason: str = ""
    skip_reason: str = ""
    content_hash_before: str = ""
    content_hash_after: str = ""
    page: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WritebackReport:
    enabled: bool
    dry_run: bool
    markdown_before: str
    markdown_after: str
    entries: list[WritebackEntry] = field(default_factory=list)
    applied_count: int = 0
    skipped_count: int = 0
    rolled_back_count: int = 0
    release_gate: dict[str, Any] = field(default_factory=dict)
    document_status: str = "ok"  # ok | formula_incomplete
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "dry_run": self.dry_run,
            "applied_count": self.applied_count,
            "skipped_count": self.skipped_count,
            "rolled_back_count": self.rolled_back_count,
            "unchanged": self.markdown_before == self.markdown_after,
            "release_gate": self.release_gate,
            "document_status": self.document_status,
            "error": self.error,
            "entries": [e.to_dict() for e in self.entries],
            "markdown_changed": self.markdown_before != self.markdown_after,
        }


class FormulaBlockRegistry:
    """candidate_id → 精确 span。重复 ID fail-closed。"""

    def __init__(self) -> None:
        self._blocks: dict[str, FormulaBlockRef] = {}

    def __len__(self) -> int:
        return len(self._blocks)

    def get(self, candidate_id: str) -> FormulaBlockRef | None:
        return self._blocks.get(candidate_id)

    def ids(self) -> list[str]:
        return list(self._blocks.keys())

    def register(self, block: FormulaBlockRef) -> None:
        cid = (block.candidate_id or "").strip()
        if not cid:
            raise ValueError("empty_candidate_id")
        if cid in self._blocks:
            raise ValueError(f"duplicate_candidate_id:{cid}")
        if block.start < 0 or block.end <= block.start:
            raise ValueError(f"invalid_span:{cid}")
        self._blocks[cid] = block

    def register_from_markdown_spans(
        self,
        markdown: str,
        spans: Iterable[tuple[str, int, int, str]],
    ) -> None:
        """spans: (candidate_id, start, end, wrap) 其中 [start:end] 为完整 $...$ / $$...$$。"""
        for cid, start, end, wrap in spans:
            full = markdown[start:end]
            if wrap == "display":
                if not (full.startswith("$$") and full.endswith("$$")):
                    raise ValueError(f"span_not_display:{cid}")
                inner = full[2:-2]
            else:
                if not (full.startswith("$") and full.endswith("$") and not full.startswith("$$")):
                    raise ValueError(f"span_not_inline:{cid}")
                inner = full[1:-1]
            self.register(
                FormulaBlockRef(
                    candidate_id=cid,
                    start=start,
                    end=end,
                    original_inner=inner,
                    original_full=full,
                    content_hash=content_hash(full),
                    wrap=wrap,
                )
            )


def build_display_block(latex: str) -> str:
    """行间公式标准围栏：多行 $$ / body / $$（勿写成单行 $$...$$，Typora 下 \\tag 常不显示）。"""
    body = (latex or "").strip()
    if body.startswith("$$") and body.endswith("$$"):
        body = body[2:-2].strip()
    body = body.strip().strip("$").strip()
    return f"$$\n{body}\n$$"


def build_inline_block(latex: str) -> str:
    body = (latex or "").strip().strip("$")
    return f"${body}$"


_EQ_ID_UNRESOLVED = re.compile(r"_eqi\d+$", re.I)
_EQ_ID_LABEL = re.compile(r"_eq(.+)$", re.I)


def equation_label_from_candidate_id(candidate_id: str) -> str:
    """page7_eq6 → 6；page7_eqA.1 → A.1；page7_eqi2 → ''（不打 tag）。"""
    cid = (candidate_id or "").strip()
    if not cid or _EQ_ID_UNRESOLVED.search(cid):
        return ""
    m = _EQ_ID_LABEL.search(cid)
    if not m:
        return ""
    lab = m.group(1).strip()
    # 去掉可能的后缀 _2 撞名修复
    lab = re.sub(r"_\d+$", "", lab)
    return lab


def inject_equation_tag(latex: str, tag: str) -> str:
    """在公式体末尾插入 \\tag{n}（不包 $$）。已有 tag 则替换。"""
    tag = (tag or "").strip()
    body = (latex or "").strip()
    if body.startswith("$$") and body.endswith("$$"):
        body = body[2:-2].strip()
    body = body.strip().strip("$").strip()
    # 去掉已有 \tag{...} / \tag*{...}
    body = re.sub(r"\\tag\*?\{[^}]*\}\s*", "", body).rstrip()
    if not tag:
        return body
    return f"{body}\\tag{{{tag}}}"


def latex_with_optional_tag(
    latex: str,
    *,
    candidate_id: str = "",
    eq_number: str | None = None,
    preserve: bool = True,
) -> str:
    if not preserve:
        body = (latex or "").strip()
        if body.startswith("$$") and body.endswith("$$"):
            return body[2:-2].strip()
        return body.strip().strip("$")
    tag = (eq_number or "").strip() or equation_label_from_candidate_id(candidate_id)
    return inject_equation_tag(latex, tag)


class FormulaWritebackManager:
    """受控写回：只按 registry 中的 candidate_id 替换。"""

    def __init__(self, config: FormulaConfig | None = None) -> None:
        self.config = config or FormulaConfig()

    def validate_target(
        self,
        markdown: str,
        registry: FormulaBlockRegistry,
        candidate_id: str,
    ) -> tuple[bool, str, FormulaBlockRef | None]:
        block = registry.get(candidate_id)
        if block is None:
            return False, "candidate_id_not_found", None
        if block.end > len(markdown) or block.start < 0:
            return False, "span_out_of_range", block
        current = markdown[block.start : block.end]
        if current != block.original_full:
            return False, "stale_content_mismatch", block
        if content_hash(current) != block.content_hash:
            return False, "stale_content_hash", block
        return True, "", block

    def apply(
        self,
        markdown: str,
        recovery_results: list[RecoveryWritebackItem] | list[dict[str, Any]],
        registry: FormulaBlockRegistry,
        *,
        force_enabled: bool | None = None,
        force_dry_run: bool | None = None,
        false_risk_signals: int = 0,
        unresolved_formula_count: int = 0,
    ) -> WritebackReport:
        from app.formula.config import normalize_preset

        cfg = self.config
        enabled = (
            bool(cfg.deepseek_recovery_writeback_enabled)
            if force_enabled is None
            else bool(force_enabled)
        )
        dry_run = (
            bool(cfg.deepseek_recovery_writeback_dry_run)
            if force_dry_run is None
            else bool(force_dry_run)
        )
        # 未启用写回 → 强制 dry-run 语义且正文不变；若 enabled=False 无论 dry_run 都不改文
        effective_mutate = bool(enabled and not dry_run)

        items = [_coerce_item(x) for x in recovery_results]
        for it in items:
            if not it.gate_decision:
                it.gate_decision = classify_gate_decision(
                    gate_accepted=it.gate_accepted, gate_reason=it.gate_reason
                )

        report = WritebackReport(
            enabled=enabled,
            dry_run=dry_run or not enabled,
            markdown_before=markdown,
            markdown_after=markdown,
            document_status="formula_incomplete" if unresolved_formula_count > 0 else "ok",
        )

        if not enabled and not dry_run:
            # disabled 且非 dry_run：仍不改文，全部 skip（退化 4B shadow）
            for it in items:
                report.entries.append(
                    WritebackEntry(
                        candidate_id=it.candidate_id,
                        original=it.original,
                        replacement=it.recovered_latex,
                        accepted=it.gate_accepted,
                        gate_reason=it.gate_reason,
                        gate_decision=it.gate_decision,
                        writeback_applied=False,
                        dry_run=False,
                        skip_reason="writeback_disabled",
                        page=page_from_candidate_id(it.candidate_id, it.page),
                    )
                )
                report.skipped_count += 1
            return report

        # 有限生产仅 Balanced
        if cfg.deepseek_limited_production_enabled and normalize_preset(
            cfg.recovery_preset
        ) != "balanced":
            report.error = "preset_not_balanced_for_production"
            for it in items:
                report.entries.append(
                    WritebackEntry(
                        candidate_id=it.candidate_id,
                        accepted=it.gate_accepted,
                        gate_reason=it.gate_reason,
                        gate_decision=it.gate_decision,
                        skip_reason="preset_not_balanced_for_production",
                        dry_run=not effective_mutate,
                        page=page_from_candidate_id(it.candidate_id, it.page),
                    )
                )
                report.skipped_count += 1
            return report

        # 文档级 false-risk → 禁止自动写回
        if int(false_risk_signals) > 0 and effective_mutate:
            report.error = "document_false_risk"
            for it in items:
                report.entries.append(
                    WritebackEntry(
                        candidate_id=it.candidate_id,
                        accepted=it.gate_accepted,
                        gate_reason=it.gate_reason,
                        gate_decision=it.gate_decision,
                        skip_reason="document_false_risk",
                        dry_run=False,
                        page=page_from_candidate_id(it.candidate_id, it.page),
                    )
                )
                report.skipped_count += 1
            return report

        # 检测请求内重复 candidate_id → fail closed（全部不写）
        seen: set[str] = set()
        dup: set[str] = set()
        for it in items:
            cid = it.candidate_id
            if cid in seen:
                dup.add(cid)
            seen.add(cid)
        if dup:
            report.error = f"duplicate_candidate_id_in_request:{sorted(dup)}"
            for it in items:
                report.entries.append(
                    WritebackEntry(
                        candidate_id=it.candidate_id,
                        original=it.original,
                        replacement=it.recovered_latex,
                        accepted=it.gate_accepted,
                        gate_reason=it.gate_reason,
                        gate_decision=it.gate_decision,
                        writeback_applied=False,
                        dry_run=not effective_mutate,
                        skip_reason="duplicate_candidate_id",
                        page=page_from_candidate_id(it.candidate_id, it.page),
                    )
                )
                report.skipped_count += 1
            return report

        max_doc = int(getattr(cfg, "deepseek_max_writebacks_per_document", 0) or 0)
        max_page = int(getattr(cfg, "deepseek_max_writebacks_per_page", 0) or 0)
        require_hi = bool(getattr(cfg, "deepseek_writeback_require_high_confidence", True))
        doc_planned = 0
        page_planned: dict[int, int] = {}

        # Phase 5D/5H：对齐模糊 或 编号-内容冲突 → 禁止写回（不改编号）
        alignment_conflicts = resolve_multi_formula_alignment_conflicts(items)
        identity_conflicts: set[str] = set()
        try:
            from app.formula.equation_identity_gate import find_identity_content_conflicts

            identity_conflicts = find_identity_content_conflicts(items)
        except Exception:
            identity_conflicts = set()
        block_ids = alignment_conflicts | identity_conflicts

        # 按 start 倒序替换，避免 offset 错位
        planned: list[tuple[RecoveryWritebackItem, FormulaBlockRef, str]] = []
        for it in items:
            page = page_from_candidate_id(it.candidate_id, it.page)
            entry = WritebackEntry(
                candidate_id=it.candidate_id,
                original=it.original,
                replacement=it.recovered_latex,
                accepted=it.gate_accepted,
                gate_reason=it.gate_reason,
                gate_decision=it.gate_decision,
                dry_run=not effective_mutate,
                page=page,
            )
            from app.formula.writeback_context_gate import pages_consistent

            if it.candidate_id in block_ids:
                entry.skip_reason = (
                    "identity_content_conflict"
                    if it.candidate_id in identity_conflicts
                    else "multi_formula_alignment_ambiguous"
                )
                report.entries.append(entry)
                report.skipped_count += 1
                continue
            if it.unresolved:
                entry.skip_reason = "unresolved_formula"
                report.entries.append(entry)
                report.skipped_count += 1
                report.document_status = "formula_incomplete"
                continue
            if it.error:
                entry.skip_reason = f"executor_error:{it.error}"
                report.entries.append(entry)
                report.skipped_count += 1
                continue
            if not it.gate_accepted or not it.would_replace:
                entry.skip_reason = "not_accepted_or_would_replace_false"
                report.entries.append(entry)
                report.skipped_count += 1
                continue
            mode = (it.scheduler_mode or "").lower().strip()
            if mode == "skip":
                entry.skip_reason = "scheduler_skip"
                report.entries.append(entry)
                report.skipped_count += 1
                continue
            if mode and mode not in ALLOWED_WRITEBACK_MODES:
                entry.skip_reason = f"scheduler_mode_not_allowed:{mode}"
                report.entries.append(entry)
                report.skipped_count += 1
                continue
            if require_hi and it.gate_decision != "ACCEPT_HIGH_CONFIDENCE":
                entry.skip_reason = "not_high_confidence"
                report.entries.append(entry)
                report.skipped_count += 1
                continue

            if not pages_consistent(it.candidate_id, page):
                entry.skip_reason = "candidate_page_mismatch"
                report.entries.append(entry)
                report.skipped_count += 1
                continue

            if max_doc > 0 and doc_planned >= max_doc:
                entry.skip_reason = "writeback_budget_exceeded"
                report.entries.append(entry)
                report.skipped_count += 1
                continue
            if page is not None and max_page > 0 and page_planned.get(page, 0) >= max_page:
                entry.skip_reason = "writeback_budget_exceeded"
                report.entries.append(entry)
                report.skipped_count += 1
                continue

            ok, reason, block = self.validate_target(markdown, registry, it.candidate_id)
            if not ok or block is None:
                entry.skip_reason = reason or "validate_failed"
                report.entries.append(entry)
                report.skipped_count += 1
                continue

            tagged = latex_with_optional_tag(
                it.recovered_latex,
                candidate_id=it.candidate_id,
                eq_number=getattr(it, "eq_number", None) or None,
                preserve=bool(getattr(cfg, "preserve_equation_numbers", True)),
            )
            repl = (
                build_display_block(tagged)
                if block.wrap == "display"
                else build_inline_block(it.recovered_latex)
            )
            entry.replacement = repl
            # 轻量结构检查：替换块本身不能破坏 $
            if repl.count("$") % 2 == 1:
                entry.skip_reason = "replacement_unbalanced_dollar"
                report.entries.append(entry)
                report.skipped_count += 1
                continue

            entry.content_hash_before = block.content_hash
            entry.original = block.original_full
            entry.replacement = repl
            planned.append((it, block, repl))
            report.entries.append(entry)
            doc_planned += 1
            if page is not None:
                page_planned[page] = page_planned.get(page, 0) + 1

        if not planned:
            if unresolved_formula_count > 0:
                report.document_status = "formula_incomplete"
            return report

        # dry-run / disabled：只记录将要发生的替换，不改 markdown
        if not effective_mutate:
            for entry in report.entries:
                if entry.skip_reason:
                    continue
                entry.writeback_applied = False
                entry.dry_run = True
                entry.content_hash_after = content_hash(entry.replacement)
            report.applied_count = 0
            report.skipped_count = sum(1 for e in report.entries if e.skip_reason)
            return report

        # 真正写回：倒序 apply → integrity → 失败则整单 rollback
        working = markdown
        by_id = {e.candidate_id: e for e in report.entries}

        for it, block, repl in sorted(planned, key=lambda x: x[1].start, reverse=True):
            cur = working[block.start : block.end]
            if cur != block.original_full:
                by_id[it.candidate_id].skip_reason = "stale_during_apply"
                by_id[it.candidate_id].writeback_applied = False
                report.skipped_count += 1
                continue
            working = working[: block.start] + repl + working[block.end :]
            entry = by_id[it.candidate_id]
            entry.writeback_applied = True
            entry.content_hash_after = content_hash(repl)
            report.applied_count += 1

        dq = _writeback_integrity_check(working, cfg)
        report.release_gate = {
            "publishable": dq.publishable,
            "status": dq.status,
            "reasons": dq.reasons,
            "formula_failures": dq.formula_failures,
        }

        if not dq.publishable:
            working = markdown
            for entry in report.entries:
                if entry.writeback_applied:
                    entry.writeback_applied = False
                    entry.rollback_reason = ",".join(dq.reasons) or "release_gate_failed"
                    report.rolled_back_count += 1
            report.applied_count = 0
            report.markdown_after = markdown
            report.document_status = "formula_incomplete"
            return report

        report.markdown_after = working
        if unresolved_formula_count > 0:
            report.document_status = "formula_incomplete"
        return report


def _writeback_integrity_check(
    markdown: str,
    cfg: FormulaConfig,
    *,
    writeback_skipped: int = 0,
) -> DocumentQuality:
    """写回后轻量检查：不引用旧 recovery_failed 计数。"""
    return check_release(
        markdown,
        report=None,
        cfg=cfg,
        writeback_skipped=writeback_skipped,
    )


def _coerce_item(x: RecoveryWritebackItem | dict[str, Any]) -> RecoveryWritebackItem:
    if isinstance(x, RecoveryWritebackItem):
        if not x.gate_decision:
            x.gate_decision = classify_gate_decision(
                gate_accepted=x.gate_accepted, gate_reason=x.gate_reason
            )
        return x
    ga = bool(x.get("gate_accepted") or x.get("accepted"))
    gr = str(x.get("gate_reason") or "")
    gd = str(x.get("gate_decision") or "") or classify_gate_decision(
        gate_accepted=ga, gate_reason=gr
    )
    page = x.get("page")
    return RecoveryWritebackItem(
        candidate_id=str(x.get("candidate_id") or ""),
        recovered_latex=str(
            x.get("recovered") or x.get("recovered_latex") or x.get("replacement") or ""
        ),
        gate_accepted=ga,
        would_replace=bool(x.get("would_replace", ga)),
        gate_reason=gr,
        original=str(x.get("original") or ""),
        error=str(x.get("error") or ""),
        scheduler_mode=str(x.get("scheduler_mode") or ""),
        page=int(page) if page is not None and str(page).isdigit() else (
            int(page) if isinstance(page, int) else None
        ),
        gate_decision=gd,
        unresolved=bool(x.get("unresolved")),
        eq_number=str(x.get("eq_number") or x.get("equation_number") or ""),
        context_before=str(x.get("context_before") or ""),
        context_after=str(x.get("context_after") or ""),
        bbox=tuple(x["bbox"]) if isinstance(x.get("bbox"), (list, tuple)) and len(x.get("bbox")) == 4 else None,
    )


_DISPLAY = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)


def register_display_formulas_by_order(
    markdown: str,
    candidate_ids: list[str],
) -> FormulaBlockRegistry:
    """按文档中 $$ 出现顺序注册 ID（仅用于已知顺序的 fixture / O-018 试验）。

    仍不做内容搜索替换；只在构建 registry 时扫描一次结构。
    """
    reg = FormulaBlockRegistry()
    matches = list(_DISPLAY.finditer(markdown))
    if len(candidate_ids) != len(matches):
        raise ValueError(
            f"id_count_mismatch:ids={len(candidate_ids)} displays={len(matches)}"
        )
    for cid, m in zip(candidate_ids, matches, strict=True):
        reg.register(
            FormulaBlockRef(
                candidate_id=cid,
                start=m.start(),
                end=m.end(),
                original_inner=m.group(1),
                original_full=m.group(0),
                content_hash=content_hash(m.group(0)),
                wrap="display",
            )
        )
    return reg
