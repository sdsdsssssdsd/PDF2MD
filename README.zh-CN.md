# PDF2MD

![PDF2MD 产品宣传](docs/images/product-promo.png)

Windows 桌面端：**学术 PDF / 截图 → Markdown**。五种互不替代的工作流：

| # | 模式 | 输入 | 谁写 Markdown |
|---|------|------|----------------|
| 1 | **日常识图** | 截图 | DeepSeek Vision API（一次输出） |
| 2 | **API 高精度** | PDF 整页 | DeepSeek Vision API（识别 + 格式一次完成） |
| 3 | **快速自动** | PDF | Docling / MinerU + 本地公式恢复 |
| 4 | **网页高保真** | PDF 整页 | DeepSeek **网页**识图（Playwright） |
| 5 | **格式修正** | 已有 `.md` / `.txt` | DeepSeek Chat API（整篇修格式） |

**1 / 2 / 4** 要求 DeepSeek **第一次**就输出规范 Markdown（行内 `$...$`、多行 `$$`、不插 `---`）。**不会**在识别后再打一次 API 做后处理。

**5** 是独立工具：把已经转坏的 Markdown 整篇交给 DeepSeek，保存为 `原名_修复版.md`。

**3** 走本地引擎，**不需要** DeepSeek API Key。

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

## 如何选择

| | **日常识图** | **API 高精度** | **快速自动** | **网页高保真** | **格式修正** |
|---|---|---|---|---|---|
| **输入** | 截图 / 粘贴 | PDF | PDF | PDF | 已有 Markdown |
| **引擎** | Vision API | Vision API | Docling / MinerU | 网页 + Playwright | Chat API |
| **需要 Key** | 是 | 是 | 否 | 否（网页登录） | 是 |
| **输出** | 预览或 `日常识图/` | `<名>_API视觉/` | `<名>/` | `<名>_高保真/` | 旁路 `*_修复版.md` |
| **耗时** | 秒～分钟 | 分钟级 | 秒～分钟 | 分钟～小时 | 秒～分钟 |
| **适用** | 笔记、幻灯、手机图 | 官方 API、不跑浏览器 | 批量论文、本地 GPU | 版式难、无 API 额度 | `$` / `$$` / `---` 坏掉 |

---

## 共用 Markdown 规则

Prompt 与后处理共同遵守：

```text
行内：$n$
行间：
$$
F(\lambda)\sim\cdots
$$
禁止自动插入 ---
「公式 (19)」保持编号引用
「若 (n) 为奇数」→「若 $n$ 为奇数」
```

- 表格行与 `![图](...)` 之间必须空一行（否则图片会被吃进表格）
- 行间公式必须写成**多行** `$$` 围栏（Typora / MathJax 才能稳定显示 `\tag{n}`）
- 主界面只留高频选项，诊断项收入「…」

---

## 各模式说明

### 1. 日常识图

粘贴或拖入截图。DeepSeek Vision API 转录可见文字（公式、表格、图片标记）。可选归档到 `日常识图/`。

格式规则写在识图 Prompt 里，不再二次纠错。

### 2. API 高精度

渲染 PDF 页面，调用官方 Vision API。与网页模式同一套 Prompt：页标记、多行 `$$`、原图有编号才写 `\tag{n}`、禁止 `---`。

输出目录：`<Pdf名>_API视觉/`。

在 **设置 → DeepSeek API** 配置 Base URL、Key（`DEEPSEEK_API_KEY` 或系统凭据）、传输方式（自动 / Base64 / Files API）、超时。

没有 Key **不能**让模式 3 / 4 转换失败。模式 1 / 2 / 5 会提示先配置 Key。

### 3. 快速自动

| 模块 | 说明 |
|------|------|
| 解析 | Docling Lean：公式 enrich **关**，表格 FAST，图片 ×3 |
| 引擎 | Docling（默认）/ MinerU / 自动回退 |
| 公式 | 坏公式 → 本地 DeepSeek-OCR-2 Worker |
| 编号 | OCR **前**绑定印刷 Eq.(n) |
| 写回 | 仅高置信；多行 `$$`；有编号则 `\tag{n}` |
| Worker | 与 GUI 解耦的本机 daemon（`127.0.0.1:18765`） |

暖机参考：无坏公式约 4–11 秒；约 7 式恢复约 60–70 秒。冷加载模型可能一次性多花数分钟。

### 4. 网页高保真

| 模块 | 说明 |
|------|------|
| 渲染 | 整页 PNG（**3×**，`bookfigures/`） |
| 转录 | 每批 **10 页**，Playwright 有头浏览器 |
| Prompt | 与 API 模式相同的「一次写对格式」（`vision-transcribe-v2.2`） |
| 容错 | Level-0～4；「服务器繁忙」冷却约 10 分钟 |
| 断点 | `.vision/manifest.json` |
| 裁图 | 合并后 Docling 填入 `FIGURE` |

推荐 **Playwright 自动**（登录态在 `data/deepseek_profile/`）。自动化不可用时用剪贴板半自动。  
UI 校准：工具栏 **DeepSeek UI…** 或 `scripts/calibrate_deepseek_ui.py`。

浏览器转录结束后**不会**再打一轮 Vision API。

### 5. 格式修正

给「已经有一份 md，但格式很烂」用：

