# PDF2MD

![PDF2MD](docs/images/product-promo.png)

Windows 桌面端：把 **学术 PDF / 截图变成能在 Typora、VS Code 里改的 Markdown**。

它不是「整篇换一个大模型」。结构化转换会 **先便宜地解析**，**再测量哪里坏了**，然后 **只恢复失败的页或块**。视觉模式要求 DeepSeek **第一遍就写出规范 Markdown**。第五个模式修的是你已经有的 Markdown。

五种工作流互不替代：

| # | 模式 | 输入 | 谁写 Markdown | 需要 Key |
|---|------|------|----------------|----------|
| 1 | **日常识图** | 截图 | DeepSeek Vision API（一次输出） | 是 |
| 2 | **API 高精度** | PDF 整页 | DeepSeek Vision API（一次输出） | 是 |
| 3 | **快速自动** | PDF | Docling / MinerU + 本地公式恢复 | 否 |
| 4 | **网页高保真** | PDF 整页 | DeepSeek **网页**（Playwright） | 否（网页登录） |
| 5 | **格式修正** | 已有 `.md` / `.txt` | DeepSeek Chat API | 是 |

**1 / 2 / 4 不会**在识别后再打一轮 API 做「格式后处理」。**3** 走本地。没有 Key **不能**让模式 3 / 4 失败。

> **状态：Alpha（v0.1.0-alpha）。** 请把输出当草稿。公式、表格、图注在发表前要抽查。

开源协议：**Apache-2.0**（[`LICENSE`](LICENSE) · [`NOTICE`](NOTICE)）。  
English: [README.md](README.md)

---

## 转化前后

结构化路线（PDF 摘录 → Markdown）。

**PDF**

![转化前 PDF](docs/images/demo-01-pdf-source.png)

**Markdown**

![转化后 Markdown](docs/images/demo-02-markdown-result.png)

---

## 怎么选

| | **日常识图** | **API 高精度** | **快速自动** | **网页高保真** | **格式修正** |
|---|---|---|---|---|---|
| **适用** | 笔记、幻灯、手机图 | 官方 API、不跑浏览器 | 批量论文、本地 GPU | 版式难、没有 API 额度 | `$` / `$$` / `---` 坏掉 |
| **输出** | 预览或 `日常识图/` | `<名>_API视觉/` | `<名>/` | `<名>_高保真/` | 旁路 `*_修复版.md` |
| **耗时** | 秒～分钟 | 分钟级 | 秒～分钟 | 分钟～小时 | 秒～分钟 |

主窗口只留高频选项（导出图片 + Markdown；识别表格 + 参考文献）。诊断项放在 **…** 里。

---

## Markdown 契约

所有导出路径都应遵守。破坏这些规则就是 bug。

```text
行内：$n$
行间（禁止单行 $$...$$）：

$$
F(\lambda)\sim\cdots\tag{1}
$$

禁止自动插入 ---
保留「公式 (19)」这类印刷编号
```

- 表格行（`| ... |`）和图片（`![...](...)`）之间必须**空一行**，否则 CommonMark / Typora / GitHub 会把图吃进表格。
- 行间公式必须是**多行** `$$` 围栏，Typora（MathJax）才能稳定显示右侧 `\tag{n}`。

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

### DeepSeek API（模式 1、2、5）

```bat
set DEEPSEEK_API_KEY=your-deepseek-api-key
```

也可在 **设置 → DeepSeek API** 填写。Key 进 Windows 凭据管理器，日志不打印。

### 网页高保真（模式 4）

```bash
pip install playwright
playwright install chromium
```

首次在弹出的有头浏览器里登录。登录态在 `data/deepseek_profile/`（不进 git）。转换中不要关窗口。出现 **服务器繁忙** 时，程序大约冷却 10 分钟再续跑。

### 本地公式恢复（模式 3，可选）

用**独立**的 Python/CUDA 环境加载 DeepSeek-OCR-2，不要塞进 GUI 那个 Python。

```bat
set PDF2MD_HF_HOME=%CD%\.cache\hf
set PDF2MD_DEEPSEEK_MODEL_DIR=%CD%\models\DeepSeek-OCR-2
set PDF2MD_DSOCR2_PYTHON=%CD%\envs\dsocr2\Scripts\python.exe
python scripts/start_deepseek_ocr_daemon.py --warmup
```

国内镜像（可选）：

```bat
set HF_ENDPOINT=https://hf-mirror.com
set MINERU_MODEL_SOURCE=modelscope
```

详见 [`.env.example`](.env.example)。

---

## 结构化转换实际在做什么

模式 3 是一条运行时，不是「Docling 外面加几个按钮」：

```text
PDF
  → 便宜解析（默认 Docling；扫描件比例高时才倾向 MinerU）
  → DocumentIR（块、顺序、出处；不把 benchmark 分数写进 IR）
  → 统一 QA（VERIFIED / WARNINGS / INCOMPLETE / FAILED）
  → 只恢复失败的页/块（公式 / 表格 / 覆盖）
  → 再测一遍
  → Markdown + .pdf2md/{run.json, document.ir.json, qa.json}
```

