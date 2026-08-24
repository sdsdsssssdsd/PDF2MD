# DeepSeek-OCR 2（可选增强）

Lean Balanced 路径下，Docling 公式 enrich 关闭，由 DeepSeek-OCR 2 Worker 做高置信 display 公式修复。

## 环境变量

| 变量 | 含义 |
|------|------|
| `PDF2MD_HF_HOME` / `HF_HOME` | Hugging Face 缓存目录 |
| `PDF2MD_DEEPSEEK_MODEL_DIR` | 本地权重目录（可选；否则用 Hub id `deepseek-ai/DeepSeek-OCR-2`） |
| `PDF2MD_DSOCR2_PYTHON` | 专用 venv 的 Python（建议 `transformers==4.46.3`） |
| `PDF2MD_BENCH_PDF` | 基准 PDF 路径（脚本用） |

## Worker

```bash
python -u scripts/deepseek_ocr_worker_server.py
```

主进程通过 `app/ocr/deepseek_worker_client.py` 以 localhost JSON-RPC 调用。

## 说明

- 默认不强制写回条数上限（`deepseek_max_writebacks_*=0`）。
- 单式 hard timeout 默认 30s；超时会 kill + restart Worker（最多一次）。
- Gate / Extractor / Writeback 仍要求高置信才落 Markdown。
