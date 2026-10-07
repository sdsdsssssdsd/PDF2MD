"""确定进度的共用件：把「真实已接收字数」映射成百分比，不猜总长度。

日常识图与格式修正都按 段/批 划分真实工作单元，段内再按流式接收字数推进。
"""
from __future__ import annotations

from typing import Callable

# 阶段进度回调：(阶段文本, 百分比)。百分比 None = 保持不变。
ProgressFn = Callable[[str, "int | None"], None]


class PipelineCancelled(RuntimeError):
    """用户在段/批之间或流式接收中取消。"""


# 模型阶段占总进度的比例，其余留给收尾（校验 / 写盘 / 归档）
MODEL_PERCENT = 90
# 流式曲线常数：已接收该字数时走完当前段的一半
STREAM_HALF_CHARS = 400


def stream_percent(base: float, span: float, chars: int) -> int:
    """chars → [base, base+span)：单调递增、永不越过本段区间。"""
    if chars <= 0:
        return int(base)
    frac = chars / (chars + STREAM_HALF_CHARS)
    return int(base + span * frac)


class StreamProgress:
    """一个段/批的流式进度：只前进、不倒退（重试后重新计数也不会回退）。"""

    def __init__(
        self,
        emit: ProgressFn,
        *,
        base: float,
        span: float,
        label: str,
    ) -> None:
        self._emit = emit
        self._base = base
        self._span = span
        self._label = label
        self._chars = 0
        self._percent = int(base)

    @property
    def chars(self) -> int:
        return self._chars

    def feed(self, total_chars: int) -> None:
        chars = max(self._chars, int(total_chars))
        self._chars = chars
        percent = stream_percent(self._base, self._span, chars)
        if percent <= self._percent:
            return
        self._percent = percent
        self._emit(f"{self._label} · 已接收 {chars:,} 字", percent)
