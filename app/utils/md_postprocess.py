"""Markdown 后处理：补行内公式 LaTeX、尽量恢复 PDF 粗体。

Docling 公式 enrichment 只处理版面标成 FORMULA 的行间公式；
正文里的 δ、∈、T i 等通常是 Unicode/纯文本。PDF 管线也不把
font bold 写进 TextItem.formatting，导致 **粗体** 丢失。
"""
from __future__ import annotations

import re
from pathlib import Path

_GREEK = {
    "α": r"\alpha",
    "β": r"\beta",
    "γ": r"\gamma",
    "δ": r"\delta",
    "ε": r"\varepsilon",
    "ϵ": r"\epsilon",
    "ζ": r"\zeta",
    "η": r"\eta",
    "θ": r"\theta",
    "ϑ": r"\vartheta",
    "ι": r"\iota",
    "κ": r"\kappa",
    "λ": r"\lambda",
    "μ": r"\mu",
    "ν": r"\nu",
    "ξ": r"\xi",
    "π": r"\pi",
    "ρ": r"\rho",
    "σ": r"\sigma",
    "ς": r"\varsigma",
    "τ": r"\tau",
    "υ": r"\upsilon",
    "φ": r"\varphi",
    "ϕ": r"\phi",
    "χ": r"\chi",
    "ψ": r"\psi",
    "ω": r"\omega",
    "Γ": r"\Gamma",
    "Δ": r"\Delta",
    "Θ": r"\Theta",
    "Λ": r"\Lambda",
    "Ξ": r"\Xi",
    "Π": r"\Pi",
    "Σ": r"\Sigma",
    "Φ": r"\Phi",
    "Ψ": r"\Psi",
    "Ω": r"\Omega",
}

_OPS = {
    "∈": r"\in",
    "∉": r"\notin",
    "∋": r"\ni",
    "≤": r"\le",
    "≥": r"\ge",
    "≠": r"\ne",
    "≈": r"\approx",
    "∼": r"\sim",
    "≃": r"\simeq",
    "≡": r"\equiv",
    "∝": r"\propto",
    "±": r"\pm",
    "∓": r"\mp",
    "·": r"\cdot",
    "×": r"\times",
    "÷": r"\div",
    "∞": r"\infty",
    "∑": r"\sum",
    "∏": r"\prod",
    "∫": r"\int",
    "∂": r"\partial",
    "∇": r"\nabla",
    "√": r"\sqrt",
    "→": r"\to",
    "←": r"\leftarrow",
    "⇒": r"\Rightarrow",
    "⇔": r"\Leftrightarrow",
    "↔": r"\leftrightarrow",
    "⊂": r"\subset",
    "⊆": r"\subseteq",
    "⊃": r"\supset",
    "⊇": r"\supseteq",
    "∪": r"\cup",
    "∩": r"\cap",
    "∧": r"\land",
    "∨": r"\lor",
    "¬": r"\neg",
    "∀": r"\forall",
    "∃": r"\exists",
    "ℝ": r"\mathbb{R}",
    "ℕ": r"\mathbb{N}",
    "ℤ": r"\mathbb{Z}",
    "ℚ": r"\mathbb{Q}",
    "ℂ": r"\mathbb{C}",
    "ℓ": r"\ell",
    "∘": r"\circ",
    "⊕": r"\oplus",
    "⊗": r"\otimes",
    "⊥": r"\perp",
    "∥": r"\parallel",
    "−": "-",
    "ˆ": r"\hat",  # 单独出现时由后续规则变成 \hat{x}
    "⋈": r"\bowtie",
}

_SUB = str.maketrans(
    "₀₁₂₃₄₅₆₇₈₉₊₋₍₎ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ",
    "0123456789+-()aehijklmnoprstuvx",
)
_SUP = str.maketrans(
    "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁽⁾ⁿ",
    "0123456789+-()n",
)

_SEED = set(_GREEK) | set(_OPS) | set("₀₁₂₃₄₅₆₇₈₉⁰¹²³⁴⁵⁶⁷⁸⁹ˆ")

_PROTECT = re.compile(
    r"(```[\s\S]*?```|"
    r"\$\$[\s\S]*?\$\$|"
    r"(?<!\$)\$(?!\$)(?:\\.|[^$\\])+?\$(?!\$)|"
    r"`[^`]+`)",
    re.MULTILINE,
)