```text
坏.md  →  DeepSeek Chat API  →  坏_修复版.md
```

本地只负责：读文件 / 剪贴板、按安全边界分块（不切开 `$$` 与代码围栏）、调 API、拼接、保存。  
**不再**用正则判断「这是行内还是行间」。

必须配置 API Key。不润色正文，不改数字、公式编号和引用编号。

---

## 架构

```text
解析层
  ├── 日常截图     → DeepSeek Vision API
  ├── PDF API视觉  → DeepSeek Vision API
  ├── PDF 结构化   → Docling / MinerU → Asset → Formula
  └── PDF 网页视觉 → Playwright 打开 DeepSeek 网站
        ↓
规范化（仅结构化 / 网页合并后）
  ├── 图片写回
  └── SafeRepair（Unicode、表图空行、$$ 围栏）
        ↓
格式修正模式（仅已有 Markdown）
  └── DeepSeek 整篇修格式
        ↓
导出
```

### 快速自动

```text
PDF → Docling Lean → raw.md
    → AssetPipeline → Repair / FormulaPipeline（可选本地 OCR）
    → *.md
```

### 视觉（API 或网页）

```text
PDF → 整页渲染
    → DeepSeek（官方 API **或** 网站）一次输出内容 + 格式
    → 合并 / 清理 / 裁图
    → 最终 *.md
```

---

## 环境要求

- Windows 10/11
- Python **3.10+**（3.12 已测）
- **快速自动 + 公式**：建议 NVIDIA GPU
- **日常 / API / 格式修正**：DeepSeek API Key
- **网页高保真**：`playwright` + Chromium + 网页账号
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

### DeepSeek API（模式 1、2、5）

```bat
set DEEPSEEK_API_KEY=your-deepseek-api-key
```

或在 **设置 → DeepSeek API** 填写（写入凭据管理器，日志不打印 Key）。

### 网页高保真（Playwright）

```bash
pip install playwright
playwright install chromium
```

首次在弹出窗口登录 DeepSeek，之后复用 `data/deepseek_profile/`。

### 本地公式恢复（模式 3，可选）

```bat
set PDF2MD_HF_HOME=你的HF缓存目录
set PDF2MD_DEEPSEEK_MODEL_DIR=你的DeepSeek-OCR-2目录
set PDF2MD_DSOCR2_PYTHON=能加载模型的python.exe
```

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

1. 顶部选择五种模式之一
2. 设置导出目录
3. **日常识图**：粘贴 / 拖入图片
4. **API / 快速自动 / 网页**：拖入 PDF → **开始转换**
5. **格式修正**：粘贴或导入 `.md` → **修正格式**（需要 Key）
6. 完成后看 `*.md`；快速自动公式恢复另有 `*.formula_qa.json`

**网页模式**：转换中勿关 DeepSeek 浏览器；出现「服务器繁忙」会自动冷却约 10 分钟再续跑；右键可「仅重合并与裁图」。

---

## 项目结构

```text
PDF2MD/
├── app/
│   ├── engines/              # Docling / MinerU
│   ├── assets/               # 图片资产
│   ├── repair/               # RepairPipeline
│   ├── formula/              # 公式检测 / 恢复 / 写回
│   ├── ocr/                  # 本地 DeepSeek-OCR-2 Worker
│   ├── vision_api/           # 官方 HTTP 客户端
│   ├── deepseek_api/         # Chat 封装（格式修正）
│   ├── daily_vision/         # 日常识图
│   ├── format_repair/        # 第五模式：分块 + 整篇 API
│   ├── vision_transcribe/    # API / Playwright 视觉管线
│   ├── workers/
│   └── main_window.py
├── data/deepseek_templates/  # 网页模板（含「服务器繁忙」）
├── scripts/
├── tests/
├── docs/images/
└── run_gui.py
```

---

## 配置与环境变量

| 配置项 | 说明 |
|--------|------|
| 导出目录 | 主窗口 |
| DeepSeek API | 设置页：Base URL、Key、视觉模型、传输方式 |
| 图片质量 | 有图论文建议 **高 (×3)** |
| 视觉批次 | 默认 10 页 |
| 上传限流冷却 | 默认 600 秒 |

| 变量 | 用途 |
|------|------|
| `DEEPSEEK_API_KEY` | 官方 API（日常 / API 视觉 / 格式修正） |
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

CI：Windows × Python 3.10–3.12，含隐私扫描；不下载大模型、不连真实 DeepSeek。

常用脚本：`start_deepseek_ocr_daemon.py`、`calibrate_deepseek_ui.py`、`record_deepseek_dom.py`。

---

## 路线图

- 困难文档公式 canary 继续抬升
- 网页视觉批次与 ETA
- 可选登录后预热 OCR daemon
- 表格几何修复增强

**刻意冻结**：DeepSeek OCR prompt/token、Lean picture×3、coverage-first 首轮 OCR。

---

## 注意

- 勿提交个人 PDF、模型权重、`.cache`、密钥
- GPU / CUDA PyTorch 需自行安装
- 网页模式使用 DeepSeek **网站**，请遵守其条款
- 官方 API 的额度与计费以 DeepSeek 为准；Key 只留在本机
- 第三方引擎与模型各有许可（见 `NOTICE`）
