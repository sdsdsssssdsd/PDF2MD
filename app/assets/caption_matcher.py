"""Caption / figure-label 解析与邻近匹配。"""
from __future__ import annotations

import re
from dataclasses import dataclass


# Figure 1 / Fig. 1 / FIGURE S1 / Fig 2a 等
_CAPTION_HEAD = re.compile(
    r"^\s*"
    r"(?P<label>"
    r"(?:Figure|Figures|Fig\.?|FIGURE|Scheme|SCHEME|Algorithm|ALGORITHM)"
    r"\s*"
    r"(?P<num>S?\d+[A-Za-z]?)"
    r")"
    r"\s*[.:=：\-]?\s*"
    r"(?P<body>.*?)\s*$",
    re.IGNORECASE,
)

# caption / 正文中的子图标记
_SUB_LABEL = re.compile(
    r"(?:\(([a-z]|[A-Z]|[ivxlcdm]{1,4})\)|(?:^|[\s,;])([a-zA-Z])\))"
    r"|(?:\(([a-z]|[A-Z]|[ivxlcdm]{1,4})\))",
    re.IGNORECASE,
)

# 更稳的子图标号提取：(a) (b) (c) 或 (i)(ii)
_PAREN_LABEL = re.compile(
    r"\(([a-z]|[A-Z]|i{1,3}|iv|v|vi{0,3}|ix|x)\)",
    re.IGNORECASE,
)


@dataclass
class ParsedCaption:
    raw: str
    label: str  # "Fig. 1" 保持原文风格片段
    number_token: str  # "1" / "S1"
    body: str
    expected_sublabels: list[str]


def parse_caption_line(text: str) -> ParsedCaption | None:
    """若一行像 figure caption，则解析；否则 None。"""
    line = (text or "").replace("\ufeff", "").strip()
    if not line or line.startswith("!["):
        return None
    # 去掉加粗等简单 markdown
    plain = re.sub(r"^\*\*(.+?)\*\*\s*$", r"\1", line)
    plain = re.sub(r"^_(.+?)_\s*$", r"\1", plain)
    m = _CAPTION_HEAD.match(plain)
    if not m:
        return None
    label = m.group("label").strip()
    # 尽量保留原文大小写：从 plain 里切出 label 长度前缀
    # 使用匹配到的原文片段
    start = plain.lower().find(label.lower())
    if start >= 0:
        label = plain[start : start + len(label)]
    body = (m.group("body") or "").strip()
    subs = extract_subfigure_labels(plain)
    return ParsedCaption(
        raw=plain,
        label=label,
        number_token=m.group("num"),
        body=body,
        expected_sublabels=subs,
    )


def extract_subfigure_labels(text: str) -> list[str]:
    """按出现顺序提取 (a)(b)(c) / (i)(ii)，去重保序。"""
    found: list[str] = []
    for m in _PAREN_LABEL.finditer(text or ""):
        lab = m.group(1)
        key = lab.lower()
        if key not in {x.lower() for x in found}:
            found.append(lab.lower() if lab.isalpha() and len(lab) == 1 else lab.lower())
    return found


def normalize_subfigure_index(label: str) -> int | None:
    """a→1, b→2, i→1, ii→2, A→1。无法映射则 None。"""
    s = (label or "").strip().lower()
    if not s:
        return None
    roman = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10}
    if s in roman:
        return roman[s]
    if len(s) == 1 and "a" <= s <= "z":
        return ord(s) - ord("a") + 1
    if s.isdigit():
        return int(s)
    return None


def find_caption_near_lines(
    lines: list[str],
    image_line_idx: int,
    *,
    window: int = 4,
) -> ParsedCaption | None:
    """
    在图片行上下 window 行内寻找最近 caption。
    优先：紧邻上一行 → 下一行 → 再向外。
    """
    order: list[int] = []
    for d in range(1, window + 1):
        order.append(image_line_idx - d)
        order.append(image_line_idx + d)
    best: ParsedCaption | None = None
    best_dist = 10**9
    for i in order:
        if i < 0 or i >= len(lines):
            continue
        # 跳过其它图片行
        if re.match(r"^\s*!\[", lines[i]):
            continue
        parsed = parse_caption_line(lines[i])
        if not parsed:
            continue
        dist = abs(i - image_line_idx)
        if dist < best_dist:
            best = parsed
            best_dist = dist
    return best
