# Formula OCR（debug5.md）— 专用 Pix2Tex，不接 VLM

## 决策

- Primary: `pix2tex`（`Pix2TexRecognizer`）
- VLM fallback: **默认关闭**（`vlm_fallback_enabled=False`）
- OCR confidence ≠ validity；必须再过 Validator
- Recognizer **忽略 context**（禁止猜写 Recall/TPR）

## 安装（可选）

```bash
pip install "pix2tex>=0.1.2"
```

未安装时自动降级 `NullFormulaRecognizer`，recovery 失败并留下可见占位 + `formula_qa.json`。

## 文件

- `app/formula/pix2tex_recognizer.py`
- `app/formula/preprocess.py`（原图 / 2x / 对比度）
- `app/formula/recognizer.py`（`build_recognizer`）
- `app/formula/recovery.py`（bbox × 预处理变体 × OCR × validate）
