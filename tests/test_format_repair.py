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
