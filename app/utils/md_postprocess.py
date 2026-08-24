"""Markdown 后处理：补行内公式 LaTeX、尽量恢复 PDF 粗体。

Docling 公式 enrichment 只处理版面标成 FORMULA 的行间公式；
正文里的 δ、∈、T i 等通常是 Unicode/纯文本。PDF 管线也不把
font bold 写进 TextItem.formatting，导致 **粗体** 丢失。
"""
from __future__ import annotations

import re
import unicodedata
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

    # 多字符空格下标：\gamma 3 jc → \gamma_{3jc}（Docling 常把 γ_{3jc} 拆开）
    def _multi_sub(m: re.Match[str]) -> str:
        head, body = m.group(1), m.group(2)
        if head.startswith("\\") and head[1:] in _NO_SUB:
            return m.group(0)
        compact = re.sub(r"\s+", "", body)
        return f"{head}_{{{compact}}}"

    text = re.sub(
        r"(\\[A-Za-z]+)\s+((?:\d+|[A-Za-z]+)(?:\s+(?:\d+|[A-Za-z]+)){0,6})"
        r"(?=\s*[\(\[\)\].,;=+\-]|\s*$)",
        _multi_sub,
        text,
    )
    # 已有 _{…} 后再跟空格字母：\gamma_{3} jc → \gamma_{3jc}
    for _ in range(4):
        text2, n = re.subn(
            r"(\\[A-Za-z]+)_\{([^}]+)\}\s+([A-Za-z0-9]+)"
            r"(?=\s*[\(\[\)\].,;=+\-]|\s|$)",
            r"\1_{\2\3}",
            text,
        )
        text = text2
        if not n:
            break
    # ) s → )_s（交互项后的下标）
    text = re.sub(
        r"(\))\s+([A-Za-z0-9])(?=$|[\s),.=+\-\\|])",
        r"\1_{\2}",
        text,
    )

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
    # \gamma_{3jc} (TMA → \gamma_{3jc}(TMA
    text = re.sub(r"(\\[A-Za-z]+_\{[^}]+\})\s+\(", r"\1(", text)
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
        if text[right + 1] == "\\":
            # 纳入 \cdot / \times 等命令
            j = right + 2
            while j < n and text[j].isalpha():
                j += 1
            if j > right + 2:
                right = j - 1
                continue
            break
        if text[right + 1] == "(":
            peek = text[right + 1 : right + 8].lower()
            if peek.startswith("(e.g") or peek.startswith("(i.e") or peek.startswith("(cf"):
                break
        if text[right + 1].isalpha():
            word, j = word_at_right(right + 1)
            if word.lower() in _EN_STOP:
                break
            # 允许短全大写缩写（TMA / IMD）进入已启动的公式
            if len(word) >= 3 and not any(c in word for c in _SEED):
                if not (word.isupper() and len(word) <= 8):
                    break
            if len(word) <= 2 or (word.isupper() and len(word) <= 8):
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


def _fold_math_alphanumeric(text: str) -> str:
    """数学斜体/粗体字母（U+1D400…）→ 普通希腊/拉丁，便于当公式种子识别。"""
    if not text:
        return text
    out: list[str] = []
    for ch in text:
        o = ord(ch)
        if 0x1D400 <= o <= 0x1D7FF:
            out.append(unicodedata.normalize("NFKC", ch))
        else:
            out.append(ch)
    return "".join(out)


def _glue_split_acronym_inline_math(text: str) -> str:
    """修复半截行内公式：TMA$1 \\cdot$ IMD → TMA1 \\cdot IMD。

    Docling 常把缩写+数字拆开，只把中间 `$1 \\cdot$` 标成公式。
    """
    if "$" not in text:
        return text
    text = re.sub(
        r"([A-Za-z]{2,})\$(\d+)\s*((?:\\cdot|\\times|[·⋅]))\$(?=\s*[A-Za-z])",
        r"\1\2 \3",
        text,
    )
    text = re.sub(r"([A-Za-z]{2,})\$(\d+)\$", r"\1\2", text)
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
        # 先折叠数学字母、粘合半截 $…$，再保护已有公式块
        core = _fold_math_alphanumeric(core)
        core = _glue_split_acronym_inline_math(core)
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


def _is_md_image_line(line: str) -> bool:
    """Markdown 图片引用行（整行）。"""
    return bool(re.match(r"^\s*!\[[^\]]*\]\([^)]+\)\s*$", line))


