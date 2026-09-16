"""Markdown 后处理编排。硬规则（表格↔图片空行、行间公式多行围栏）留在本文件。

行内公式 / 粗体 / 正文残片见 md_inline_math / md_bold / md_prose。
"""
from __future__ import annotations

import re
from pathlib import Path

from app.utils.md_bold import apply_bold_phrases, extract_bold_phrases
from app.utils.md_inline_math import (
    _GREEK,
    _fold_math_alphanumeric,
    convert_inline_unicode_math,
    span_to_latex,
)
from app.utils.md_prose import repair_prose_artifacts

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


def collapse_extra_blank_lines(md: str) -> str:
    """Markdown 层：连续空行压成一行空行。"""
    return re.sub(r"\n{3,}", "\n\n", md or "")


def normalize_heading_spacing(md: str) -> str:
    """标题前后至少空一行（文件开头除外）。"""
    if not md:
        return md
    out = re.sub(r"(?m)([^\n])\n(#{1,6} )", r"\1\n\n\2", md)
    out = re.sub(r"(?m)^(#{1,6} .+)\n([^\n#])", r"\1\n\n\2", out)
    return collapse_extra_blank_lines(out)


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
    text = normalize_heading_spacing(text)
    from app.utils.typora_math_repair import repair_typora_math_in_markdown

    text = repair_typora_math_in_markdown(text)
    return text