新后端只作为 **Provider** 登记（能力、许可、隔离），**不会**变成第六个界面模式。PP-Structure、Docling VLM、Marker 等实验项默认 **关闭**，要通过质量、稳定性、资源、许可、可分发五门才能晋级。Benchmark 第一名不够；Marker 的 OpenRAIL-M **不能**当默认解析器。

网页视觉是带站点契约的实验 Provider。登录后的聊天界面地标全没了，会报 `INCOMPATIBLE_SITE`，而不是把 selector 换到天荒地老。

---

## 命令行（不启动 Qt）

```bash
python -m app doctor          # Python / GPU / Provider / 磁盘 / 许可
python -m app providers
python -m app inspect paper.pdf --json
python -m app convert paper.pdf --json          # 只出计划
python -m app convert paper.pdf --execute       # 真正转换
python -m app benchmark --help
python -m app smoke
```

不加 `--execute` 的 `convert` 只做画像和计划。完整转换需要本机 Docling（以及可选的 CUDA Worker）。

---

## 环境

- Windows 10/11
- Python **3.10+**（3.12 已测）
- 快速自动 + 公式：建议 NVIDIA GPU
- 模式 1 / 2 / 5：DeepSeek API Key
- 模式 4：Playwright Chromium + 网页账号
- 引擎自行安装：`docling`、可选 `mineru`、与驱动匹配的 CUDA `torch`

可选 extras（见 `pyproject.toml`）：`pdf2md[gui]`、`pdf2md[docling]`、`pdf2md[web]`、`pdf2md[paddle]`、`pdf2md[deepseek-ocr]`。大型 CUDA runtime **不要**装进 GUI 环境。

---

## 目录

```text
PDF2MD/
├── app/
│   ├── core/                 # JobRunner、DocumentIR、QA、Provider、CLI
│   ├── engines/              # Docling / MinerU
│   ├── assets/               # 图片命名
│   ├── formula/              # 本地公式恢复
│   ├── ocr/                  # DeepSeek-OCR-2 Worker
│   ├── vision_api/           # 官方 HTTP
│   ├── deepseek_api/         # Chat / Vision 客户端
│   ├── daily_vision/         # 模式 1
│   ├── format_repair/        # 模式 5
│   ├── vision_transcribe/    # 模式 2 / 4
│   ├── ui/                   # 控制器（Qt 只做线程桥）
│   └── main_window.py        # 视图
├── data/deepseek_templates/
├── scripts/
├── tests/
├── docs/images/
└── run_gui.py
```

---

## 配置

| 项 | 说明 |
|----|------|
| 导出目录 | 主窗口 |
| DeepSeek API | 设置：Base URL、Key、视觉模型、传输方式 |
| 图片质量 | 有图论文建议 **高 (×3)** |
| 视觉批次 | 默认 10 页 |
| 上传冷却 | 站点限流时默认 600 秒 |

| 变量 | 用途 |
|------|------|
| `DEEPSEEK_API_KEY` | 官方 API（模式 1、2、5） |
| `PDF2MD_PYTHON` | 子进程工具用的 Python |
| `PDF2MD_DOCLING_ARTIFACTS` | Docling artifacts |
| `PDF2MD_HF_HOME` | Hugging Face 缓存 |
| `PDF2MD_DEEPSEEK_MODEL_DIR` | 本地 DeepSeek-OCR-2 |
| `PDF2MD_DSOCR2_PYTHON` | 能加载 OCR 模型的 Python |
| `PDF2MD_PADDLE_PYTHON` | 独立 Paddle 环境（禁止塞进 GUI Python） |
| `DEEPSEEK_WORKER_IDLE_UNLOAD_SECONDS` | 空闲卸载 OCR 权重（默认 3600） |
| `HF_ENDPOINT` / `MINERU_MODEL_SOURCE` | 国内镜像（可选） |

---

## 开发

```bash
pip install -e ".[dev]"
python -m compileall app
python scripts/check_github_submit_privacy.py
pytest
```

CI：Windows × Python 3.10–3.12，含隐私扫描；不下载大模型、不跑 OmniDocBench、不连真实 DeepSeek。

常用脚本：`start_deepseek_ocr_daemon.py`、`calibrate_deepseek_ui.py`、`record_deepseek_dom.py`、`run-portable.ps1`（便携启动，不是安装包）。

对外 schema（DocumentIR、QA、`run.json`、Provider）按 **1.x 只加不改**；破坏性变更留给 2.0。

---

## 注意

- 不要提交个人 PDF、模型权重、`.cache`、浏览器登录态、密钥
- 网页模式使用 DeepSeek **网站**，请遵守其条款
- 官方 API 的额度与计费以 DeepSeek 为准；Key 只留在本机
- 第三方引擎与模型各有许可（见 [`NOTICE`](NOTICE)）
