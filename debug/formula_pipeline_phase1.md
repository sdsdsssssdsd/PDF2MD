# Formula Pipeline 重构进度（debug3.md）

## 目标

> 进入最终 Markdown 的公式必须尽可能可信；失败可追踪、可重新识别。

## 模块边界

| 模块 | 职责 | Phase |
|------|------|-------|
| Detector | 判断哪里可能是公式（评分，不猜 LaTeX） | 1 ✓ |
| Validator | 判断结果是否可信 | 1 ✓ |
| Normalizer | 只规范已验证 LaTeX；**NEVER guesses** | 1 ✓ |
| Fallback | 不可靠 → `formula-not-decoded` | 1 ✓ |
| Recognizer | Protocol + Null（OCR 占位） | 1 stub / 2–3 |
| Pipeline | 统一编排 | 1 ✓ |
| Document QA | 报告写入 repair.json `formula` | 1 ✓ |
| PDF bbox recovery | 二次识别 | 2 |
| Context validator | 语义一致性 | 4 |

## 代码位置

```
app/formula/
  types.py config.py detector.py validator.py
  normalizer.py fallback.py recognizer.py pipeline.py
```

接入：`RepairPipeline` 在 `postprocess_markdown` **之前**跑 FormulaPipeline（先降级污染，再 scrap）。

## 验收（Phase 1）

见 `tests/test_formula_pipeline_phase1.py` + `tests/fixtures/formulas/phase1_cases.md`。
