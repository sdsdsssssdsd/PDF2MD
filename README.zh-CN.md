# PDF2MD

![PDF2MD 产品宣传](docs/images/product-promo.png)

Windows 桌面端：**学术 PDF → Markdown**。主路径为 **Lean Docling**（关公式 enrich）+ 本地 **DeepSeek-OCR-2** 公式恢复（常驻 Worker、受控写回）。

> **状态：Alpha（v0.1.0-alpha）**  
> 无坏公式的论文通常数秒完成；公式多的文档更久，仍建议人工抽查。请将输出视为草稿。

开源协议：**Apache License 2.0**（见 `LICENSE`、`NOTICE`）。

完整英文说明：[README.md](README.md)

---

## 效果示例

**转化前 · PDF**

![转化前 PDF](docs/images/demo-01-pdf-source.png)

**转化后 · Markdown**

![转化后 Markdown](docs/images/demo-02-markdown-result.png)

---

## 当前能力（相对旧版的大变化）

| 模块 | 现状 |
|------|------|
| 解析 | Docling Lean：公式 enrich **关**，表格 FAST，图片 ×3 |
| 公式 | 坏公式 / `formula-not-decoded` → DeepSeek **公式裁剪 OCR** |
| 编号 | OCR **前**用 PDF 印刷编号 / 定义句绑定 Eq.(n)；OCR 不决定编号 |
| 写回 | 仅高置信；多行 `$$`；有编号则 `\tag{n}` |
| Worker | 与 GUI **解耦**，本机 daemon 常驻，关 GUI 不卸模型进程 |
| 利用率 | OCR 后 CPU salvage（不增 GPU），提升 recovery yield |
| 导出 | AssetPipeline 语义图名、表格↔图片强制空行等硬规则 |

暖机参考（同数据典型论文量级）：无公式 ~4–11s；约 7 式恢复 ~60–70s。冷加载 DeepSeek 仍可能一次性多花数分钟。

---

## 架构（Lean Balanced）

```text
PDF
 → Docling（Lean）
 → raw.md + 图
 → AssetPipeline
 → Repair / FormulaPipeline
      → Identity 绑号
      → DeepSeek Worker（coverage-first，每式 OCR×1）
      → FormulaCrop 提取 + CPU Salvage
      → Gate（强上下文冲突硬否决）
      → 受控写回
 → *.md + *.formula_qa.json
```

原则：不根据正文**发明**公式；宁可少写回，也不 false accept；编号身份 ≠ 公式内容身份。

---

## 快速开始

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install docling
python run_gui.py
```

或双击 `run_gui.bat`。

### DeepSeek 公式恢复（推荐）

用环境变量指向本机权重与专用 Python（勿提交真实路径）：

```bat
set PDF2MD_HF_HOME=...
set PDF2MD_DEEPSEEK_MODEL_DIR=...
set PDF2MD_DSOCR2_PYTHON=...
```

可选：登录后 / 开发时预热 daemon：

```bash
python scripts/start_deepseek_ocr_daemon.py --warmup
```

国内镜像（可选）：

```bat
set HF_ENDPOINT=https://hf-mirror.com
```

---

## 使用提示

1. 需要恢复公式时打开 **DeepSeek limited production / 公式**相关选项  
2. 转换后看 `*.md`；公式任务再看 `*.formula_qa.json`（`recovery_yield`、`failure_class`、写回条数）  
3. 关 GUI 再开一般**不必**重新冷加载（Worker 仍在且未 idle unload）

---

## 开发

```bash
pip install -e ".[dev]"
python -m compileall app
pytest
```

---

## 路线图

- 困难文档 canary（多公式、低 yield）继续抬升  
- 可选「登录后后台预热」  
- GUI 预计等待时间（发现 N 个待恢复公式）  
- 更完整的表格几何修复  

**刻意冻结**：DeepSeek prompt/token、Lean picture×3、Watchdog 超时、coverage-first 首轮 OCR。

---

## 注意

- 不要提交个人 PDF、模型权重、`.cache`、密钥  
- GPU / CUDA PyTorch 需自行安装  
- 第三方引擎与模型各有许可条款（见 `NOTICE`）
