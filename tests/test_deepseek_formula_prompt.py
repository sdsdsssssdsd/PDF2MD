# -*- coding: utf-8 -*-
from unittest.mock import MagicMock

from app.ocr import PROMPT_FORMULA_LATEX
from app.ocr.deepseek_ocr2 import DeepSeekOCR2Recognizer
from app.ocr.deepseek_profiles import DeepSeekOCRProfile


def test_formula_mode_honors_explicit_prompt():
    rec = DeepSeekOCR2Recognizer(
        formula_profile=DeepSeekOCRProfile(
            name="t",
            base_size=1024,
            image_size=768,
            crop_mode=True,
            max_new_tokens=32,
            save_results=False,
            eval_mode=True,
            prompt=None,
        )
    )
    rec._ensure_loaded = MagicMock(return_value=0.0)  # type: ignore[method-assign]
    captured: dict = {}

    def _infer(tokenizer, prompt, **kwargs):
        captured["prompt"] = prompt
        return "x=1"

    model = MagicMock()
    model.infer = _infer
    model.generate = MagicMock()
    DeepSeekOCR2Recognizer._model = model
    DeepSeekOCR2Recognizer._tokenizer = MagicMock()

    from app.ocr import OCRMode
    from PIL import Image

    rec.recognize(Image.new("RGB", (8, 8)), mode=OCRMode.FORMULA, prompt=PROMPT_FORMULA_LATEX)
    assert "LaTeX only" in captured.get("prompt", "")
