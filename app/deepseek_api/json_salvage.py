"""截断 JSON 抢救：模型输出被 max_tokens 截断时，保留已完整生成的部分。

只补结构，不编内容：闭合未结束的字符串与括号；若尾部停在半截键值上，
回退到最后一个完整元素边界。
"""
from __future__ import annotations

import json
from typing import Any


def repair_truncated_json(text: str) -> dict[str, Any] | None:
    """把被截断的 JSON 文本补成合法对象；无法抢救时返回 None。"""
    raw = (text or "").strip()
    start = raw.find("{")
    if start < 0:
        return None
    raw = raw[start:]

    out: list[str] = []
    stack: list[str] = []
    in_string = False
    escaped = False
    last_safe = -1  # 最后一个元素边界逗号在 out 中的下标
    last_safe_depth = 0

    for ch in raw:
        if in_string:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            continue
        if ch in "{[":
            stack.append(ch)
            out.append(ch)
            continue
        if ch in "}]":
            if not stack:
                break
            stack.pop()
            out.append(ch)
            continue
        if ch == ",":
            out.append(ch)
            if stack:
                last_safe = len(out) - 1
                last_safe_depth = len(stack)
            continue
        out.append(ch)

    if in_string:
        if escaped:
            out.append("\\")  # 收尾的反斜杠先转义，避免吃掉闭合引号
        out.append('"')

    repaired = _load(_close(out, stack))
    if repaired is not None:
        return repaired

    if last_safe >= 0:
        repaired = _load(_close(out[:last_safe], stack[:last_safe_depth]))
        if repaired is not None:
            return repaired
    return None


def _close(parts: list[str], stack: list[str]) -> str:
    text = "".join(parts).rstrip()
    while text.endswith(","):
        text = text[:-1].rstrip()
    return text + "".join("}" if opener == "{" else "]" for opener in reversed(stack))


def _load(text: str) -> dict[str, Any] | None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None
