"""ContextTokenConsistency：只用上下文否决明显无关 OCR，禁止据此生成/补写公式。"""
from __future__ import annotations

import re

# 只比较这些“有区分度”的数学词元；不把所有字母都当证据
METRIC_TOKENS = {
    "tp",
    "tn",
    "fp",
    "fn",
    "bias",
    "mse",
    "rmse",
    "mae",
    "y",
    "f",
    "epsilon",
    "varepsilon",
    "sigma",
    "recall",
    "precision",
    "accuracy",
    "f1",
    "tpr",
    "fpr",
    "auc",
    "variance",
    "var",
    "macro",
    "weighted",
    "confusion",
    "roc",
    "auc",
    "markov",
    "laplacian",
    "stability",
    "partition",
}

# OCR 幻觉里常见、与分类/误差指标无关的符号
HALLUCINATION_TOKENS = {
    "omega",
    "hbar",
    "mu",
    "nd",
}

_CMD = re.compile(r"\\([A-Za-z]+)")
_WORD = re.compile(
    r"\b(TP|TN|FP|FN|MSE|RMSE|MAE|TPR|FPR|AUC|F1|Bias|Recall|Precision|"
    r"Accuracy|Variance|Var|epsilon|varepsilon)\b",
    re.I,
)
_GREEK = {
    "ω": "omega",
    "μ": "mu",
    "ε": "epsilon",
    "σ": "sigma",
    "γ": "gamma",
    "ħ": "hbar",
}


def extract_math_tokens(text: str) -> set[str]:
    """从上下文或 LaTeX 抽出可比较词元。"""
    if not text:
        return set()
    out: set[str] = set()
    for m in _CMD.finditer(text):
        out.add(m.group(1).lower())
    for m in _WORD.finditer(text):
        tok = m.group(1).lower()
        if tok == "f1":
            out.add("f1")
        else:
            out.add(tok)
    low = text.lower()
    for needle, canon in (
        ("true positive", "tp"),
        ("false positive", "fp"),
        ("true negative", "tn"),
        ("false negative", "fn"),
        ("f1-score", "f1"),
        ("f1 score", "f1"),
        ("harmonic", "f1"),
        ("expected mse", "mse"),
        ("mean squared", "mse"),
        ("bias-variance", "bias"),
        ("bias–variance", "bias"),
        ("macro-average", "macro"),
        ("weighted-average", "weighted"),
        ("confusion matrix", "confusion"),
        ("roc-auc", "roc"),
        ("one-vs-rest", "roc"),
    ):
        if needle in low:
            out.add(canon)
    for word in ("macro", "weighted", "confusion", "markov", "laplacian", "stability"):
        if re.search(rf"\b{word}\b", low):
            out.add(word)
    if re.search(r"\broc\b", low) or "roc-auc" in low:
        out.add("roc")
    if re.search(r"\bauc\b", low):
        out.add("auc")
    for ch, name in _GREEK.items():
        if ch in text:
            out.add(name)
    if re.search(r"F_\{?\s*1\s*\}?|F1", text, re.I):
        out.add("f1")
    # 裸 TP/FN 等（无 word boundary 的 LaTeX）
    compact = re.sub(r"[\\{}\s_^]+", "", text)
    for tok in ("TP", "TN", "FP", "FN", "MSE", "TPR", "FPR"):
        if tok in compact or tok.lower() in compact.lower():
            out.add(tok.lower())
    return out


def interesting(tokens: set[str]) -> set[str]:
    return {t for t in tokens if t in METRIC_TOKENS}


# 上下文说 MSE、OCR 给出 Bias–Var–ε 分解：应视为同族，避免 false reject
_MSE_FAMILY = frozenset({"mse", "bias", "var", "variance", "y", "f", "epsilon", "varepsilon"})
_RECALL_FAMILY = frozenset({"recall", "tp", "tn", "fp", "fn", "tpr", "fpr", "precision", "f1", "accuracy"})
_CLASSIFICATION_FAMILY = _RECALL_FAMILY | frozenset(
    {"macro", "weighted", "confusion", "matrix", "roc", "auc"}
)
_MARKOV_FAMILY = frozenset(
    {"markov", "laplacian", "stability", "partition", "transition", "random", "walk"}
)
_MARKOV_SYMBOLS = frozenset({"r", "h", "t", "pi", "l", "v", "q", "n", "omega"})

