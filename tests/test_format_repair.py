"""格式修正模式：分块 + DeepSeek 全文修复。"""
from __future__ import annotations

from pathlib import Path

from app.format_repair.chunker import split_markdown_chunks, unwrap_markdown_fence
from app.format_repair.file_io import read_text_file, repaired_sibling_path
from app.format_repair.models import RepairConfig
from app.format_repair.pipeline import repair_text
from app.format_repair.prompts import SYSTEM_PROMPT, build_repair_messages


def test_prompt_forbids_separator_and_requires_math_fences():
    assert "禁止添加 ---" in SYSTEM_PROMPT
    assert "$...$" in SYSTEM_PROMPT
    assert "$$" in SYSTEM_PROMPT
    msgs = build_repair_messages("若 (n) 为奇数")
    assert msgs[0]["role"] == "system"
    assert "若 (n) 为奇数" in msgs[1]["content"]


def test_unwrap_markdown_fence():
    raw = "```markdown\n# T\n```\n"
    assert unwrap_markdown_fence(raw).startswith("# T")


def test_chunker_keeps_display_math_together():
    body = "前言\n\n$$\n" + ("x+" * 200) + "y\n$$\n\n结尾\n"
    chunks = split_markdown_chunks(body, max_chars=80)
    joined = "".join(chunks)
    assert "$$" in joined
    assert joined.count("$$") % 2 == 0


def test_chunker_preserves_yaml_front_matter():
    src = "---\ntitle: x\n---\n\n正文很长。" + ("字" * 9000)
    chunks = split_markdown_chunks(src, max_chars=200)
    assert chunks[0].startswith("---")
    assert chunks[0].count("---") >= 2


def test_repair_text_rolls_back_content_drift():
    src = "公式 (19) 中 n=12。\n"

    def chat(md: str, part: int, total: int) -> str:
        return "公式 (19) 中 n=13。\n"

    result = repair_text(src, chat_fn=chat)
    assert "n=12" in result.output_text
    assert "n=13" not in result.output_text
    assert result.report["integrity"] == 0
    assert not result.ok
    assert result.warnings


def test_normalize_delimiters_converts_latex_forms():
    from app.format_repair.delimiters import normalize_math_delimiters

    src = (
        "行内 \\(a+b\\) 与 \\(c\\)。\n\n"
        "\\[\nE = mc^2 \\tag{1}\n\\]\n\n"
        "\\[F(x)=x\\]\n\n"
        "段中 \\[G(y)=y\\] 混排\n\n"
        "$$\nH = A^T A\n$$\n"
    )
    out = normalize_math_delimiters(src)
    assert "\\(a+b\\)" not in out and "$a+b$" in out
    assert "\\[" not in out and "\\]" not in out
    assert "$$\nE = mc^2 \\tag{1}\n$$" in out
    assert "$$\nF(x)=x\n$$" in out  # 独立一行的 \[...\] → 多行围栏
    assert "$$G(y)=y$$" in out  # 段落中间 → 就近转成 $$...$$
    assert "$$\nH = A^T A\n$$" in out


def test_normalize_delimiters_skips_code_and_linebreak():
    from app.format_repair.delimiters import (
        count_latex_delimiters,
        normalize_math_delimiters,
    )

    src = (
        "```python\n"
        "x = '\\\\(keep\\\\)'\n"
        "```\n\n"
        "行内代码 `\\(keep\\)` 不动，断行 `}\\\\[1mm]` 也不能改。\n\n"
        "真公式 \\(y=1\\)。\n"
    )
    out = normalize_math_delimiters(src)
    assert "\\(keep\\)" in out
    assert "}\\\\[1mm]" in out
    assert "$y=1$" in out
    assert count_latex_delimiters(out) == 0


def test_normalize_delimiters_is_projection_preserving_and_idempotent():
    from app.format_repair.delimiters import normalize_math_delimiters
    from app.format_repair.integrity import content_projection

    src = "前言 \\(\\alpha\\) 与\n\\[\n\\sum_i x_i = 1\n\\]\n结尾。\n"
    once = normalize_math_delimiters(src)
    assert content_projection(once) == content_projection(src)  # 不可能造成内容漂移
    assert normalize_math_delimiters(once) == once


