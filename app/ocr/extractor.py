"""DeepSeek 文档 OCR → EquationBlock 解析与选择（Phase 3A）。

硬规则：
- 只能选择 OCR 已输出的公式片段
- 禁止根据上下文发明 / 补写标准公式
- 不返回整段 Markdown / 散文段落
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from app.formula.benchmark import compact_latex, gold_match
from app.formula.types import FormulaCandidate

# DeepSeek grounding 噪声
_GROUNDING = re.compile(
    r"<\|ref\|>.*?<\|/ref\|>|<\|det\|>.*?<\|/det\|>|<\|[^|>]+?\|>",
    re.I | re.S,
)
_END_TOKEN = re.compile(r"<[^>]*end[^>]*>", re.I)

# \[ ... \] / $$ ... $$ / \( ... \) / $ ... $
_DISPLAY = re.compile(r"\\\[([\s\S]+?)\\\]|\$\$([\s\S]+?)\$\$")
_INLINE = re.compile(r"\\\(([\s\S]+?)\\\)|(?<!\$)\$(?!\$)([^\$\n]+?)\$(?!\$)")
_EQ_NUM = re.compile(r"[（(]\s*(\d{1,3})\s*[）)]")
_EQ_MENTION = re.compile(
    r"(?:Eq(?:uation)?\.?\s*[（(]\s*(\d{1,3})\s*[）)]|公式\s*[（(]\s*(\d{1,3})\s*[）)])",
    re.I,
)

_LABEL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("recall", re.compile(r"\brecall\b", re.I)),
    ("f1", re.compile(r"\bf1(?:\s*-?\s*score)?\b", re.I)),
    ("tpr", re.compile(r"\btpr\b|\btrue\s+positive\s+rate\b", re.I)),
    ("fpr", re.compile(r"\bfpr\b|\bfalse\s+positive\s+rate\b", re.I)),
    ("precision", re.compile(r"\bprecision\b", re.I)),
    ("mse", re.compile(r"\bmse\b|\bmean\s+squared\s+error\b|\bbias\b", re.I)),
    ("accuracy", re.compile(r"\baccuracy\b", re.I)),
]

# 标签 → 常见目标编号（仅用于选择已有 block，不生成公式）
_CONTEXT_LABEL_HINTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\brecall\b", re.I), "recall"),
    (re.compile(r"\bf1\b", re.I), "f1"),
    (re.compile(r"\btpr\b|true\s+positive\s+rate", re.I), "tpr"),
    (re.compile(r"\bfpr\b|false\s+positive\s+rate", re.I), "fpr"),
    (re.compile(r"\bmse\b|mean\s+squared|bias.?variance", re.I), "mse"),
    (re.compile(r"\bprecision\b", re.I), "precision"),
]


@dataclass
class EquationBlock:
    latex_or_text: str
    equation_number: str | None = None
    order: int = 0
    source_span: tuple[int, int] = (0, 0)
    nearby_label: str = ""
    source: str = "math"  # math | labeled_line

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["source_span"] = list(self.source_span)
        return d


@dataclass
class ExtractResult:
    block: EquationBlock | None
    method: str = ""  # exact_number | number_nearby | label_match | order_fallback | none
    failure_reason: str = ""
    blocks: list[EquationBlock] = field(default_factory=list)

    @property
    def latex(self) -> str:
        return (self.block.latex_or_text if self.block else "") or ""


def ocr_raw_is_prose_ref(raw: str) -> bool:
    """DeepSeek 返回 text grounding 而非 equation。"""
    t = (raw or "").lower()
    return "<|ref|>text<|/ref|>" in t or "<|ref|>text<|" in t


def strip_ocr_noise(text: str) -> str:
    s = text or ""
    s = _GROUNDING.sub("", s)
    s = _END_TOKEN.sub("", s)
    s = s.replace("\u200b", "")
    return s


def _clean_math(body: str) -> str:
    s = (body or "").strip()
    s = s.strip("$").strip()
    s = re.sub(r"^\\\(|\\\)$", "", s).strip()
    s = re.sub(r"^\\\[|\\\]$", "", s).strip()
    # 去掉尾部 \quad (n) / (n)（编号已单独记录）
    s = re.sub(r"(?:\\quad|\\qquad|\s)*[（(]\s*\d{1,3}\s*[）)]\s*$", "", s).strip()
    s = re.sub(r"(?:\\quad|\\qquad)\s*$", "", s).strip()
    return s


_CITATION_SUPER = re.compile(r"\^\{[\d,\s]+\}|\^[0-9]+")
_REAL_MATH = re.compile(
    r"=|\\frac|\\sum|\\int|\\left|\\right|\\begin|\\mathrm|\\mathbf|"
    r"\\min|\\max|\\hat|\\bar|\\times|\\cdot|\\operatorname"
)


def _looks_like_formula(s: str) -> bool:
    t = (s or "").strip()
    if len(t) < 3:
        return False
    # 「... Eq. (n)」引用句不是公式
    if re.search(r"\bEq(?:uation)?\.?\s*$", t, re.I):
        return False
    if re.search(r"\bEq(?:uation)?\.?\s*$", t.rstrip(), re.I):
        return False
    if re.search(r"(?:calculated|using|from|see|as in)\s+Eq\b", t, re.I):
        return False
    # 仅引用上标 ^{12,23} 不是公式
    core = _CITATION_SUPER.sub("", t).strip(" ,.;:")
    if not core and not _REAL_MATH.search(t):
        return False
    words4 = re.findall(r"[A-Za-z]{4,}", t)
    if len(words4) >= 3 and t.count("=") == 0 and not _REAL_MATH.search(t):
        return False
    words = re.findall(r"[A-Za-z]{3,}", t)
    mathish = bool(
        re.search(
            r"[=\\^_{}]|\\frac|\\times|\\left|\\right|\\mathrm|\\mathbf|\\begin|"
            r"Bias|\\varepsilon|(?<![A-Za-z])(?:TP|FP|FN|TN|TPR|FPR|MSE)(?![A-Za-z])",
            t,
        )
    )
    if not mathish:
        return False
    if len(words) >= 14 and t.count("=") == 0 and "\\frac" not in t:
        return False
    return True


def _formula_quality(s: str) -> tuple[int, int]:
    """越大越好；用于同号多块时择优。"""
    t = s or ""
    score = 0
    if "=" in t:
        score += 3
    if "\\frac" in t:
        score += 4
    if re.search(r"\\mathrm|\\mathbf|\\left|\\begin", t):
        score += 2
    if re.search(r"(?<![A-Za-z])(?:TP|FP|FN|TN|TPR|FPR|Bias)(?![A-Za-z])", t):
        score += 2
    if re.search(r"\bEq(?:uation)?\b", t, re.I):
        score -= 5
    words = len(re.findall(r"[A-Za-z]{3,}", t))
    if words > 12:
        score -= 3
    return (score, -len(t))


def _split_math_pieces(body: str, nums: list[str]) -> list[tuple[str, str | None]]:
    """多公式挤在同一 aligned / 多编号时拆成多块。"""
    if not nums:
        return [(body, None)]
    if len(nums) == 1:
        return [(body, nums[0])]
    # aligned / gather 按 \\ 拆行，与编号按序对应
    inner = body
    m = re.search(
        r"\\begin\{(?:aligned|align\*?|gather\*?|eqnarray\*?)\}([\s\S]*?)\\end\{(?:aligned|align\*?|gather\*?|eqnarray\*?)\}",
        body,
    )
    if m:
        inner = m.group(1)
    rows = [r.strip() for r in re.split(r"\\\\", inner) if r.strip()]
    # 去掉行内残留编号
    cleaned_rows = [_clean_math(r) for r in rows]
    cleaned_rows = [r for r in cleaned_rows if _looks_like_formula(r)]
    out: list[tuple[str, str | None]] = []
    if cleaned_rows and len(cleaned_rows) == len(nums):
        for row, num in zip(cleaned_rows, nums):
            out.append((row, num))
        return out
    # 无法对齐时：整块复制给每个编号（select 时靠 label 再筛）
    for num in nums:
        out.append((body, num))
    return out


def _detect_label(window: str) -> str:
    for name, pat in _LABEL_PATTERNS:
        if pat.search(window or ""):
            return name
    return ""


def parse_equation_blocks(markdown: str) -> list[EquationBlock]:
    """把 DeepSeek Markdown 解析成 EquationBlock[]（不选目标）。"""
    text = strip_ocr_noise(markdown)
    if not text.strip():
        return []

    blocks: list[EquationBlock] = []
    occupied: list[tuple[int, int, str | None, str]] = []

    def overlaps(a: int, b: int, num: str | None, latex: str) -> bool:
        key = _clean_math(latex)
        for x, y, n, prev in occupied:
            if not (a < y and b > x):
                continue
            # 同一 span 允许不同编号（aligned 多式）
            if n is not None and num is not None and n != num:
                continue
            if prev == key:
                return True
            if n == num:
                return True
        return False

    def add(latex: str, start: int, end: int, num: str | None, source: str) -> None:
        latex = _clean_math(latex)
        if not _looks_like_formula(latex):
            return
        if overlaps(start, end, num, latex):
            return
        left = text[max(0, start - 120) : start]
        label = _detect_label(left) or _detect_label(latex[:80])
        blocks.append(
            EquationBlock(
                latex_or_text=latex,
                equation_number=num,
                order=len(blocks),
                source_span=(start, end),
                nearby_label=label,
                source=source,
            )
        )
        occupied.append((start, end, num, latex))

    # 1) display math：编号常在块内 \quad (n)；多号 aligned 按行拆开
    for m in _DISPLAY.finditer(text):
        body = next(g for g in m.groups() if g is not None)
        nums = _EQ_NUM.findall(body)
        end = m.end()
        if not nums:
            tail = text[m.end() : m.end() + 40]
            tm = re.match(r"\s*[（(]\s*(\d{1,3})\s*[）)]", tail)
            if tm:
                nums = [tm.group(1)]
                end = m.end() + tm.end()
        pieces = _split_math_pieces(body, nums)
        for latex_piece, num in pieces:
            add(latex_piece, m.start(), end, num, "math")

    # 2) inline math + 同行尾编号：Recall = \(...\) (4)
    for m in _INLINE.finditer(text):
        body = next(g for g in m.groups() if g is not None)
        # 向左取同行前缀（标签）
        line_start = text.rfind("\n", 0, m.start()) + 1
        prefix = text[line_start : m.start()]
        tail = text[m.end() : text.find("\n", m.end()) if text.find("\n", m.end()) >= 0 else m.end() + 40]
        tm = re.match(r"\s*[（(]\s*(\d{1,3})\s*[）)]", tail)
        num = tm.group(1) if tm else None
        if num is None:
            nums = _EQ_NUM.findall(body)
            num = nums[-1] if nums else None
        latex = (prefix + body).strip() if prefix.strip() else body
        end = m.end() + (tm.end() if tm else 0)
        add(latex, line_start if prefix.strip() else m.start(), end, num, "math")

    # 3) 单行「... (n)」且含公式符号（兜底）
    for i, line in enumerate(text.splitlines()):
        raw = line.strip()
        if not raw:
            continue
        m = re.match(r"^(.+?)\s*[（(]\s*(\d{1,3})\s*[）)]\s*:?\s*$", raw)
        if not m:
            continue
        body, num = m.group(1), m.group(2)
        if not _looks_like_formula(body):
            continue
        # 定位 span
        pos = text.find(line)
        if pos < 0:
            pos = 0
        add(body, pos, pos + len(line), num, "labeled_line")

    blocks.sort(key=lambda b: b.source_span[0])
    for i, b in enumerate(blocks):
        b.order = i
    return blocks


class EquationExtractor:
    """按优先级从 EquationBlock[] 中选择目标式。"""

    def parse(self, markdown: str) -> list[EquationBlock]:
        return parse_equation_blocks(markdown)

    def select(
        self,
        blocks: list[EquationBlock],
        *,
        eq_number: str,
        context_before: str = "",
        context_after: str = "",
        markdown: str = "",
    ) -> ExtractResult:
        n = str(eq_number or "").strip()
        if not blocks:
            return ExtractResult(
                block=None,
                method="none",
                failure_reason="no_equation_blocks",
                blocks=[],
            )

        # a) exact equation number
        if n:
            exact = [b for b in blocks if b.equation_number == n]
            if exact:
                exact.sort(key=lambda b: _formula_quality(b.latex_or_text), reverse=True)
                best = exact[0]
                if _formula_quality(best.latex_or_text)[0] < 0:
                    pass  # 继续后续策略
                else:
                    return ExtractResult(block=best, method="exact_number", blocks=blocks)

        # b) equation number nearby — OCR 文中有 Eq. (n) 提及，取其后方最近 block
        if n and markdown:
            text = strip_ocr_noise(markdown)
            for m in _EQ_MENTION.finditer(text):
                mention_n = m.group(1) or m.group(2)
                if mention_n != n:
                    continue
                after = [b for b in blocks if b.source_span[0] >= m.start()]
                if after:
                    return ExtractResult(
                        block=after[0], method="number_nearby", blocks=blocks
                    )

        # c) label match（仅选择已有 block）
        ctx = f"{context_before or ''} {context_after or ''}"
        wanted_labels: list[str] = []
        for pat, lab in _CONTEXT_LABEL_HINTS:
            if pat.search(ctx):
                wanted_labels.append(lab)
        for lab in wanted_labels:
            hits = [b for b in blocks if b.nearby_label == lab]
            if not hits:
                hits = [b for b in blocks if lab.lower() in b.latex_or_text.lower()]
            if hits:
                # 若目标编号存在于别的 block，不要用错误标签抢号
                return ExtractResult(block=hits[0], method="label_match", blocks=blocks)

        # d) order fallback — 仅当只有一个公式块时
        if len(blocks) == 1:
            return ExtractResult(
                block=blocks[0], method="order_fallback", blocks=blocks
            )

        return ExtractResult(
            block=None,
            method="none",
            failure_reason="no_matching_equation_block",
            blocks=blocks,
        )

    def extract(
        self,
        markdown: str,
        *,
        eq_number: str,
        context_before: str = "",
        context_after: str = "",
    ) -> ExtractResult:
        blocks = self.parse(markdown)
        return self.select(
            blocks,
            eq_number=eq_number,
            context_before=context_before,
            context_after=context_after,
            markdown=markdown,
        )

    def extract_candidate(
        self,
        markdown: str,
        *,
        eq_number: str,
        context_before: str = "",
        context_after: str = "",
    ) -> FormulaCandidate | None:
        """兼容旧接口：返回 FormulaCandidate 或 None。"""
        res = self.extract(
            markdown,
            eq_number=eq_number,
            context_before=context_before,
            context_after=context_after,
        )
        if not res.block:
            return None
        return FormulaCandidate(
            text=res.block.latex_or_text,
            raw_text=res.block.latex_or_text,
            context_before=context_before or "",
            issues=[
                f"extract:{res.method}",
                f"eq:{res.block.equation_number or eq_number}",
                f"label:{res.block.nearby_label or '-'}",
            ],
        )


# 兼容旧名
class FormulaFromDocumentOCRExtractor(EquationExtractor):
    def extract(  # type: ignore[override]
        self,
        markdown: str,
        *,
        eq_number: str,
        context_before: str = "",
        context_after: str = "",
    ) -> FormulaCandidate | None:
        res = EquationExtractor.extract(
            self,
            markdown,
            eq_number=eq_number,
            context_before=context_before,
            context_after=context_after,
        )
        if not res.block:
            return None
        return FormulaCandidate(
            text=res.block.latex_or_text,
            raw_text=res.block.latex_or_text,
            context_before=context_before or "",
            issues=[
                f"extract:{res.method}",
                f"eq:{res.block.equation_number or eq_number}",
            ],
        )


def raw_ocr_contains_gold(raw: str, gold: str) -> str:
    """OCR 原文是否已含 gold（忽略抽取）。yes|no|—"""
    if not (gold or "").strip():
        return "—"
    if not (raw or "").strip():
        return "no"
    # 先整段宽松匹配
    if gold_match(raw, gold) == "yes":
        return "yes"
    g = compact_latex(gold)
    r = compact_latex(raw)
    if not g:
        return "—"
    # 核心 token：去公共包装后的连续片段
    core = re.sub(r"^(recall|f1|tpr|fpr|precision|accuracy)=", "", g, flags=re.I)
    if len(core) >= 6 and core in r:
        return "yes"
    # 关键符号组合
    keys = [k for k in ("TP+FN", "TP+FP", "FP+TN", "Bias", r"\frac{TP}", "Precision") if k]
    hit = 0
    for k in keys:
        ck = compact_latex(k)
        if ck and ck in r and ck in g:
            hit += 1
    if hit >= 2:
        return "yes"
    return "no"


def extractor_selected_gold(extracted: str, gold: str) -> str:
    return gold_match(extracted, gold)
