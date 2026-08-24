import os
from pathlib import Path

from app.formula.recognizer import NullFormulaRecognizer
from app.ocr.deepseek_benchmark import (
    DeepSeekBenchmarkConfig,
    build_o018_cases,
    run_deepseek_benchmark,
)
from app.ocr.deepseek_ocr2 import FakeDeepSeekOCR2Recognizer
from app.ocr.extractor import FormulaFromDocumentOCRExtractor

md = r"""
Bias-variance:
$$E[(y-\hat{f})^2]=Bias^2+Var+\varepsilon$$
(1)
Recall:
$$Recall=\frac{TP}{TP+FN}$$
(4)
F1:
$$F1=2\times\frac{Precision\times Recall}{Precision+Recall}$$
(5)
$$TPR=\frac{TP}{TP+FN}$$
(6)
$$FPR=\frac{FP}{FP+TN}$$
(7)
"""

ex = FormulaFromDocumentOCRExtractor()
for n in ("1", "4", "5", "6", "7"):
    c = ex.extract(md, eq_number=n)
    print(n, "OK" if c else "FAIL", (c.text[:60] if c else ""))

pdfs = list(Path(os.environ.get("PDF2MD_BENCH_ROOT") or (ROOT / "input")).rglob("O-018_Abdo2025_Stacking_SHAP.pdf"))
pdf = pdfs[0]
fake = FakeDeepSeekOCR2Recognizer(
    {"page": md, "region": md, "formula": r"$$Recall=\frac{TP}{TP+FN}$$ (4)", "*": md}
)
payload = run_deepseek_benchmark(
    pdf,
    cfg=DeepSeekBenchmarkConfig(
        experiment_only=True,
        run_baseline=False,
        baseline_recognizer="null",
    ),
    cases=build_o018_cases(pdf),
    doc_recognizer=fake,
    formula_recognizer=NullFormulaRecognizer(),
    progress=print,
)
print("summary", payload["summary"]["by_mode"])
print("cache", payload["summary"]["telemetry"])
print("out", payload["output_path"])
