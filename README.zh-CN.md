# PDF2MD

![PDF2MD 产品宣传](docs/images/product-promo.png)

Windows 桌面端：**学术 PDF → Markdown**。提供两条互补路线：

1. **快速自动** — Lean Docling 结构化解析 + 本地 **DeepSeek-OCR-2** 公式恢复
2. **高保真视觉** — 整页渲染 + **DeepSeek 网页识图** 高保真转录

> **状态：Alpha（v0.1.0-alpha）**  
> 请将输出视为草稿；公式多或走视觉路线时务必抽查。

开源协议：**Apache License 2.0**（见 `LICENSE`、`NOTICE`）。

English: [README.md](README.md)

---

## 效果示例

**转化前 · PDF**

![转化前 PDF](docs/images/demo-01-pdf-source.png)

**转化后 · Markdown**（快速自动路线）

![转化后 Markdown](docs/images/demo-02-markdown-result.png)

---

## 如何选择工作流

| | **快速自动**（默认） | **高保真视觉** |
|---|---|---|
| **目标** | 快速得到可编辑的结构化 Markdown | 按页面视觉逐字转录，最大限度保留版式 |
| **引擎** | Docling / MinerU | DeepSeek **网页**识图模式（Playwright） |
| **公式** | 本地 DeepSeek-OCR-2 Worker（可选） | 模型读整页图，在转录稿中写 LaTeX |
| **图片** | AssetPipeline 语义命名与导出 | 转录稿 FIGURE 占位 + Docling 自动裁图 |
| **输出目录** | `output/<论文名>/` | `output/<论文名>_高保真/` |
| **典型耗时** | 无坏公式时数秒级 | 分钟～小时（每批 10 页，受浏览器限制） |
| **适用** | 大多数论文、批量转换 | 版式复杂、要求严格对齐原稿 |

两条路线**相互独立**。高保真视觉**不依赖**本地 OCR daemon。

---

## 快速自动：当前能力

| 模块 | 说明 |
|------|------|
| 解析 | Docling Lean：公式 enrich **关**，表格 FAST，图片 ×3 |
| 引擎 | Docling（默认）/ MinerU / 自动回退 |
| 公式 | 坏公式 / `formula-not-decoded` → DeepSeek **公式裁剪 OCR** |
| 编号 | OCR **前**用 PDF 印刷编号绑定 Eq.(n)；OCR 不决定编号 |
| 写回 | 仅高置信；多行 `$$`；有编号则 `\tag{n}` |
| Worker | 与 GUI **解耦**的本机 daemon（`127.0.0.1:18765`），关 GUI 不杀进程 |
| 修复 | Unicode、表格/`$` 安全、表格与图片间强制空行 |

暖机参考：无公式 ~4–11s；约 7 式恢复 ~60–70s。冷加载 DeepSeek 可能一次性多花数分钟。

---

## 高保真视觉：当前能力

| 模块 | 说明 |
|------|------|
| 渲染 | PDF 逐页 → 带页码标签的 PNG（**3×**，`bookfigures/`） |
| 转录 | 每批 **10 页** → DeepSeek 识图对话（Playwright 有头浏览器） |
| Prompt | 禁止摘要/润色；行间公式多行 `$$`；`\tag{n}` 仅当原图有编号 |
| 自动化 | DOM 填词/上传/发送；截图模板 L2；录制流程回放 |
| 容错 | Level-0～4 恢复（重抽、单页重跑、子批次、全量重提） |
| 限流 | 附件「**服务器繁忙**」：DOM + 图模板双检；账户级冷却 **约 10 分钟** 后自动续跑 |
| 校验 | 页标记、截断检测、公式完整性、内容保留规则 |
| 合并 | 批次合并 + Markdown 清理（表图空行、公式围栏） |
| 裁图 | 合并后 Docling 自动填入 `FIGURE` 占位 |
| 断点续跑 | `.vision/manifest.json` + 各 batch 目录 |

**浏览器模式**

- **Playwright 自动**（推荐）：子进程隔离，登录态保存在 `data/deepseek_profile/`
- **剪贴板半自动**：自动化不可用时手动粘贴

**UI 校准**：工具栏 **DeepSeek UI…**，或运行 `scripts/calibrate_deepseek_ui.py`（模板在 `data/deepseek_templates/`）。

---

## 架构

### 快速自动（Lean Balanced）

```text
PDF
 → Docling（Lean）
 → raw.md + 图
 → AssetPipeline
 → Repair / FormulaPipeline
      → Identity 绑号
      → DeepSeek Worker（coverage-first）
      → Gate（强上下文冲突硬否决）
      → 受控写回
 → *.md + *.formula_qa.json
```

### 高保真视觉

```text
PDF
 → 整页渲染（3× + 页标签）
 → VisionPipeline（按批）
      → Playwright：新对话 → 识图模式 → Prompt + 上传
      → 等待回答 → 抽取 Markdown
      → 校验 / 失败恢复
 → 合并 + 清理
 → Docling 裁图写回
 → 最终 *.md
```