_GREEK_CMDS = frozenset(
    {
        "pi",
        "alpha",
        "beta",
        "gamma",
        "sigma",
        "omega",
        "varepsilon",
        "epsilon",
        "theta",
        "lambda",
        "mu",
        "hbar",
    }
)


def extract_symbol_signature(text: str) -> set[str]:
    """从上下文 / LaTeX 抽变量符号签名（k3：补 METRIC_TOKENS 覆盖不到的 MS/LEAP 式）。"""
    if not text:
        return set()
    out: set[str] = set()
    for m in _CMD.finditer(text):
        cmd = m.group(1)
        low = cmd.lower()
        if low in _GREEK_CMDS:
            out.add(low)
        if len(cmd) == 1 and cmd.isalpha():
            out.add(low)
    # 行内 / display 单字母变量：R(t;H), H_{lc}, \mathcal{F}
    for m in re.finditer(r"\\mathcal\s*\{\s*([A-Za-z])\s*\}", text):
        out.add(m.group(1).lower())
    for m in re.finditer(r"(?<![A-Za-z])([A-Za-z])\s*[\(\[,;:=]", text):
        out.add(m.group(1).lower())
    for m in re.finditer(r"_\{\s*([A-Za-z]{1,3})\s*\}", text):
        out.add(m.group(1).lower())
    for m in re.finditer(r"\b([A-Za-z])\s*_\{", text):
        out.add(m.group(1).lower())
    low = text.lower()
    for word, sym in (
        ("autocovariance", "r"),
        ("partition", "h"),
        ("markov", "r"),
        ("stationary", "pi"),
        ("laplacian", "l"),
        ("random walk", "q"),
        ("cutoff", "t"),
        ("records", "r"),
        ("truncat", "f"),
    ):
        if word in low:
            out.add(sym)
    return {s for s in out if s and len(s) <= 4}


def symbol_overlap_ratio(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))


_MAX_RE = re.compile(
    r"\\max(?:\b|_)|\bmaxim(?:is|um|ize|ise)\b|\bmax\b|arg\s*\\?max|argmax|r\s*\^\s*\{?\s*\*",
    re.I,
)
_MIN_RE = re.compile(
    r"\\min(?:\b|_)|\bminim(?:is|um|ize|ise)\b|\bmin\b|arg\s*\\?min|argmin",
    re.I,
)


def direction_flags(text: str) -> tuple[bool, bool]:
    t = (text or "").lower()
    return bool(_MAX_RE.search(t)), bool(_MIN_RE.search(t))


def operator_direction_conflict(
    context_before: str,
    ocr_latex: str,
    *,
    original_latex: str = "",
) -> tuple[bool, list[str]]:
    """检测 max/min 方向冲突。原文损坏式优先于正文（避免相邻式子 max/min 污染）。"""
    reasons: list[str] = []
    ocr = (ocr_latex or "").lower()
    if not ocr.strip():
        return False, reasons

    def _flags(text: str) -> tuple[bool, bool]:
        return direction_flags(text)

    ocr_max, ocr_min = _flags(ocr)
    orig_max, orig_min = _flags(original_latex)
    if orig_max or orig_min:
        if orig_max and ocr_min and not ocr_max:
            reasons.append("operator_direction_conflict")
            return True, reasons
        if orig_min and ocr_max and not ocr_min:
            reasons.append("operator_direction_conflict")
            return True, reasons
        return False, reasons

    ctx_max, ctx_min = _flags(context_before)
    if ctx_max and ocr_min and not ocr_max:
        reasons.append("operator_direction_conflict")
        return True, reasons
    if ctx_min and ocr_max and not ocr_min:
        reasons.append("operator_direction_conflict")
        return True, reasons
    return False, reasons


