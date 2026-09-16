"""行内 Unicode / 拆分公式 → LaTeX。从 md_postprocess 拆出。"""
from __future__ import annotations

import re
import unicodedata

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
    from app.utils.md_postprocess import _is_md_table_line, _repair_table_line_math

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