def ensure_figure_table_separation(md: str) -> str:
    """
    硬规则：表格行与图片引用之间必须至少空一行。

    否则 CommonMark/多数渲染器会把 `![...](...)` 吃进表格单元格，
    导致图片「进入表格内」。图片前后的表格都要隔开。
    """
    if not md:
        return md
    lines = md.splitlines(keepends=True)
    out: list[str] = []

    def _core(s: str) -> str:
        return s[:-1] if s.endswith("\n") else s

    for line in lines:
        core = _core(line)
        if out:
            prev = _core(out[-1])
            # 跳过已有空行
            if prev.strip() != "":
                need_gap = (_is_md_table_line(prev) and _is_md_image_line(core)) or (
                    _is_md_image_line(prev) and _is_md_table_line(core)
                )
                # 图注行紧跟图片是允许的；但表格紧贴图片不行
                if need_gap:
                    out.append("\n")
        out.append(line)
    return "".join(out)


# Docling CodeFormula 常把版面装饰/对齐残片读成 \text{...}
_LAYOUT_TEXT_SCRAPS = frozenset(
    {
        "red",
        "al",  # aligned 残片
        "ign",
        "aligned",
        "bottom",
        "top",
        "left",
        "right",
        "center",
        "centre",
        "wein",
        "out",
        "blue",
        "green",
        "black",
        "white",
        "gray",
        "grey",
        "weighted",
        "equative",
        "due",
        "that",
        "graphs",
        "scale of",
        "scale of,",
        "to the",
        "this, we",
        "this we",
        "accorages",
        "code",
        "pang",
        "a pang",
    }
)

# 公式内允许保留的短说明词
_TEXT_KEEP = frozenset(
    {
        "if",
        "otherwise",
        "otherwise.",
        "and",
        "or",
        "where",
        "if node",
    }
)

_DISPLAY_MATH = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)
_FORMULA_CORRUPT_MARK = "<!-- formula-not-decoded -->"


def _norm_text_inner(inner: str) -> str:
    return re.sub(r"\s+", " ", inner).strip().lower()


def _is_prose_scrap_text(inner: str) -> bool:
    """判断 \\text{...} 是否为混入公式的英文垃圾。"""
    t = _norm_text_inner(inner)
    if not t:
        return True
    if t in _LAYOUT_TEXT_SCRAPS:
        return True
    # 允许 cases 里的短说明
    if t in _TEXT_KEEP or t.startswith("if node") or t.startswith("otherwise"):
        return False
    if t in {"and", " or "}:
        return False
    # 带空格的 " and " 保留
    if t.strip() == "and":
        return False
    # 空格拆开的词：s e f t i m e
    if re.fullmatch(r"[a-z](?:\s+[a-z]){2,}", t):
        return True
    # 纯英文短语（≥2 词）且不含数学符号 → 垃圾
    if re.fullmatch(r"[a-z][a-z\s,',.-]{2,}", t) and " " in t and len(t) <= 40:
        return True
    return False


def _display_still_contaminated(s: str) -> bool:
    """清理后仍明显不可信 → 宁可不输出假公式。"""
    low = s.lower()
    if r"\intertext" in low or r"\code" in low:
        return True
    if re.search(r"\bw\s+h\s+e\s+n\b", low):
        return True
    if "accorages" in low or "seftime" in low.replace(" ", ""):
        return True
    if r"\stackrel" in low:
        return True
    # 多个散文 \text
    texts = [_norm_text_inner(x) for x in re.findall(r"\\text\s*\{([^}]*)\}", s, flags=re.I)]
    if sum(1 for t in texts if _is_prose_scrap_text(t) or (t and t not in _TEXT_KEEP and " " in t)) >= 2:
        return True
    # 明显散文噪声：空格拆开的小写串仍在
    if re.search(r"(?:^|[^\\])([a-z]\s+){3,}[a-z]\b", low):
        return True
    return False


