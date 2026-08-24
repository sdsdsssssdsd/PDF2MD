"""PDF 几何信息：用 baseline/字号判断上下标（Phase 几何）。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class GeoChar:
    char: str
    x0: float
    y0: float
    x1: float
    y1: float
    size: float
    font: str
    origin_y: float


def extract_page_chars(pdf_path: Path, page_index: int) -> list[GeoChar]:
    try:
        import pymupdf
    except Exception:
        return []
    try:
        doc = pymupdf.open(pdf_path)
    except Exception:
        return []
    try:
        if page_index < 0 or page_index >= len(doc):
            return []
        page = doc[page_index]
        out: list[GeoChar] = []
        for block in page.get_text("rawdict").get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    size = float(span.get("size") or 0)
                    font = span.get("font") or ""
                    for ch in span.get("chars", []):
                        c = ch.get("c") or ""
                        if not c:
                            continue
                        b = ch.get("bbox") or (0, 0, 0, 0)
                        origin = ch.get("origin") or (b[0], b[3])
                        out.append(
                            GeoChar(
                                char=c,
                                x0=float(b[0]),
                                y0=float(b[1]),
                                x1=float(b[2]),
                                y1=float(b[3]),
                                size=size,
                                font=font,
                                origin_y=float(origin[1]),
                            )
                        )
        return out
    finally:
        doc.close()


_XTI = re.compile(
    r"(?<![A-Za-z\\])([A-Za-z])\s*\(\s*([A-Za-z0-9]+)\s*\)\s*([A-Za-z0-9])(?![A-Za-z,])"
)
# T ( t ) i,g → T_{i,g}^{(t)}（必须先于普通 XTI，否则会拆成 T_i^{(t)}, g）
_XTI_COMMA = re.compile(
    r"(?<![A-Za-z\\])([A-Za-z])\s*\(\s*([A-Za-z0-9]+)\s*\)\s*"
    r"([A-Za-z0-9])\s*,\s*([A-Za-z0-9])(?![A-Za-z])"
)
# R ( ≤ t ) i / R (\le t) i → R_i^{(\le t)}
_RTI = re.compile(
    r"(?<![A-Za-z\\])([A-Za-z])\s*\(\s*(?:≤|\\le|\\leq)\s*([A-Za-z0-9]+)\s*\)\s*([A-Za-z0-9])(?![A-Za-z])"
)
_RI = re.compile(
    # 含 F：PDF 中 Ft 截断算子；避免 Rec（R e c 由短语层处理）
    r"(?<![A-Za-z\\])([FRSTXYZNMKI])\s+([ijklmnpt])(?![A-Za-z0-9])"
)
# t 1 / t K：小写变量 + 数字或单大写下标
_T_SUB = re.compile(
    r"(?<![A-Za-z\\$])([txyijkmn])\s+([0-9A-Z])(?![A-Za-z0-9])"
)
# D ( t ) / I ( t )：单字母函数应用（XTI 已处理 x(t)i）
# 仅拒绝后面跟单字符下标；允许 ") contains" 这类正文
_FUNC_T = re.compile(
    r"(?<![A-Za-z\\$])([DIT])\s*\(\s*([A-Za-z0-9]+)\s*\)(?!\s*[A-Za-z0-9](?![A-Za-z0-9]))"
)
# predictor f ( t ) → f^{(t)}
_F_SUP = re.compile(
    r"(?<![A-Za-z\\$])f\s*\(\s*t\s*\)(?!\s*[A-Za-z0-9](?![A-Za-z0-9]))"
)


def _repair_high_confidence_phrases(text: str) -> tuple[str, int]:
    """整段高置信公式（避免把集合定义拆成碎 $）。"""
    edits = 0
    out = text

    def sub(pattern: str, repl: str, s: str, flags: int = 0) -> tuple[str, int]:
        return re.subn(pattern, repl, s, flags=flags)

    # T = { t 1 , . . . , t K }
    out2, n = sub(
        r"\bT\s*=\s*\{\s*t\s+1\s*,\s*\.\s*\.\s*\.\s*,\s*t\s+K\s*\}",
        r"$T = \\{t_1, \\ldots, t_K\\}$",
        out,
    )
    if n:
        out = out2
        edits += n

    # D ( t ) = { ( x ( t ) i , y i ) } i ∈ I ( t )
    # 也兼容 ∈I 粘连、以及 safe 已局部加 $ 的残片
    out2, n = sub(
        r"D\s*\(\s*t\s*\)\s*=\s*\{\s*\(\s*"
        r"(?:x\s*\(\s*t\s*\)\s*i|\$x_\{i\}\^\{\(t\)\}\$)\s*,\s*"
        r"(?:y\s+i|\$y_\{i\}\$?)\s*"
        r"\)\s*(?:\\\})?\}\s*"
        r"(?:\$)?i\s*(?:∈|\\in)\s*I\s*\(\s*t\s*\)\$?",
        r"$D(t) = \\{(x_i^{(t)}, y_i)\\}_{i \\in I(t)}$",
        out,
    )
    if n:
        out = out2
        edits += n

    # 集合下标残片：} $i \in I(t)$ / } i ∈ I ( t )
    out2, n = sub(
        r"\}\s*\$?\s*([a-z])\s*(?:∈|\\in)\s*([A-Z])\s*\(\s*([^)]+?)\s*\)\$?",
        r"\}_{{\1} \\in \2(\3)}",
        out,
    )
    if n:
        out = out2
        edits += n

    # PDF/AMS 常把 ⋈ 编码成相邻的 ⋊⋉；对照视觉与语义为 join/bowtie
    out2, n = sub(r"⋊\s*⋉", r"\\bowtie", out)
    if n:
        out = out2
        edits += n
    out2, n = sub(r"⋈", r"\\bowtie", out)
    if n:
        out = out2
        edits += n

    # safe 残片：$S (\le t) 1$ \bowtie $S (\le t) 2).$ → 单段 + 括号句点外置
    out2, n = sub(
        r"\$S\s*\(\\le t\)\s*1\$\s*\\bowtie\s*\$S\s*\(\\le t\)\s*2\)\.\$",
        r"$S_{1}^{(\\le t)} \\bowtie S_{2}^{(\\le t)}$).",
        out,
    )
    if n:
        out = out2
        edits += n

    # 表内/无句点：`$S (\le t) 1$ \bowtie $S (\le t) 2$`（| 可能被误吞进 $）
    out2, n = sub(
        r"\$S\s*\(\\le t\)\s*1\$\s*\\bowtie\s*\$S\s*\(\\le t\)\s*2\s*\|?\s*\$",
        r"$S_{1}^{(\\le t)} \\bowtie S_{2}^{(\\le t)}$",
        out,
    )
    if n:
        out = out2
        edits += n

    # 已修好但仍被拆开的两段
    out2, n = sub(
        r"\$S_\{1\}\^\{\(\\le t\)\}\$\s*\\bowtie\s*\$S_\{2\}\^\{\(\\le t\)\}\$",
        r"$S_{1}^{(\\le t)} \\bowtie S_{2}^{(\\le t)}$",
        out,
    )
    if n:
        out = out2
        edits += n

    # 原始无 $：S ( ≤ t ) 1 \bowtie S ( ≤ t ) 2
    out2, n = sub(
        r"(?<![\$A-Za-z])S\s*\(\s*(?:≤|\\le)\s*t\s*\)\s*1\s*\\bowtie\s*"
        r"S\s*\(\s*(?:≤|\\le)\s*t\s*\)\s*2(?!\})",
        r"$S_{1}^{(\\le t)} \\bowtie S_{2}^{(\\le t)}$",
        out,
    )
    if n:
        out = out2
        edits += n

    # assert T ( t ) i,g ≤ t（含 safe 把 g≤t 拆走的残片）
    out2, n = sub(
        r"T\s*\(\s*t\s*\)\s*i\s*,\s*(?:\$)?g\s*(?:≤|\\le)\s*t\$?",
        r"$T_{i,g}^{(t)} \\le t$",
        out,
    )
    if n:
        out = out2
        edits += n

    # Brier：去掉 Docling 污染的 \text{wein out...}，对照 PDF 保留公式本体
    out2, n = sub(
        r"\$\$\s*\\text\s*\{[^}]*wein[^}]*\}[^$]*?"
        r"\\text\s*\{\s*Brier\s*\}\s*\\,\s*=\s*\\,\s*"
        r"\\frac\s*\{\s*1\s*\}\s*\{\s*n\s*\}\s*"
        r"\\sum\s*_\s*\{\s*i\s*=\s*1\s*\}\s*\^\s*\{\s*n\s*\}\s*"
        r"\(\s*y\s*_\s*\{\s*i\s*\}\s*-\s*\\hat\s*\{\s*p\s*\}\s*_\s*\{\s*i\s*\}\s*\)\s*\^\s*\{\s*2\s*\}\s*\.?\s*\$\$",
        r"$$\\mathrm{Brier} = \\frac{1}{n} \\sum_{i=1}^{n} (y_i - \\hat{p}_i)^2.$$",
        out,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if n:
        out = out2
        edits += n

    # F1 / Prec / Rec 定义（Docling 把词拆开并弄乱结构）
    out2, n = sub(
        r"\$\$\s*F\s*1\s*&?\s*=\s*\\frac\s*\{\s*2\s*\\Pr\s*e\s*c\s*\{\s*R\s*e\s*c\s*\}\s*\}"
        r"\s*\{\s*\\Pr\s*e\s*c\s*\{\s*\+\s*R\s*e\s*c\s*\}\s*\}\s*,\s*"
        r"\\quad\s*\\Pr\s*e\s*c\s*\{\s*=\s*\\frac\s*\{\s*T\s*P\s*\}\s*\{\s*T\s*P\s*\+\s*F\s*P\s*\}\s*\}\s*,\s*"
        r"\\quad\s*R\s*e\s*c\s*=\s*\\frac\s*\{\s*T\s*P\s*\}\s*\{\s*T\s*P\s*\+\s*F\s*N\s*\}\s*\.?\s*\\\\?\s*\$\$",
        r"$$F1 = \\frac{2 \\cdot \\mathrm{Prec} \\cdot \\mathrm{Rec}}{\\mathrm{Prec} + \\mathrm{Rec}}, "
        r"\\quad \\mathrm{Prec} = \\frac{TP}{TP + FP}, "
        r"\\quad \\mathrm{Rec} = \\frac{TP}{TP + FN}.$$",
        out,
        flags=re.DOTALL,
    )
    if n:
        out = out2
        edits += n

    # 通用：display/inline 内拆开的指标词（漏网）
    for a, b in (
        (r"\bF\s+1\b", "F1"),
        (r"\\Pr\s+e\s+c\b", r"\\mathrm{Prec}"),
        (r"\bPr\s+e\s+c\b", r"\\mathrm{Prec}"),
        (r"\bR\s+e\s+c\b", r"\\mathrm{Rec}"),
        (r"\bT\s+P\b", "TP"),
        (r"\bF\s+P\b", "FP"),
        (r"\bF\s+N\b", "FN"),
    ):
        out2, n = sub(a, b, out)
        if n:
            out = out2
            edits += n

    return out, edits


def _repair_chunk(chunk: str, *, wrap_dollars: bool) -> tuple[str, int]:
    """在单一文本块内修复；wrap_dollars=False 表示已在 $...$ 内。"""
    edits = 0
    out = chunk

    def wrap(body: str) -> str:
        return f"${body}$" if wrap_dollars else body

    def repl_xti(m: re.Match[str]) -> str:
        return wrap(f"{m.group(1)}_{{{m.group(3)}}}^{{({m.group(2)})}}")

    def repl_xti_comma(m: re.Match[str]) -> str:
        return wrap(
            f"{m.group(1)}_{{{m.group(3)},{m.group(4)}}}^{{({m.group(2)})}}"
        )

    def repl_rti(m: re.Match[str]) -> str:
        return wrap(f"{m.group(1)}_{{{m.group(3)}}}^{{(\\le {m.group(2)})}}")

    def repl_ri(m: re.Match[str]) -> str:
        return wrap(f"{m.group(1)}_{{{m.group(2)}}}")

    def repl_tsub(m: re.Match[str]) -> str:
        return wrap(f"{m.group(1)}_{{{m.group(2)}}}")

    def repl_func(m: re.Match[str]) -> str:
        return wrap(f"{m.group(1)}({m.group(2)})")

    def repl_fsup(m: re.Match[str]) -> str:
        return wrap(r"f^{(t)}")

    out2, n = _RTI.subn(repl_rti, out)
    if n:
        out = out2
        edits += n

    out2, n = _XTI_COMMA.subn(repl_xti_comma, out)
    if n:
        out = out2
        edits += n

    out2, n = _XTI.subn(repl_xti, out)
    if n:
        out = out2
        edits += n

    out2, n = _RI.subn(repl_ri, out)
    if 0 < n <= 40:
        out = out2
        edits += n

    out2, n = _T_SUB.subn(repl_tsub, out)
    if 0 < n <= 40:
        out = out2
        edits += n

    out2, n = _F_SUP.subn(repl_fsup, out)
    if n:
        out = out2
        edits += n

    out2, n = _FUNC_T.subn(repl_func, out)
    if 0 < n <= 50:
        out = out2
        edits += n

    return out, edits


def _iter_segments(md: str) -> list[tuple[str, bool]]:
    """切成 (segment, is_math)。display/inline 都标为 math。"""
    parts: list[tuple[str, bool]] = []
    i = 0
    n = len(md)
    while i < n:
        if md.startswith("$$", i):
            j = md.find("$$", i + 2)
            if j < 0:
                parts.append((md[i:], False))
                break
            parts.append((md[i : j + 2], True))
            i = j + 2
            continue
        if md[i] == "$":
            j = md.find("$", i + 1)
            if j < 0:
                parts.append((md[i:], False))
                break
            parts.append((md[i : j + 1], True))
            i = j + 1
            continue
        j = i
        while j < n and md[j] != "$":
            j += 1
        parts.append((md[i:j], False))
        i = j
    return parts


def _cleanup_after_geometry(text: str) -> tuple[str, int]:
    """无歧义收尾：HTML 实体、公式尾标点外移。"""
    edits = 0
    out = text
    for a, b in (("&gt;", ">"), ("&lt;", "<"), ("&amp;", "&")):
        if a in out:
            c = out.count(a)
            out = out.replace(a, b)
            edits += c
    # $phi .$ / $R_i^{(\le t)} .$ → 标点移出（要求空白，避免动 $0.5$）
    # 绝不匹配 $$...$$：开闭 $ 两侧不能再贴着 $
    out2, n = re.subn(
        r"(?<!\$)\$([^$\n]+?)\s+([.,;:])\s*\$(?!\$)",
        r"$\1$\2",
        out,
    )
    if n:
        out = out2
        edits += n
    return out, edits


def repair_detached_scripts_in_text(text: str, chars: list[GeoChar]) -> tuple[str, int]:
    """极保守几何/结构修复。

    - 先整段高置信短语（集合定义等）
    - 再按行：表格行跳过上下标猜测；其余按 $ 分段修复
    """
    if not chars:
        return text, 0

    sizes = [c.size for c in chars if c.char.strip()]
    if not sizes:
        return text, 0
    median = sorted(sizes)[len(sizes) // 2]
    small = [c for c in chars if c.size < median * 0.85]
    if len(small) < 3:
        return text, 0

    from app.utils.md_postprocess import _is_md_table_line, _repair_table_line_math

    total = 0
    text, n = _repair_high_confidence_phrases(text)
    total += n

    out_lines: list[str] = []
    for line in text.splitlines(keepends=True):
        core, nl = line, ""
        if line.endswith("\n"):
            core, nl = line[:-1], "\n"
        if _is_md_table_line(core):
            # 表格：不再做 R i / x(t)i 猜测，只做表格安全规范化
            fixed = _repair_table_line_math(core)
            if fixed != core:
                total += 1
            out_lines.append(fixed + nl)
            continue

        out_parts: list[str] = []
        for seg, is_math in _iter_segments(core):
            if is_math:
                if seg.startswith("$$") and seg.endswith("$$") and len(seg) >= 4:
                    inner, n = _repair_chunk(seg[2:-2], wrap_dollars=False)
                    out_parts.append(f"$$\n{inner}\n$$")
                    total += n
                elif seg.startswith("$") and seg.endswith("$") and len(seg) >= 2:
                    inner, n = _repair_chunk(seg[1:-1], wrap_dollars=False)
                    out_parts.append(f"${inner}$")
                    total += n
                else:
                    out_parts.append(seg)
            else:
                fixed, n = _repair_chunk(seg, wrap_dollars=True)
                out_parts.append(fixed)
                total += n
        out_lines.append("".join(out_parts) + nl)

    text = "".join(out_lines)
    text, n = _cleanup_after_geometry(text)
    total += n
    return text, total


def apply_geometry_repair(md: str, pdf_path: Path) -> tuple[str, int]:
    """对全文做保守几何修复；返回 (text, n_edits)。"""
    try:
        import pymupdf
    except Exception:
        return md, 0

    try:
        doc = pymupdf.open(pdf_path)
        chars: list[GeoChar] = []
        for i in range(min(3, len(doc))):
            chars.extend(extract_page_chars(pdf_path, i))
        doc.close()
    except Exception:
        return md, 0

    return repair_detached_scripts_in_text(md, chars)
