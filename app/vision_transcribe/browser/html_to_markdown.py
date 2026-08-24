"""轻量 HTML → Markdown（剪贴板 CF_HTML / assistant innerHTML 兜底）。"""
from __future__ import annotations

import html as html_lib
import re
from html.parser import HTMLParser


def _strip_cf_html(raw: str) -> str:
    """解析 Windows CF_HTML，取 Fragment 段。"""
    if not raw:
        return ""
    text = raw.replace("\r\n", "\n")
    start = end = None
    for line in text.split("\n")[:32]:
        if line.startswith("StartFragment:"):
            start = int(line.split(":", 1)[1].strip())
        elif line.startswith("EndFragment:"):
            end = int(line.split(":", 1)[1].strip())
    if start is not None and end is not None and end > start:
        return text[start:end]
    m = re.search(r"(?is)<html[\s\S]*</html>", text)
    return m.group(0) if m else text


class _HtmlToMd(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._out: list[str] = []
        self._table_rows: list[list[str]] = []
        self._row: list[str] = []
        self._in_cell = False
        self._cell_buf: list[str] = []
        self._in_pre = False
        self._pre_buf: list[str] = []
        self._list_depth = 0
        self._in_li = False

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(tag[1])
            self._out.append("\n\n" + "#" * level + " ")
        elif tag == "p":
            self._out.append("\n\n")
        elif tag == "br":
            self._out.append("\n")
        elif tag in ("strong", "b"):
            self._out.append("**")
        elif tag in ("em", "i"):
            self._out.append("*")
        elif tag == "code" and not self._in_pre:
            self._out.append("`")
        elif tag == "pre":
            self._in_pre = True
            self._pre_buf = []
        elif tag == "table":
            self._table_rows = []
        elif tag == "tr":
            self._row = []
        elif tag in ("td", "th"):
            self._in_cell = True
            self._cell_buf = []
        elif tag in ("ul", "ol"):
            self._list_depth += 1
            self._out.append("\n")
        elif tag == "li":
            self._in_li = True
            self._out.append("\n" + ("  " * max(0, self._list_depth - 1)) + "- ")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6", "p"):
            self._out.append("\n\n")
        elif tag in ("strong", "b"):
            self._out.append("**")
        elif tag in ("em", "i"):
            self._out.append("*")
        elif tag == "code" and not self._in_pre:
            self._out.append("`")
        elif tag == "pre":
            self._in_pre = False
            block = "".join(self._pre_buf).strip("\n")
            self._out.append(f"\n\n```\n{block}\n```\n\n")
        elif tag in ("td", "th"):
            self._in_cell = False
            cell = re.sub(r"\s+", " ", "".join(self._cell_buf)).strip()
            self._row.append(cell.replace("|", "\\|"))
        elif tag == "tr":
            if self._row:
                self._table_rows.append(self._row)
        elif tag == "table":
            if self._table_rows:
                lines = ["| " + " | ".join(r) + " |" for r in self._table_rows]
                if len(lines) > 1:
                    sep = "| " + " | ".join("---" for _ in self._table_rows[0]) + " |"
                    lines.insert(1, sep)
                self._out.append("\n\n" + "\n".join(lines) + "\n\n")
            self._table_rows = []
        elif tag in ("ul", "ol"):
            self._list_depth = max(0, self._list_depth - 1)
            self._out.append("\n")
        elif tag == "li":
            self._in_li = False

    def handle_data(self, data: str) -> None:
        if self._in_pre:
            self._pre_buf.append(data)
        elif self._in_cell:
            self._cell_buf.append(data)
        else:
            self._out.append(data)

    def get_markdown(self) -> str:
        text = "".join(self._out)
        text = html_lib.unescape(text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def html_fragment_to_markdown(html: str) -> str:
    fragment = _strip_cf_html(html or "")
    if not fragment.strip():
        return ""
    parser = _HtmlToMd()
    try:
        parser.feed(fragment)
        parser.close()
    except Exception:
        return ""
    return parser.get_markdown()