def _repair_one_display_math(body: str) -> str:
    """清理单个 $$...$$；过高污染时返回空串（由上层换成 not-decoded 标记）。"""
    s = body

    # 0) 直接扔掉 intertext / code（几乎全是 OCR 串台）
    s = re.sub(r"\\intertext\s*\{[^}]*\}", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\\code\s*\{[^}]*\}", "", s, flags=re.IGNORECASE)

    # 1) 去掉布局/散文垃圾 \text{...}（保留 if/otherwise）
    def _drop_scrap_text(m: re.Match[str]) -> str:
        return "" if _is_prose_scrap_text(m.group(1)) else m.group(0)

    s = re.sub(r"\\text\s*\{\s*([^}]*)\s*\}", _drop_scrap_text, s, flags=re.IGNORECASE)

    # 1b) 行首空格拆开的英文：w h e n \, p
    s = re.sub(r"^(?:[a-z]\s+){2,}[a-z]\b(?:\s*\\,)?\s*", "", s, flags=re.I)
    s = re.sub(r"\\\\\s*(?:[a-z]\s+){2,}[a-z]\b(?:\s*\\,)?\s*", r"\\\\ ", s, flags=re.I)

    # 2) logit 被拆成 \log i / \log i t
    s = re.sub(r"\\log\s*i\s*t\b", r"\\operatorname{logit}", s)
    s = re.sub(r"\\log\s*i\b(?=\s*[\(\\{])", r"\\operatorname{logit}", s)

    # 3) 多字母缩写被空格拆开：T M A 1 → TMA1
    def _glue_caps(m: re.Match[str]) -> str:
        return re.sub(r"\s+", "", m.group(0))

    s = re.sub(
        r"(?<![A-Za-z\\])(?:[A-Z]\s+){1,8}[A-Z](?:\s*\d+)?(?![A-Za-z])",
        _glue_caps,
        s,
    )

    # 3b) 高置信结构修复（Markov Stability / 通用 Laplacian）
    # e^{-t l} / e^{-t t} → e^{-tL}
    s = re.sub(r"e\s*\^\s*\{\s*-\s*t\s*[lt]\s*\}", r"e^{-tL}", s, flags=re.I)
    # \mathfrak{p} → \mathbf{p}（向量概率）
    s = re.sub(r"\\mathfrak\s*\{\s*p\s*\}", r"\\mathbf{p}", s)
    # min_{t ≺ t} → min_{τ < t}
    s = re.sub(r"\\min\s*_\s*\{\s*t\s*(?:\\prec|<)\s*t\s*\}", r"\\min_{\\tau < t}", s)
    # max_H (t,H) → max_H r(t,H)
    s = re.sub(
        r"(\\max\s*_\s*\{\s*H\s*\})\s*\(\s*t\s*,\s*H\s*\)",
        r"\1 r(t, H)",
        s,
    )
    # 丢掉无意义的 \stackrel{\circ}{a} 残片
    s = re.sub(r"\\stackrel\s*\{[^}]*\}\s*\{[^}]*\}", "", s)
    s = re.sub(r"(\\begin\{aligned\})\s*(?:&\s*)+", r"\1 ", s)
    # membership 定义前的无关 frac 噪声
    if re.search(r"H\s*_\s*\{\s*i\s*c\s*\}\s*=\s*\\begin\s*\{\s*cases\s*\}", s):
        s = re.sub(
            r"^.*?(\\quad\s*)?(H\s*_\s*\{\s*i\s*c\s*\}\s*=)",
            r"\2",
            s,
            count=1,
            flags=re.DOTALL,
        )
    # VI 定义：丢掉前面的 ker / 2Ω 残片，只留 VI = …
    if re.search(r"\bVI\s*\(", s) and r"\Omega" in s:
        m_vi = re.search(
            r"VI\s*\(\s*H\s*,\s*H\s*\^\s*\{\s*\\prime\s*\}\s*\)\s*=\s*"
            r"\\frac\s*\{.*?\}\s*\{\s*\\log\s*\(\s*N\s*\)\s*\}\s*(?:,\s*\(?\s*8\s*\)?)?",
            s,
            flags=re.DOTALL,
        )
        if m_vi:
            s = m_vi.group(0)
            s = re.sub(r",\s*\(?\s*8\s*\)?\s*$", "", s)
    # V(t) 求和下标 i∈j → i≠j；内侧 V( → VI(
    if re.search(r"V\s*\(\s*t\s*\)\s*=", s) and r"\sum" in s:
        s = re.sub(r"\\sum\s*_\s*\{\s*i\s*\\in\s*j\s*\}", r"\\sum_{i \\neq j}", s)
        s = re.sub(
            r"\\sum\s*_\s*\{\s*i\s*\\neq\s*j\s*\}\s*V\s*\(",
            r"\\sum_{i \\neq j} VI(",
            s,
        )
        s = re.sub(r"^V\s*\(\s*t\s*\)", r"VI(t)", s)
    # ν(t,t') 重复行：只留第一行定义
    if s.count(r"\nu") >= 2 and r"\widehat" in s:
        m_nu = re.search(
            r"\\nu\s*\(\s*t\s*,\s*t\s*\^\s*\{\s*\\prime\s*\}\s*\)\s*=\s*"
            r"\\,?\s*\\nu\s*\(\s*\\widehat\s*\{\s*H\s*\}\s*\(\s*t\s*\)\s*,\s*"
            r"\\widehat\s*\{\s*H\s*\}\s*\(\s*t\s*\^\s*\{\s*\\prime\s*\}\s*\)\s*\)\s*"
            r"(?:\.\s*(?:\(\s*1\s*0\s*\))?)?",
            s,
            flags=re.DOTALL,
        )
        if m_nu:
            s = m_nu.group(0)
            s = re.sub(r"\s*\(\s*1\s*0\s*\)\s*$", r" \\quad (10)", s)
    # 行尾 A pang / 噪声（字母间可能夹杂 \\ ）
    s = re.sub(
        r"(?:\\|\s)*A(?:\\|\s)*p(?:\\|\s)*a(?:\\|\s)*n(?:\\|\s)*g\s*\{[^}]*\}\s*$",
        "",
        s,
        flags=re.I,
    )
    s = re.sub(r"(?:\\\\)?\s*\\text\s*\{\s*this,\s*we\s*\}\s*$", "", s, flags=re.I)
    # 行首残留的孤立 p \quad（when 被剥掉后）
    s = re.sub(r"^p\s*\\quad\s*", "", s)
    # 行尾无意义的 \quad 与 \\ 空格串
    s = re.sub(r"(?:\\quad|\s|\\ )+$", "", s)

    # 4) array → aligned（同前）
    if r"\begin{array}" in s and r"\end{array}" in s:
        inner = re.sub(r"\\begin\{array\}\s*\{[^}]*\}", "", s, count=1)
        inner = re.sub(r"\\end\{array\}", "", inner)
        inner = re.sub(r"(^|\\\\)\s*&", r"\1 ", inner)
        s2 = inner.strip()
        if "&" not in s2 and r"\\" in s2:
            s = s2
        elif s2.count("&") <= s2.count(r"\\") + 1:
            s = r"\begin{aligned}" + s2 + r"\end{aligned}"
        else:
            s = s2

    # 5) 非 align 内孤立 &
    if r"\begin{aligned}" not in s and r"\begin{align}" not in s:
        s = re.sub(r"\s*&\s*", " ", s)

    # 6) 空白 / 编号 / F1
    s = re.sub(r"\(\s*(\d+)\s*\)", r"(\1)", s)
    s = re.sub(r"[ \t]{2,}", " ", s)
    s = re.sub(r"\s*\\\\\s*", r" \\\\ ", s)
    s = re.sub(r"\s*\\quad\s*", r" \\quad ", s)
    s = re.sub(r"\s*\\\\\s*(\\end\{(?:aligned|align)\})", r" \1", s)
    s = re.sub(r"(?:\\\\|\s)+$", "", s)
    # 命令名后多余空格：\hat { p } → \hat{p}
    s = re.sub(r"\\([A-Za-z]+)\s*\{\s*", r"\\\1{", s)
    s = re.sub(r"\s*\}", "}", s)
    if "F1" in s and "Prec" in s:
        s2 = re.sub(
            r"F1\s*=\s*\\frac\s*\{\s*2\s*\\mathrm\{Prec\}\s*\{\s*\\mathrm\{Rec\}\s*\}\s*\}"
            r"\s*\{\s*\\mathrm\{Prec\}\s*\{\s*\+\s*\\mathrm\{Rec\}\s*\}\s*\}\s*,\s*"
            r"\\quad\s*\\mathrm\{Prec\}\s*\{\s*=\s*\\frac\s*\{\s*TP\s*\}\s*\{\s*TP\s*\+\s*FP\s*\}\s*\}\s*,\s*"
            r"\\quad\s*\\mathrm\{Rec\}\s*=\s*\\frac\s*\{\s*TP\s*\}\s*\{\s*TP\s*\+\s*FN\s*\}\s*\.?",
            r"F1 = \\frac{2 \\cdot \\mathrm{Prec} \\cdot \\mathrm{Rec}}{\\mathrm{Prec} + \\mathrm{Rec}}, "
            r"\\quad \\mathrm{Prec} = \\frac{TP}{TP + FP}, "
            r"\\quad \\mathrm{Rec} = \\frac{TP}{TP + FN}.",
            s,
            flags=re.DOTALL,
        )
        s = s2

    s = s.strip()
    if _display_still_contaminated(s):
        return ""
    return s


