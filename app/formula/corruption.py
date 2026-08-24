"""FormulaCorruptionDetector：专门捕获 OCR/布局灾难（与语法 validator 分离）。"""
from __future__ import annotations

import re

from app.formula.config import FormulaConfig
from app.formula.types import FormulaQuality

_SPACING_CMD = re.compile(
    r"\\(?:quad|qquad|[,;:!]|hspace\s*\{[^}]*\}|vspace\s*\{[^}]*\})"
)
_PROSE_SCRAPS = re.compile(
    r"\\intertext\b|\\code\b|"
    r"\\text\s*\{\s*(?:red|al|bottom|top|weighted|equative|due|graphs|wein|"
    r"s\s*e\s*f\s*t\s*i\s*m\s*e|accorages|this,\s*we|scale\s+of)\s*\}",
    re.I,
)
# Docling/OCR 把散文塞进 \text{...}，闭括号在句末而非 scrap 词后（O-024 Brier）
_TEXT_PROSE_BLOB = re.compile(
    r"\\text\s*\{[^}]*(?:wein|out\s+comes|predicted\s+pro|probabin|between\s+out)",
    re.I,
)
# LaTeX 命令被空格拆开：\Pr e c { R e c }（O-024 F1）
_SPLIT_CMD_SPACES = re.compile(
    r"\\(?:Pr|mathrm|mathbf|mathcal|hat|frac|text)\s+[a-z](?:\s+[a-z]){1,}",
    re.I,
)
# 表格碎片误进 display：F 1 & = ...
_AMP_LEADING_EQ = re.compile(r"^\s*F\s*1\s*&\s*=", re.M | re.I)
# OCR 残留 \) 且无对应 \(
_STRAY_INLINE_CLOSE = re.compile(r"(?<!\\)\\\)")
# aligned 环境以 &= 开头、缺左端标签（O-024 canary F1 写回）
_ALIGNED_NO_LHS = re.compile(r"\\begin\{(?:aligned|align\*?)\}\s*&\s*=", re.I)
_HALLUCINATION = re.compile(
    r"\\Pr\s*_\s*\{\s*\\?\s*\}\s*c\s+a\s+r|"
    r"\bc\s+a\s+r\b|"
    r"(?:\\quad\s*){8,}|"
    r"\\stackrel\b|"
    # Pix2Tex 低清幻觉：ħ、空双花括号、重复 n/n
    r"\\hbar\b|"
    r"\{\s*\{\s*=\s*\}\s*\}|"
    r"(?:\\frac\s*\{\s*n\s*\}\s*\{\s*n\s*\}\s*){2,}|"
    r"(?:\\frac\s*\{\s*\\hbar\s*\}\s*\{\s*\\hbar\s*\})|"
    r"\\text\s*\{\s*tests\s*\}|"
    r"\\text\s*\{\s*esense\s*\}",
    re.I | re.S,
)
_SPACED_LETTERS = re.compile(r"(?:^|[^\\a-z])([a-z])(?:\s+[a-z]){3,}(?![a-z])", re.I)


def strip_spacing(body: str) -> str:
    """剔除 spacing command 与空白后的语义内容。"""
    s = _SPACING_CMD.sub("", body)
    # Docling 常留下 `\\ ` / `\` 伪空格
    s = re.sub(r"\\[ \t]", "", s)
    s = re.sub(r"\\{2,}", "", s)
    s = re.sub(r"\s+", "", s)
    return s


def meaningful_token_count(body: str) -> int:
    cleaned = _SPACING_CMD.sub(" ", body)
    tokens = re.findall(r"\\[A-Za-z]+|[A-Za-z0-9]+", cleaned)
    # 纯 spacing 命令不算
    skip = {"quad", "qquad", "hspace", "vspace"}
    return sum(1 for t in tokens if t.lstrip("\\").lower() not in skip)


