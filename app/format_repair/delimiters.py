"""公式定界符归一：\\(...\\) → $...$，\\[...\\] → $$ 多行围栏。

为什么单独做一遍（不靠模型）：
- 这是**纯定界符**改写，`content_projection()` 对两种写法剥离结果相同，
  所以它不可能造成内容漂移，可以在完整性门之后无条件执行；
- 模型偶尔会在改写时顺手改动字符（触发完整性门回滚），此时整段修正被丢弃，
  但定界符归一仍然必须生效——否则会出现「前半段 \\( 后半段 $$」的混合文档。
"""
from __future__ import annotations

import re

# 代码区域先占位：围栏代码块 + 行内代码，绝不改写其中的反斜杠
_FENCE_BLOCK = re.compile(
    r"(?ms)^(?P<indent>[ \t]*)(?P<fence>`{3,}|~{3,})[^\n]*\n.*?^(?P=indent)(?P=fence)[ \t]*$"
)
_INLINE_CODE = re.compile(r"(`+[^`\n]*?`+)")
_PLACEHOLDER = "\ue000{}\ue001"

# \[ ... \] 独占多行
_DISPLAY_BLOCK = re.compile(
    r"(?m)^(?P<indent>[ \t]*)\\\[[ \t]*\n(?P<body>.*?)\n(?P=indent)\\\][ \t]*(?=\n|$)",
    re.DOTALL,
)
# \[ ... \] 独占一行
_DISPLAY_LINE = re.compile(r"(?m)^(?P<indent>[ \t]*)\\\[(?P<body>[^\n]*?)\\\][ \t]*(?=\n|$)")
# \[ ... \] 混在正文里
_DISPLAY_INLINE = re.compile(r"(?<!\\)\\\[(?P<body>[^\n]*?)(?<!\\)\\\]")
# \( ... \)
_INLINE_MATH = re.compile(r"(?<!\\)\\\((?P<body>[^\n]*?)(?<!\\)\\\)")
# 独占一行的 $$ ... $$ → 多行围栏（表格里不会误伤）
_DOLLAR_ONE_LINE = re.compile(r"(?m)^(?P<indent>[ \t]*)\$\$(?P<body>[^\n$]+?)\$\$[ \t]*(?=\n|$)")

_LATEX_LEFT = re.compile(r"(?<!\\)\\[\(\[]")


def _mask_code(text: str) -> tuple[str, list[str]]:
    spans: list[str] = []

    def _keep(m: re.Match[str]) -> str:
        spans.append(m.group(0))
        return _PLACEHOLDER.format(len(spans) - 1)

    masked = _FENCE_BLOCK.sub(_keep, text or "")
    masked = _INLINE_CODE.sub(_keep, masked)
    return masked, spans


def _unmask(text: str, spans: list[str]) -> str:
    for idx, chunk in enumerate(spans):
        text = text.replace(_PLACEHOLDER.format(idx), chunk)
    return text


def count_latex_delimiters(md: str) -> int:
    """剩余 \\( 或 \\[ 的个数（0 表示已统一为 $ / $$）。代码区域不计。"""
    masked, _spans = _mask_code(md)
    return len(_LATEX_LEFT.findall(masked))


def normalize_math_delimiters(md: str) -> str:
    """把 \\(...\\) 与 \\[...\\] 统一成 $...$ 与 $$ 围栏；幂等。"""
    masked, spans = _mask_code(md)
    out = _DISPLAY_BLOCK.sub(
        lambda m: f"{m.group('indent')}$$\n{m.group('body')}\n{m.group('indent')}$$",
        masked,
    )
    out = _DISPLAY_LINE.sub(
        lambda m: f"{m.group('indent')}$$\n{m.group('body')}\n{m.group('indent')}$$",
        out,
    )
    out = _DISPLAY_INLINE.sub(lambda m: f"$${m.group('body')}$$", out)
    out = _INLINE_MATH.sub(lambda m: f"${m.group('body')}$", out)
    out = _DOLLAR_ONE_LINE.sub(
        lambda m: f"{m.group('indent')}$$\n{m.group('body')}\n{m.group('indent')}$$",
        out,
    )
    return _unmask(out, spans)
