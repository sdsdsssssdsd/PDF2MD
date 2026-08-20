# PDF2MD

![PDF2MD 产品宣传](docs/images/product-promo.png)

Windows 桌面端工具：将**学术 PDF**转为 Markdown，引擎为 **Docling** / **MinerU**，解析后经保守的 **RepairPipeline** 修复。

> **状态：Alpha（v0.1.0-alpha）**  
> 行内公式与复杂版面仍可能需要人工核对，请将输出视为草稿。

开源协议：**Apache License 2.0**（见 `LICENSE`、`NOTICE`）。

## 效果示例

同一段学术正文：**转化前 PDF** vs **转化后 Markdown**。

**转化前 · PDF**

![转化前 PDF](docs/images/demo-01-pdf-source.png)

**转化后 · Markdown（.md）**

![转化后 Markdown](docs/images/demo-02-markdown-result.png)

## 当前能力

- 拖放 / 批量 PDF（支持中文路径）
- Docling（默认）/ MinerU / 自动
- 可指定**导出目录**（可选每篇独立子文件夹）
- 解析只写 `*.raw.md`，再经 RepairPipeline 得到 `*.md`（可选 `*.repair.json`）
- 安全 Unicode / 小数清理；保守 PDF 几何修复；表格行避免 `$` 拆坏 `|`

## 路线图（尚未实现）

- 更强公式质量检测 / 置信度报告
- 本地 olmOCR（Ollama）视觉回退
- DeepSeek 多证据融合
- 更完整的表格结构修复

请勿将 Roadmap 中的能力当作本 Alpha 已交付功能。

## 快速开始

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install docling
python run_gui.py
```

也可双击 `run_gui.bat`；会顺带生成带桌面封面图标的 `PDF2MD.lnk`，可固定到任务栏或复制到桌面。

国内网络（**可选**，默认不启用）：

```bat
set HF_ENDPOINT=https://hf-mirror.com
set MINERU_MODEL_SOURCE=modelscope
```

更完整说明见 [README.md](README.md)。

## 注意

- 不要提交个人 PDF、模型权重、`.cache`、密钥
- GPU 需自行安装对应 CUDA 版 PyTorch
