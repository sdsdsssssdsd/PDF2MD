# Formula Pipeline Phase 2（debug4.md）

## 闭环

```text
DETECTED → VALID
        → CORRUPTED → RECOVERY_PENDING → SUCCESS | FAILED
仅 RECOVERY_FAILED → fallback renderer
```

## 关键变更

1. `FormulaCorruptionDetector`（`corruption.py`）：spacing 剔除后低信息量 / `\quad` 刷屏 → CORRUPTED（语法合法也算）
2. `FormulaRecoveryManager`（`recovery.py`）：PDF bbox 三级 padding 裁剪 + Recognizer；无 PDF/OCR → FAILED
3. **禁止上下文猜写**标准 Recall/TPR 公式
4. fallback：`clean`（默认，MD 不写调试注释）/ `debug` / `strict`
5. 失败写入 `formula_failures` + `{stem}.formula_qa.json`
6. `FormulaReleaseGate`：`document_status=formula_incomplete`，不能标 fully-successful

## 测试

`tests/test_formula_recovery_phase2.py`

## 仍缺（有 OCR 后才能闭环成功）

接入真实 `FormulaRecognizer`（Pix2Tex / VLM / MinerU formula），否则 recovery attempt 会失败但状态机正确。