def assess_corruption(body: str, cfg: FormulaConfig | None = None) -> FormulaQuality:
    """corruption_score 高 → CORRUPTED；语法合法也可失真。"""
    cfg = cfg or FormulaConfig()
    reasons: list[str] = []
    corruption = 0.0
    raw = body.strip()
    raw_len = max(1, len(raw))
    semantic = strip_spacing(raw)
    semantic_len = len(semantic)
    tokens = meaningful_token_count(raw)
    quads = len(re.findall(r"\\quad\b", raw))

    if raw_len > cfg.corruption_len_threshold and tokens < cfg.corruption_min_tokens:
        corruption = max(corruption, 1.0)
        reasons.append("long_low_information")

    if quads >= cfg.max_quad_run:
        corruption = max(corruption, 0.8)
        reasons.append("quad_run")

    token_denom = max(1, tokens + quads)
    if quads / token_denom > 0.15 and quads >= 4:
        corruption = max(corruption, 0.8)
        reasons.append("quad_ratio")

    if semantic_len / raw_len < cfg.corruption_semantic_ratio and raw_len >= 40:
        corruption = max(corruption, 1.0)
        reasons.append("spacing_only_ratio")

    # 清洗后几乎只剩单个符号（Recall → Γ）
    if raw_len >= 80 and semantic_len <= 12 and tokens <= 2:
        corruption = max(corruption, 1.0)
        reasons.append("degenerate_after_strip")

    if _PROSE_SCRAPS.search(raw):
        corruption = max(corruption, 0.9)
        reasons.append("layout_prose_scrap")

    if _TEXT_PROSE_BLOB.search(raw):
        corruption = max(corruption, 0.9)
        reasons.append("prose_in_math_text")

    if _SPLIT_CMD_SPACES.search(raw):
        corruption = max(corruption, 0.88)
        reasons.append("split_latex_command")

    if _AMP_LEADING_EQ.search(raw):
        corruption = max(corruption, 0.85)
        reasons.append("amp_table_fragment")

    if _STRAY_INLINE_CLOSE.search(raw) and r"\(" not in raw:
        corruption = max(corruption, 0.82)
        reasons.append("stray_inline_close")

    if _ALIGNED_NO_LHS.search(raw):
        corruption = max(corruption, 0.85)
        reasons.append("aligned_missing_lhs")

    if _SPACED_LETTERS.search(raw):
        corruption = max(corruption, 0.85)
        reasons.append("spaced_letter_garbage")

    if _HALLUCINATION.search(raw):
        corruption = max(corruption, 0.95)
        reasons.append("ocr_hallucination")

    # 几乎只有空 {} / = / - 碎片
    if re.fullmatch(
        r"(?:\{\s*\{\s*[=+\-]?\s*\}\s*\}|\\\\|\s|\\,|\\quad)*",
        raw.replace("\n", " "),
    ):
        corruption = max(corruption, 1.0)
        reasons.append("empty_brace_garbage")

    # 重复同一 frac 超过 2 次
    if len(re.findall(r"\\frac\s*\{\s*n\s*\}\s*\{\s*n\s*\}", raw, flags=re.I)) >= 2:
        corruption = max(corruption, 1.0)
        reasons.append("repeated_nn_frac")

    if re.fullmatch(r"\\Gamma(?:\s|\\quad|\\,)*", raw):
        corruption = max(corruption, 1.0)
        reasons.append("degenerate_gamma")

    # 语法维：粗略括号
    syntax = 1.0
    for a, b in (("{", "}"), ("[", "]"), ("(", ")")):
        tmp = raw.replace("\\" + a, "").replace("\\" + b, "")
        if tmp.count(a) != tmp.count(b):
            syntax = min(syntax, 0.4)
            reasons.append(f"unbalanced_{a}{b}")

    begins = re.findall(r"\\begin\{([^}]+)\}", raw)
    ends = re.findall(r"\\end\{([^}]+)\}", raw)
    if sorted(begins) != sorted(ends):
        syntax = min(syntax, 0.3)
        reasons.append("env_mismatch")

    semantic_score = 1.0  # 上下文 mismatch 由 pipeline 另填
    corrupted = corruption >= 0.75
    # 语法极差也当不可用
    invalid = corrupted or syntax < 0.5
    return FormulaQuality(
        syntax_score=syntax,
        corruption_score=corruption,
        semantic_score=semantic_score,
        valid=not invalid,
        recoverable=corrupted or syntax < 0.5,
        reasons=reasons,
    )


def context_mismatch(body: str, before: str, after: str) -> list[str]:
    """轻量上下文不一致；禁止据此猜写公式，只触发 recovery。

    只用公式前文中的**引导句**；忽略前文里已有的 $$ 公式块，避免相邻公式误杀。
    """
    del after
    reasons: list[str] = []
    # 去掉前文里的公式，只留散文引导
    prose = re.sub(r"\$\$[\s\S]*?\$\$", " ", before)
    prose = re.sub(r"(?<!\$)\$(?!\$)(?:\\.|[^$\\])+?\$(?!\$)", " ", prose)
    ctx = prose.lower()
    low = body.lower()
    compact = strip_spacing(body)
    intro = bool(
        re.search(r"\beq\.?\b|using|defined as|given by|calculated|follows|score", ctx)
    )
    metric_ctx = bool(
        re.search(r"\bmse\b|bias.?variance|mean squared|expected mse", ctx)
    )

    if intro and "recall" in ctx and not any(
        x in low for x in ("recall", "tp", "fn", "frac", "=")
    ):
        if len(compact) < 30:
            reasons.append("context_mismatch_recall")

    if intro and re.search(r"\bf1\b|f1-score|f1 score|f1@0", ctx) and (
        "c a r" in low
        or re.search(r"\\Pr\s+e\s+c|F\s*1\s*&", body, re.I)
        or (len(compact) < 20 and "f1" not in low)
    ):
        reasons.append("context_mismatch_f1")

    if intro and re.search(
        r"\bbrier\s+score\b|mean squared error between outcomes", ctx
    ):
        if re.search(r"wein|probabin|out\s+comes", low):
            reasons.append("context_mismatch_brier")
        elif re.search(r"\\text\s*\{[^}]{15,}", body) and re.search(
            r"\\sum|brier", low
        ):
            reasons.append("context_mismatch_brier")

    if intro and re.search(r"\btpr\b|true positive rate", ctx) and "tpr" not in low:
        if len(compact) < 40 and "tp" not in low:
            reasons.append("context_mismatch_tpr")

    if intro and re.search(r"\bfpr\b|false positive rate", ctx) and "fpr" not in low:
        if len(compact) < 40 and "fp" not in low:
            reasons.append("context_mismatch_fpr")

    if (intro or metric_ctx) and re.search(
        r"\bmse\b|bias.?variance|expected mse|mean squared", ctx
    ):
        has_error_term = bool(
            re.search(r"mse|bias|variance|varepsilon|epsilon", low)
        )
        looks_wrong = bool(re.search(r"\\omega\b|\bomega\b|\\hbar\b", low))
        if looks_wrong and not has_error_term:
            reasons.append("semantically_suspicious")

    return reasons
