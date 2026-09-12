"""表格结构修复。"""
from __future__ import annotations

import re

_PIPE_TABLE_RE = re.compile(r"^\s*\|[^|]+\|")
_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")


def _pipe_cell_count(line: str) -> int:
    return max(1, line.count("|") - 1)


def _to_pipe(line: str) -> str:
    cells = [cell.strip() for cell in line.split("\t")]
    return "| " + " | ".join(cells) + " |"


def _separator_for(line: str) -> str:
    count = max(1, line.count("|") - 1)
    return "|" + " --- |" * count


def repair_table(md: str) -> str:
    text = (md or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.splitlines()
    out: list[str] = []
    in_code = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            in_code = not in_code
            out.append(line)
            i += 1
            continue
        if in_code:
            out.append(line)
            i += 1
            continue

        if "\t" in line:
            block = []
            while i < len(lines) and "\t" in lines[i]:
                block.append(_to_pipe(lines[i]))
                i += 1
            if block:
                out.append(block[0])
                if len(block) > 1:
                    out.append(_separator_for(block[0]))
                    out.extend(block[1:])
            continue

        if _PIPE_TABLE_RE.match(line):
            out.append(line)
            i += 1
            if i < len(lines):
                nxt = lines[i]
                if _PIPE_TABLE_RE.match(nxt) and not _SEPARATOR_RE.match(nxt):
                    out.append(_separator_for(line))
            continue

        out.append(line)
        i += 1
    return "\n".join(out) + "\n"