def sanitize_recovery_context(text: str) -> str:
    """Gate 用上下文：去掉 formula-not-decoded 占位，避免假冲突。"""
    from app.formula.equation_identity import NOT_DECODED_RE

    t = NOT_DECODED_RE.sub(" ", text or "")
    return re.sub(r"\s+", " ", t).strip()


def _related_families(a: set[str], b: set[str]) -> bool:
    """两边词元无交集时，是否仍属同一指标族（仅否决用，不生成公式）。"""
    if (a & _MSE_FAMILY) and (b & _MSE_FAMILY):
        return True
    if (a & _RECALL_FAMILY) and (b & _RECALL_FAMILY):
        return True
    if (a & _CLASSIFICATION_FAMILY) and (b & _CLASSIFICATION_FAMILY):
        return True
    if (a & _MARKOV_FAMILY) and (b & _MARKOV_FAMILY):
        return True
    return False


def token_consistency(
    source_text: str,
    ocr_latex: str,
) -> tuple[float, list[str]]:
    """返回 (overlap_ratio, reasons)。

    Phase 6C：
    - ocr_context_conflict = 强冲突（两边都有指标词且无交集、非同族）→ hard veto
    - ocr_context_insufficient = 上下文无足够支持、但也非强冲突 → 可被其他证据接受
    """
    reasons: list[str] = []
    src = extract_math_tokens(source_text)
    ocr = extract_math_tokens(ocr_latex)
    src_i = interesting(src)
    ocr_i = interesting(ocr)
    sym_src = extract_symbol_signature(source_text)
    sym_ocr = extract_symbol_signature(ocr_latex)
    sym_r = symbol_overlap_ratio(sym_src, sym_ocr)
    ocr_noise = {t for t in ocr if t in HALLUCINATION_TOKENS}

    if src_i and ocr_i:
        overlap = src_i & ocr_i
        denom = max(1, len(src_i | ocr_i))
        ratio = len(overlap) / denom
        if not overlap:
            if _related_families(src_i, ocr_i):
                return 0.25, reasons
            if sym_r >= 0.2:
                reasons.append("symbol_signature_support")
                return max(0.3, sym_r), reasons
            reasons.append("ocr_context_conflict")
            return 0.0, reasons
        return ratio, reasons

    if src_i and not ocr_i:
        low = (ocr_latex or "").lower()
        if "bias" in low or "var" in low or "varepsilon" in low or "epsilon" in low:
            if src_i & _MSE_FAMILY:
                return 0.25, reasons
        if sym_r >= 0.15:
            reasons.append("symbol_signature_support")
            return max(0.35, sym_r), reasons
        if (src_i & _MARKOV_FAMILY) and (sym_ocr & _MARKOV_SYMBOLS):
            reasons.append("symbol_signature_support")
            return 0.32, reasons
        if ocr_noise:
            reasons.append("ocr_context_conflict")
            return 0.0, reasons
        if (ocr_latex or "").strip():
            if sym_ocr and not sym_src:
                reasons.append("ocr_context_insufficient")
                return 0.35, reasons
            if sym_r < 0.1 and src_i & _CLASSIFICATION_FAMILY:
                reasons.append("ocr_context_conflict")
                return 0.0, reasons
            if sym_r >= 0.2:
                reasons.append("symbol_signature_support")
                return max(0.3, sym_r), reasons
            reasons.append("ocr_context_conflict")
            return 0.0, reasons
        reasons.append("ocr_context_insufficient")
        return 0.35, reasons

    if not src_i and ocr_i:
        if sym_r >= 0.2:
            reasons.append("symbol_signature_support")
            return max(0.4, sym_r), reasons
        reasons.append("ocr_context_insufficient")
        return 0.4, reasons

    if sym_r >= 0.2:
        reasons.append("symbol_signature_support")
        return max(0.4, sym_r), reasons

    return 1.0, reasons
