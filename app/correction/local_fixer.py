"""本地确定性数学/格式修复（Phase A）。"""
from __future__ import annotations

import re

from app.correction.models import CorrectionPatch

_ARRAY_ENVS = ("array", "aligned", "alignedat", "cases", "gather", "gathered", "split")
_ENV_BLOCK = re.compile(
    r"\\begin\{(?P<env>"
    + "|".join(_ARRAY_ENVS)
    + r")\}(?P<body>.*?)\\end\{(?P=env)\}",
    re.DOTALL,
)
_BROKEN_ARRAY_BREAK = re.compile(
    r"(?<![\\])\\" + "\\[(?P<sp>1mm|\\d+(?:\\.\\d+)?(?:mm|pt|em|ex)?)\\]"
)
_BROKEN_ARRAY_BREAK_AFTER_BRACE = re.compile(
    r"\}\\" + "\\[(?P<sp>1mm|\\d+(?:\\.\\d+)?(?:mm|pt|em|ex)?)\\]"
)
_GAMMA_OCR = re.compile(r"(?<![\\A-Za-z])Gamma!(?=\\left\b)")
_O_SPACING = re.compile(r"(?<![A-Za-z\\])O!(?=\\left\b)")
_EQ_REF_LEFT = re.compile(
    r"(?:公式|式|Eq\.?|Equation|equation|见|由|式\s*\(|公式\s*\()\s*$",
    re.I,
)
_VAR_LEFT = re.compile(
    r"(?:若|当|如果|其中|即|对任意|令|设|记|为|满足|where|when|if|for|let)\s*$",
    re.I,
)
_VAR_RIGHT = re.compile(
    r"^\s*(?:为|是|满足|时|则|的|，|,|。|；|；|奇|偶|大于|小于|成立|表示|denotes|is|are|holds)",
    re.I,
)
_INLINE_VAR = re.compile(r"\((?P<var>[a-zA-Z])\)")


def _patch(
    issue_id: str,
    before: str,
    after: str,
    *,
    reason: str,
) -> CorrectionPatch:
    return CorrectionPatch(
        issue_id=issue_id,
        before=before,
        after=after,
        source="local",
        confidence=1.0,
        gate="accepted",
        reason=reason,
    )


def fix_array_line_breaks(text: str) -> tuple[str, list[CorrectionPatch]]:
    patches: list[CorrectionPatch] = []

    def fix_body(body: str) -> str:
        out = body

        def repl_brace(m: re.Match[str]) -> str:
            sp = m.group("sp")
            before = m.group(0)
            after = "}" + "\\\\[" + sp + "]"
            patches.append(_patch(f"ARRAY-{len(patches)+1:04d}", before, after, reason="array_row_break"))
            return after

        out = _BROKEN_ARRAY_BREAK_AFTER_BRACE.sub(repl_brace, out)

        def repl_line(m: re.Match[str]) -> str:
            sp = m.group("sp")
            before = m.group(0)
            after = "\\\\[" + sp + "]"
            patches.append(_patch(f"ARRAY-{len(patches)+1:04d}", before, after, reason="array_row_break"))
            return after

        out = _BROKEN_ARRAY_BREAK.sub(repl_line, out)
        return out

    def repl_env(m: re.Match[str]) -> str:
        env = m.group("env")
        body = m.group("body")
        fixed = fix_body(body)
        if fixed == body:
            return m.group(0)
        return f"\\begin{{{env}}}{fixed}\\end{{{env}}}"

    return _ENV_BLOCK.sub(repl_env, text), patches


def fix_gamma_and_spacing_commands(text: str) -> tuple[str, list[CorrectionPatch]]:
    patches: list[CorrectionPatch] = []

    def gamma(m: re.Match[str]) -> str:
        before = m.group(0)
        after = r"\Gamma\!\left"
        patches.append(_patch(f"GAMMA-{len(patches)+1:04d}", before, after, reason="missing_backslash_gamma"))
        return after

    def o_sp(m: re.Match[str]) -> str:
        before = m.group(0)
        after = r"O\!\left"
        patches.append(_patch(f"OCR-{len(patches)+1:04d}", before, after, reason="lost_spacing_command"))
        return after

    text = _GAMMA_OCR.sub(gamma, text)
    text = _O_SPACING.sub(o_sp, text)
    return text, patches


def fix_lost_inline_delimiters(text: str) -> tuple[str, list[CorrectionPatch]]:
    patches: list[CorrectionPatch] = []
    out: list[str] = []
    last = 0
    for m in _INLINE_VAR.finditer(text):
        out.append(text[last : m.start()])
        inner = m.group("var")
        left = text[max(0, m.start() - 24) : m.start()]
        right = text[m.end() : m.end() + 24]
        token = m.group(0)
        if _EQ_REF_LEFT.search(left):
            out.append(token)
        elif inner.isdigit():
            out.append(token)
        elif not (_VAR_LEFT.search(left) or _VAR_RIGHT.search(right)):
            out.append(token)
        else:
            after = f"${inner}$"
            patches.append(
                _patch(
                    f"INLINE-{len(patches)+1:04d}",
                    token,
                    after,
                    reason="lost_inline_math_delimiter",
                )
            )
            out.append(after)
        last = m.end()
    out.append(text[last:])
    return "".join(out), patches


def apply_local_fixes(text: str) -> tuple[str, list[CorrectionPatch]]:
    patches: list[CorrectionPatch] = []
    text, p1 = fix_array_line_breaks(text)
    patches.extend(p1)
    text, p2 = fix_gamma_and_spacing_commands(text)
    patches.extend(p2)
    text, p3 = fix_lost_inline_delimiters(text)
    patches.extend(p3)
    return text, patches