def repair_display_formula_scraps(md: str) -> str:
    """
    清理 Docling 完整公式中的版面边角料。

    清不干净的高污染块改为 `<!-- formula-not-decoded -->`，禁止输出假公式。
    """
    if not md or "$$" not in md:
        return md

    def _repl(m: re.Match[str]) -> str:
        body = m.group(1)
        fixed = _repair_one_display_math(body)
        compact = re.sub(r"\s+", "", fixed)
        if not compact:
            return _FORMULA_CORRUPT_MARK
        if len(compact) <= 4 and re.fullmatch(r"[=+\-*/]?\d*", compact or ""):
            return ""
        if compact in {"=", "+", "-", "(", ")"}:
            return ""
        return f"$$\n{fixed.strip()}\n$$"

    out = _DISPLAY_MATH.sub(_repl, md)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out


def normalize_display_math_multiline(md: str) -> str:
    """
    将行间公式统一为多行围栏（Typora / CommonMark 标准）：

        $$
        ...
        $$

    禁止输出单行 `$$...$$`：带 `\\tag{n}` 时 Typora 常不渲染右侧编号。
    """
    if not md or "$$" not in md:
        return md

    def _repl(m: re.Match[str]) -> str:
        body = (m.group(1) or "").strip()
        return f"$$\n{body}\n$$"

    return _DISPLAY_MATH.sub(_repl, md)


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
        # 表格里的数学斜体（𝐴𝑣𝑒𝑟𝑎𝑔𝑒 / 𝑃）先折成普通字母
        c = _fold_math_alphanumeric(c)
        c = c.replace("∑", r"$\sum$")
        # 单希腊字母：τ / β → $\tau$
        for g, cmd in _GREEK.items():
            if g in c and len(g) == 1:
                c = c.replace(g, f"${cmd}$")
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
        # 𝑃 0 → $P_0$（折完后的短变量下标）
        c = re.sub(
            r"(?<![A-Za-z\\$])([A-Z])\s+(\d)\b",
            r"$\1_{\2}$",
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


def repair_prose_artifacts(md: str) -> str:
    """正文里高频、与公式无关的 Docling/转义残片。"""
    if not md:
        return md
    # 千分位被拆进数学：29,$390 / 29$,370 → 29,390 / 29,370
    md = re.sub(r"(\d+),\$(\d{3})\b", r"\1,\2", md)
    md = re.sub(r"(\d+)\$,(\d{3})\b", r"\1,\2", md)
    # Markdown 误转义下划线：student\_assessments / view\_only
    md = re.sub(r"\\_", "_", md)
    # fi 连字被拆：de fi ne / ef fi cient / identi fi es
    md = re.sub(r"\b([A-Za-z]+)\s+fi\s+([A-Za-z]+)\b", r"\1fi\2", md)
    # 孤立页码行（图片后的 9 / 10）
    md = re.sub(r"(?m)\n\n(\d{1,2})\n\n", "\n\n", md)
    # 控制字符
    md = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", md)
    return md


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
        # 完整 $$...$$ 中的版面边角料 / 拆散词（与行内识别分开）
        text = repair_display_formula_scraps(text)
    text = repair_prose_artifacts(text)
    if fix_bold and pdf_path is not None and Path(pdf_path).exists():
        text = apply_bold_phrases(text, extract_bold_phrases(Path(pdf_path)))
    # 永远保证：表格与图片之间空一行（防图片并入表格）
    text = ensure_figure_table_separation(text)
    # 行间公式：多行 $$ 围栏（单行 $$...$$ 会导致 Typora \\tag 不显示）
    text = normalize_display_math_multiline(text)
    from app.utils.typora_math_repair import repair_typora_math_in_markdown

    text = repair_typora_math_in_markdown(text)
    return text