def test_repair_normalizes_delimiters_even_when_chunk_rolled_back():
    """整段因漂移回滚时，公式定界符仍必须统一（曾出现前半 \\( 后半 $$ 的混合文档）。"""
    p1 = "第一段 \\(a+b\\) 与\n\\[\nE=1\n\\]\n"
    p2 = "第二段 \\(c+d\\) 与\n\\[\nF=2\n\\]\n"
    src = p1 + "\n" + p2
    calls = {"n": 0}

    def chat(md: str, part: int, total: int) -> str:
        calls["n"] += 1
        fixed = md.replace("\\(", "$").replace("\\)", "$")
        fixed = fixed.replace("\\[", "$$").replace("\\]", "$$")
        if part == 1:
            return fixed + "\n漂移字符。\n"  # 第一段：定界符改对了，但多写了内容 → 回滚
        return fixed

    result = repair_text(src, chat_fn=chat)
    assert result.ok, result.errors
    assert result.report["rolled_back"] == 1
    assert result.report["delimiters_normalized"] > 0
    # 全文再无 \( / \[ 残留
    from app.format_repair.delimiters import count_latex_delimiters

    assert count_latex_delimiters(result.output_text) == 0
    assert "漂移字符" not in result.output_text  # 回滚段正文保持原样
    assert any("回滚" in w for w in result.warnings)


def test_repair_retries_once_before_rollback():
    """第一次漂移 → 追加「只修格式」再要一次，能过门就不回滚。"""
    src = "第一段 \\(a+b\\)。\n"
    seen: list[str] = []

    def chat(md: str, part: int, total: int) -> str:
        seen.append(md)
        if len(seen) == 1:
            return "第一段 $a+b$。多了几个字。\n"  # 漂移 → 触发复检
        return "第一段 $a+b$。\n"

    result = repair_text(src, chat_fn=chat)
    assert len(seen) == 2
    assert "只修格式" in seen[1]
    assert result.ok
    assert result.report["rolled_back"] == 0
    assert "多了几个字" not in result.output_text


def test_typora_lint_ignores_linebreak_and_known_commands():
    from app.utils.typora_math_repair import find_undefined_math_commands

    body = "\\begin{pmatrix}a&b\\\\F&G\\end{pmatrix} \\langle x,y\\rangle \\longmapsto \\pi"
    assert find_undefined_math_commands(body) == []
    assert find_undefined_math_commands("\\Precisio_{c}") == ["Precisio"]


def test_repair_text_allows_math_wrap():
    src = "若 (n) 为奇数\n\n[\nF(\\lambda)\n]\n"
    fake = "若 $n$ 为奇数\n\n$$\nF(\\lambda)\n$$\n"

    def chat(md: str, part: int, total: int) -> str:
        return fake

    result = repair_text(src, chat_fn=chat)
    assert result.ok
    assert "$n$" in result.output_text
    assert "$$" in result.output_text
    assert result.report["chunks"] == 1


def test_repair_does_not_save_on_integrity_fail(tmp_path: Path):
    source = tmp_path / "chapter.md"
    source.write_text("公式 (19) 中 n=12。\n", encoding="utf-8")
    text, snap = read_text_file(source)
    out = repair_text(
        text,
        config=RepairConfig(),
        source_path=source,
        snapshot=snap,
        chat_fn=lambda md, part, total: "公式 (19) 中 n=13。\n",
    )
    assert not out.ok
    assert "saved_path" not in out.report
    assert list(tmp_path.glob("*修复版*")) == []


def test_protected_image_path_restored():
    src = "见图 ![x](images/a.png) 结束\n"

    def chat(md: str, part: int, total: int) -> str:
        return md.replace("images/a.png", "images/hack.png")

    result = repair_text(src, chat_fn=chat)
    assert "images/a.png" in result.output_text
    assert "hack.png" not in result.output_text


def test_file_snapshot_and_sibling_output(tmp_path: Path):
    source = tmp_path / "chapter3.md"
    source.write_bytes("\ufeff当\r\n\r\n$$x=1$$\r\n\r\n时成立。\r\n".encode("utf-8"))
    text, snap = read_text_file(source)
    out = repair_text(
        text,
        config=RepairConfig(),
        source_path=source,
        snapshot=snap,
        chat_fn=lambda md, part, total: "当 $x=1$ 时成立。\n",
    )
    saved = Path(out.report["saved_path"])
    assert saved.name.startswith("chapter3_修复版")
    raw = saved.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" in raw


def test_sibling_path_never_overwrites(tmp_path: Path):
    source = tmp_path / "a.md"
    source.write_text("x", encoding="utf-8")
    first = tmp_path / "a_修复版.md"
    first.write_text("y", encoding="utf-8")
    second = repaired_sibling_path(source)
    assert second.name == "a_修复版_2.md"