**共用导出硬规则**（代码强制）：

- 表格行与 `![图](...)` 之间至少空一行
- 行间公式写成多行 `$$` 围栏
- 主界面选项行精简，诊断项收入「…」

---

## 环境要求

- Windows 10/11
- Python **3.10+**（3.12 已测）
- **快速自动 + 公式**：建议 NVIDIA GPU + CUDA PyTorch
- **高保真视觉**：`playwright` + Chromium；需 DeepSeek 网页账号登录
- 引擎需单独安装：`docling`、可选 `mineru`

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

### 高保真视觉（Playwright）

```bash
pip install playwright
playwright install chromium
```

首次运行：在弹出的浏览器中登录 DeepSeek，之后复用 `data/deepseek_profile/`。

### 公式恢复（快速自动，推荐）

```bat
set PDF2MD_HF_HOME=你的HF缓存目录
set PDF2MD_DEEPSEEK_MODEL_DIR=你的DeepSeek-OCR-2目录
set PDF2MD_DSOCR2_PYTHON=能加载模型的python.exe
```

可选预热 daemon：

```bash
python scripts/start_deepseek_ocr_daemon.py --warmup
```

国内镜像（可选）：

```bat
set HF_ENDPOINT=https://hf-mirror.com
set MINERU_MODEL_SOURCE=modelscope
```

详见 [`.env.example`](.env.example)。

---

## 使用提示

1. 顶部选择 **快速自动** 或 **高保真视觉**
2. 设置导出目录，拖入 PDF，点 **开始转换**
3. **快速自动**：需要公式时开启 DeepSeek 相关选项；完成后看 `*.md` 与 `*.formula_qa.json`
4. **高保真视觉**：输出在 `*_高保真/`；关注流水线阶段面板；勿关 DeepSeek 浏览器窗口
5. 上传出现 **服务器繁忙** 时程序会自动暂停约 10 分钟再续跑（刷新无效，属账户级限流）
6. 右键任务可 **仅重合并与裁图**（不重跑浏览器）

---

## 项目结构

```text
PDF2MD/
├── app/
│   ├── engines/              # Docling / MinerU
│   ├── assets/               # 图片资产管线
│   ├── repair/               # RepairPipeline
│   ├── formula/              # 公式检测 / 恢复 / 写回
│   ├── ocr/                  # DeepSeek-OCR-2 Worker 客户端
│   ├── vision_transcribe/    # 高保真视觉全流程 + Playwright
│   ├── workers/              # 后台 QThread
│   └── main_window.py
├── data/
│   ├── deepseek_ui.json
│   └── deepseek_templates/   # 截图模板（发送键、重试、服务器繁忙等）
├── scripts/
├── tests/
├── docs/images/
├── debug/formula_benchmark/
├── .cursor/rules/
└── run_gui.py
```

---

## 配置与环境变量

| 配置项 | 说明 |
|--------|------|
| 导出目录 | 主窗口 |
| 图片质量 | 有图论文建议 **高 (×3)** |
| 视觉批次大小 | 默认 10 页 |
| 上传限流冷却 | 默认 600 秒 |

| 变量 | 用途 |
|------|------|
| `PDF2MD_HF_HOME` | HuggingFace 缓存 |
| `PDF2MD_DEEPSEEK_MODEL_DIR` | DeepSeek-OCR-2 权重 |
| `PDF2MD_DSOCR2_PYTHON` | 能加载 OCR 模型的 Python |
| `PDF2MD_DOCLING_ARTIFACTS` | Docling artifacts |
| `DEEPSEEK_WORKER_IDLE_UNLOAD_SECONDS` | Worker 空闲卸模型（默认 3600） |
| `HF_ENDPOINT` / `MINERU_MODEL_SOURCE` | 国内镜像（可选） |

---

## 开发

```bash
pip install -e ".[dev]"
python -m compileall app
python scripts/check_github_submit_privacy.py
pytest
```

CI：Windows × Python 3.10–3.12，不下载大模型、不连真实 DeepSeek。

常用脚本：`start_deepseek_ocr_daemon.py`、`calibrate_deepseek_ui.py`、`record_deepseek_dom.py`。

---

## 路线图

- 困难文档公式 canary 继续抬升
- 视觉模式批次与 ETA 优化
- 可选登录后后台预热 OCR daemon
- 表格几何修复增强

**刻意冻结**：DeepSeek OCR prompt/token、Lean picture×3、coverage-first 首轮 OCR。

---

## 注意

- 勿提交个人 PDF、模型权重、`.cache`、密钥
- GPU / CUDA PyTorch 需自行安装
- 高保真模式使用 DeepSeek **网站**，请遵守其服务条款
- 第三方引擎与模型各有许可（见 `NOTICE`）