def _map_char(ch: str) -> str:
    if ch in _GREEK:
        return _GREEK[ch]
    if ch in _OPS:
        return _OPS[ch]
    if ch == "{":
        return r"\{"
    if ch == "}":
        return r"\}"
    return ch


def span_to_latex(span: str) -> str:
    """Docling 风格 Unicode/拆分下标 → LaTeX（不含 $）。"""
    s = span.strip()
    out: list[str] = []
    i = 0
    while i < len(s):
        ch = s[i]
        if "\u2080" <= ch <= "\u209c" or ch in "₊₋₍₎":
            buf: list[str] = []
            while i < len(s) and (
                "\u2080" <= s[i] <= "\u209c" or s[i] in "₊₋₍₎"
            ):
                buf.append(s[i].translate(_SUB))
                i += 1
            out.append("_{" + "".join(buf) + "}")
            continue
        if ("\u2070" <= ch <= "\u207f") or ch in "ⁿ⁺⁻⁽⁾":
            buf = []
            while i < len(s) and (
                ("\u2070" <= s[i] <= "\u207f") or s[i] in "ⁿ⁺⁻⁽⁾"
            ):
                buf.append(s[i].translate(_SUP))
                i += 1
            out.append("^{" + "".join(buf) + "}")
            continue
        out.append(_map_char(ch))
        i += 1

    text = "".join(out)
    text = re.sub(r"\s+", " ", text).strip()
    # hat 必须先于下标吸收，否则 \hat p i → \hat_{pi}
    text = re.sub(
        r"(?:ˆ|\\hat)\s*([A-Za-z])\s+([A-Za-z0-9])\b",
        r"\\hat{\1}_{\2}",
        text,
    )
    text = re.sub(r"(?:ˆ|\\hat)\s*([A-Za-z])", r"\\hat{\1}", text)
    # \inI / \inT → \in I（运算符与变量粘连）
    text = re.sub(r"\\(in|notin|subset|subseteq|cup|cap)\s*([A-Z])\b", r"\\\1 \2", text)
    # 仅对“变量样”token 吸收空格下标；运算符 \in \le \pm 等绝不能变 \in_{T}
    _NO_SUB = {
        "in",
        "notin",
        "ni",
        "le",
        "ge",
        "ne",
        "approx",
        "sim",
        "simeq",
        "equiv",
        "propto",
        "pm",
        "mp",
        "cdot",
        "times",
        "div",
        "to",
        "rightarrow",
        "leftarrow",
        "Rightarrow",
        "Leftrightarrow",
        "subset",
        "subseteq",
        "supset",
        "supseteq",
        "cup",
        "cap",
        "land",
        "lor",
        "neg",
        "forall",
        "exists",
        "sum",
        "prod",
        "int",
        "partial",
        "nabla",
        "infty",
        "circ",
        "oplus",
        "otimes",
        "perp",
        "parallel",
        "hat",
        "widehat",
        "tilde",
        "bar",
        "vec",
        "dot",
        "ddot",
        "mathbf",
        "mathrm",
        "mathit",
        "mathcal",
        "mathbb",
        "text",
    }

    def _sub_repl(m: re.Match[str]) -> str:
        head, sub = m.group(1), m.group(2)
        if head.startswith("\\") and head[1:] in _NO_SUB:
            return f"{head} {sub}"
        return f"{head}_{{{sub}}}"

    text = re.sub(
        r"(\\[A-Za-z]+|[A-Za-z])\s+([A-Za-z0-9])(?=$|[\s(),.|=+\-<>\\])",
        _sub_repl,
        text,
    )
    # T_{i} t → T_{it}（同样跳过运算符）
    def _sub2(m: re.Match[str]) -> str:
        head, a, b = m.group(1), m.group(2), m.group(3)
        if head.startswith("\\") and head[1:] in _NO_SUB:
            return m.group(0)
        return f"{head}_{{{a}{b}}}"

    text = re.sub(
        r"([A-Za-z]|\\[A-Za-z]+)_\{([A-Za-z0-9])\}\s+([A-Za-z0-9])(?=$|[\s(),.|=+\-<>\\])",
        _sub2,
        text,
    )
    text = re.sub(r"\\\{\s*", r"\\{", text)
    text = re.sub(r"\s*\\\}", r"\\}", text)
    text = re.sub(r"\s*,\s*", ", ", text)
    text = re.sub(r"\s*([=|])\s*", r" \1 ", text)
    text = re.sub(r"\(\s+", "(", text)
    text = re.sub(r"\s+\)", ")", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _looks_math(span: str, latex: str) -> bool:
    if any(ch in span for ch in _SEED):
        return True
    # 仅接受短变量下标：T_{i} / S_{i}(t)
    return bool(
        re.fullmatch(
            r"[A-Za-z]_\{[A-Za-z0-9]{1,4}\}(?:\([^)]{0,20}\))?",
            latex,
        )
    )


_EN_STOP = frozenset(
    """
    a an the and or but if then else when while for from with without within
    into onto upon over under about after before between among against through
    during until unless although because since while where whether which who
    whom whose what why how that this these those there here thus hence also
    only just even both either neither each every any all some few many much
    more most other such same own so than too very can could may might must
    shall should will would do does did done being been is are was were be
    have has had having of to in on at by as we you they he she it us them
    our your their its my his her
    corresponds denote denotes denoted denoting including both records record
    associated associate instance instances learner course run example specified
    """.split()
)


def _expand_math_span(text: str, center: int) -> tuple[int, int]:
    """从种子字符向两侧扩展到完整行内公式片段。"""
    n = len(text)
    left = right = center

    def brace_depth_between(a: int, b: int) -> int:
        d = 0
        for k in range(a, b + 1):
            if text[k] == "{":
                d += 1
            elif text[k] == "}":
                d -= 1
        return d

    def is_math_atom(i: int, *, from_left: bool) -> bool:
        ch = text[i]
        if ch.isalnum() or ch in _SEED or ch in "()[]{}.=<>+_^\\- \t":
            return True
        # 逗号仅在 {} / [] 内允许：{0, 1} / [0, 1]
        if ch == ",":
            window = text[min(left, i) : max(right, i) + 1]
            if window.count("{") > window.count("}") or window.count("[") > window.count("]"):
                return True
            if from_left:
                return brace_depth_between(i, right) > 0
            return brace_depth_between(left, i) > 0
        return False

    def word_at_left(end: int) -> str:
        j = end
        while j > 0 and text[j - 1].isalpha():
            j -= 1
        return text[j:end]

    def word_at_right(start: int) -> tuple[str, int]:
        j = start
        while j < n and text[j].isalpha():
            j += 1
        return text[start:j], j

    while left > 0 and is_math_atom(left - 1, from_left=True):
        # 不要跨过花括号：`} i ∈ I` 是集合下标，∈ 不应吞掉左侧整段
        if text[left - 1] in "{}":
            break
        if text[left - 1] in "|$":
            break
        if text[left - 1].isalpha():
            word = word_at_left(left)
            if word.lower() in _EN_STOP:
                break
            if len(word) >= 3 and not any(c in word for c in _SEED):
                break
        left -= 1

    while right + 1 < n and is_math_atom(right + 1, from_left=False):
        if text[right + 1] in "{}":
            # 右侧遇到 `{` 仍可纳入集合；`}` 结束
            if text[right + 1] == "}":
                break
        if text[right + 1] in "|$":
            # 表格单元格 | 或数学定界不应吞进公式
            break
        if text[right + 1] == "(":
            peek = text[right + 1 : right + 8].lower()
            if peek.startswith("(e.g") or peek.startswith("(i.e") or peek.startswith("(cf"):
                break
        if text[right + 1].isalpha():
            word, j = word_at_right(right + 1)
            if word.lower() in _EN_STOP:
                break
            if len(word) >= 3 and not any(c in word for c in _SEED):
                break
            if len(word) <= 2:
                right = j - 1
                continue
            break
        right += 1

    while left <= right and text[left] in " \t,;:":
        left += 1
    while right >= left and text[right] in " \t,;:":
        right -= 1
    return left, right


def _convert_plain(text: str, *, mode: str = "safe") -> str:
    if not text:
        return text

    # 1) 含希腊/数学符号的片段
    used = [False] * len(text)
    replacements: list[tuple[int, int, str]] = []
    for i, ch in enumerate(text):
        if ch not in _SEED or used[i]:
            continue
        a, b = _expand_math_span(text, i)
        if a > b or any(used[a : b + 1]):
            continue
        span = text[a : b + 1]
        if len(span) > 100:
            continue
        latex = span_to_latex(span)
        if not _looks_math(span, latex):
            continue
        for k in range(a, b + 1):
            used[k] = True
        replacements.append((a, b + 1, f"${latex}$"))

    if replacements:
        replacements.sort(key=lambda x: x[0])
        out: list[str] = []
        pos = 0
        for a, b, rep in replacements:
            out.append(text[pos:a])
            out.append(rep)
            pos = b
        out.append(text[pos:])
        text = "".join(out)

    # 2) 大写变量拆开下标：仅 aggressive（debug1：默认不要猜 T i）
    if mode != "aggressive":
        return text

    def repl_short(m: re.Match[str]) -> str:
        var, sub = m.group(1), m.group(2)
        rest = m.group(3) or ""
        latex = f"{var}_{{{sub}}}"
        if rest:
            inner = re.sub(r"\s+", "", rest)
            latex += inner
        return f"${latex}$"

    text = re.sub(
        r"(?<![A-Za-z\\$])([A-Z])\s+([a-z0-9])(?:\s*(\(\s*[a-z0-9]+\s*\)))?(?![A-Za-z])",
        repl_short,
        text,
    )
    return text


def convert_inline_unicode_math(md: str, *, mode: str = "safe") -> str:
    """正文 Unicode → $LaTeX$。safe 不做 `T i` 猜测。

    Markdown 表格行单独处理：禁止 ±/∈ 跨 `|` 包成数学，否则会把整行管道拆烂。
    """
    out_lines: list[str] = []
    for line in md.splitlines(keepends=True):
        core, nl = line, ""
        if line.endswith("\n"):
            core, nl = line[:-1], "\n"
        if _is_md_table_line(core):
            out_lines.append(_repair_table_line_math(core) + nl)
            continue
        parts: list[str] = []
        last = 0
        for m in _PROTECT.finditer(core):
            parts.append(_convert_plain(core[last : m.start()], mode=mode))
            parts.append(m.group(0))
            last = m.end()
        parts.append(_convert_plain(core[last:], mode=mode))
        out_lines.append("".join(parts) + nl)
    return "".join(out_lines)


def _is_md_table_line(line: str) -> bool:
    s = line.strip()
    if not s.startswith("|"):
        return False
    # 至少两个单元格分隔
    return s.count("|") >= 2


def _repair_table_line_math(line: str) -> str:
    """表格行：只粘合小数、规范化 mean±std，绝不跨 `|` 包 $。"""
    # 分隔行不动
    if re.match(r"^\s*\|[\s\-:|]+\|\s*$", line):
        return line

    parts = line.split("|")
    fixed: list[str] = []
    for idx, cell in enumerate(parts):
        c = cell
        # 清掉贴管道/残留 $
        c = c.replace("$", "")
        for _ in range(8):
            c2, n = re.subn(r"(\d+)\s+\.\s+(\d+)", r"\1.\2", c)
            c = c2
            if not n:
                break
        # 0 . . 0059 / . 0050
        c = re.sub(r"(\d+)\s*\.\s*\.\s*(\d+)", r"\1.\2", c)
        c = re.sub(r"(?<![\d.])\.\s+(\d{2,})", r"0.\1", c)
        # mean ± std → $0.8602 \pm 0.0028$
        c = re.sub(
            r"(?<![\w.\\])(\d+\.\d+)\s*±\s*(\d+\.\d+)(?![\w.])",
            r"$\1 \\pm \2$",
            c,
        )
        c = re.sub(
            r"(?<![\w.\\$])(\d+\.\d+)\s*\\pm\s*(\d+\.\d+)(?![\w.])",
            r"$\1 \\pm \2$",
            c,
        )
        # 单元格两侧留空，避免 |$0.86$| 挤在一起
        if idx == 0 or idx == len(parts) - 1:
            fixed.append(c)
        else:
            inner = c.strip()
            fixed.append(f" {inner} " if inner else c)
    return "|".join(fixed)


def extract_bold_phrases(
    pdf_path: Path, *, min_len: int = 3, max_len: int = 60
) -> list[str]:
    """用 PyMuPDF 从 PDF 提取粗体短语。"""
    try:
        import pymupdf
    except Exception:
        return []

    phrases: dict[str, int] = {}
    try:
        doc = pymupdf.open(pdf_path)
    except Exception:
        return []

    try:
        for page in doc:
            for block in page.get_text("dict").get("blocks", []):
                for line in block.get("lines", []):
                    bold_bits: list[str] = []
                    for span in line.get("spans", []):
                        raw = (span.get("text") or "").replace("\xa0", " ")
                        font = (span.get("font") or "").lower()
                        flags = int(span.get("flags") or 0)
                        is_bold = bool(flags & 2**4) or any(
                            k in font
                            for k in (
                                "bold",
                                "black",
                                "heavy",
                                "semibold",
                                "demibold",
                                "-bd",
                                "cmbx",
                                "cmbxti",
                            )
                        )
                        if is_bold and raw:
                            bold_bits.append(raw)
                        elif bold_bits:
                            phrase = re.sub(r"\s+", " ", "".join(bold_bits)).strip()
                            if min_len <= len(phrase) <= max_len:
                                phrases[phrase] = phrases.get(phrase, 0) + 1
                            bold_bits = []
                    if bold_bits:
                        phrase = re.sub(r"\s+", " ", "".join(bold_bits)).strip()
                        if min_len <= len(phrase) <= max_len:
                            phrases[phrase] = phrases.get(phrase, 0) + 1
    finally:
        doc.close()

    stop = {
        "abstract",
        "introduction",
        "references",
        "appendix",
        "acknowledgements",
        "acknowledgment",
        "day",
        "days",
        "fig",
        "figure",
        "table",
        "section",
        "eq",
        "equation",
        "and",
        "or",
        "the",
        "of",
        "to",
        "in",
        "on",
        "for",
        "with",
    }
    items = []
    for p in phrases:
        pl = p.lower().strip(" .:;,")
        if pl in stop:
            continue
        if p.startswith("http"):
            continue
        if re.fullmatch(r"[\d\W]+", p):
            continue
        # 过短且无字母数字混合的短语跳过（减少 **Day** 这类碎片）
        if len(p) < 4 and not re.search(r"[A-Za-z].*[0-9]|[0-9].*[A-Za-z]", p):
            if " " not in p:
                continue
        items.append(p)
    items.sort(key=len, reverse=True)
    return items


def apply_bold_phrases(md: str, phrases: list[str]) -> str:
    if not phrases:
        return md

    # 整篇统一计数，避免按段落重置导致 LEAP 被加粗几十次
    counters: dict[str, int] = {p: 0 for p in phrases}
    parts: list[str] = []
    last = 0
    for m in _PROTECT.finditer(md):
        parts.append(
            _bold_plain(md[last : m.start()], phrases, counters=counters)
        )
        parts.append(m.group(0))
        last = m.end()
    parts.append(_bold_plain(md[last:], phrases, counters=counters))
    return "".join(parts)


def _bold_plain(
    text: str,
    phrases: list[str],
    *,
    counters: dict[str, int],
) -> str:
    out = text
    for phrase in phrases:
        if len(phrase) < 2 or phrase not in out:
            continue
        limit = 2
        if " " not in phrase and phrase.isupper() and len(phrase) <= 6:
            limit = 1
        pat = re.compile(re.escape(phrase))

        def wrap(m: re.Match[str], _phrase=phrase, _limit=limit) -> str:
            if counters.get(_phrase, 0) >= _limit:
                return m.group(0)
            s, e = m.start(), m.end()
            left = m.string[max(0, s - 2) : s]
            right = m.string[e : e + 2]
            if left.endswith("**") or right.startswith("**"):
                return m.group(0)
            if s > 0 and m.string[s - 1].isalnum():
                return m.group(0)
            if e < len(m.string) and m.string[e].isalnum():
                return m.group(0)
            line_start = m.string.rfind("\n", 0, s) + 1
            if m.string[line_start : line_start + 1] == "#":
                return m.group(0)
            counters[_phrase] = counters.get(_phrase, 0) + 1
            return f"**{m.group(0)}**"

        out = pat.sub(wrap, out)
    return out


def postprocess_markdown(
    md: str,
    *,
    pdf_path: Path | None = None,
    fix_inline_math: bool = True,
    fix_bold: bool = True,
    mode: str = "safe",
) -> str:
    text = md
    if fix_inline_math:
        text = convert_inline_unicode_math(text, mode=mode)
    if fix_bold and pdf_path is not None and Path(pdf_path).exists():
        text = apply_bold_phrases(text, extract_bold_phrases(Path(pdf_path)))
    return text
