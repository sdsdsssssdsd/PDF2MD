# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from app.task_model import ConvertTask


def test_convert_task_has_id_and_message():
    t = ConvertTask(pdf_path=Path("sample.pdf"), message="queued")
    assert t.id.endswith("sample.pdf")
    assert t.message == "queued"
    assert t.formula_recognized is None
    assert t.formula_post_ok is None
    assert t.formula_total is None
