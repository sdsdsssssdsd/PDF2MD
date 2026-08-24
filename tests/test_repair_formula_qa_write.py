# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from app.repair import RepairConfig, RepairPipeline


def test_formula_qa_written_even_when_all_valid(tmp_path: Path):
  raw = tmp_path / "doc.raw.md"
  raw.write_text(r"$$\alpha + \beta$$\n", encoding="utf-8")
  cfg = RepairConfig(keep_formulas=True, write_final_md=True, write_raw_md=True)
  pipe = RepairPipeline(cfg)

  fake_report = {
    "formula_count": 1,
    "validated": 1,
    "recovery_attempted_count": 0,
    "corrupted_formula_count": 0,
    "telemetry": {"ocr_calls": 0},
  }

  class _FakeReport:
    document_quality = None
    corrupted_formula_count = 0
    recovery_attempted_count = 0
    recovery_success_count = 0
    recovery_failed_count = 0
    suspected_unwrapped = 0
    writeback = {}

    def to_dict(self):
      return fake_report

  class _FakeResult:
    markdown = r"$$\alpha + \beta$$"
    report = _FakeReport()

  with patch("app.formula.FormulaPipeline") as fp_cls:
    fp_cls.return_value.process_markdown.return_value = _FakeResult()
    pipe.run(
      pdf_path=tmp_path / "doc.pdf",
      raw_markdown_path=raw,
      out_dir=tmp_path,
    )

  qa = tmp_path / "doc.formula_qa.json"
  assert qa.is_file()
  data = json.loads(qa.read_text(encoding="utf-8"))
  assert data["formula_count"] == 1
