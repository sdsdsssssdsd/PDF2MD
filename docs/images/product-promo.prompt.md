# Hero image brief — `product-promo.png`

The README hero is an **AI-generated overview diagram**, not a screenshot. It was drawn from the
text briefs below and refined once. Like every file in this folder it is documentation only —
nothing in the app loads it at runtime.

Provenance:

| | |
|---|---|
| Type | Text-to-image, flat vector infographic (no photo, no watermark) |
| Model | `auto-image` through a local image workbench (OpenAI-compatible endpoint) |
| Requested ratio | 16:9 (the endpoint returns 1672 × 941 px) |
| Round 1 | Brief 1 → two candidates; candidate B picked |
| Round 2 | Brief 2 (icon uniformity) with candidate B as the reference image → shipped file |

Content it is expected to match (if the framework changes, redraw it):

- five workflows: 日常识图 / API 高精度 / 快速自动 / 网页高保真 / 格式修正;
- the five layers: UI → Controller → QThread Worker → Service → engines & channels
  (Docling · MinerU · DeepSeek V4.1 Flash · Playwright);
- **real** progress: page/batch counters + streamed characters + stage weights, never a guess;
- the two stage strips (`Parse › Assets › Repair › Mirror`, `Render › Transcribe › Merge › Figures`);
- the format-repair gate (chunk → rewrite → integrity gate → rollback → delimiter normalisation);
- the on-disk layout (`paper_MD/`, `paper_API视觉/`, `paper_高保真/`, `paper_修复版.md`,
  `output/_vision_work/`, `.vision/`).

---

## Brief 1 — first draft

```text
为开源桌面软件 PDF2MD 画一张 GitHub README 首图：产品总览信息图（横幅，信息密集但排版整齐、网格对齐、专业产品手册质感）。

【左上：品牌区】
蓝色圆角文档图标，图标内白色字母 M 与向下箭头。大号深蓝标题「PDF2MD」，下方副标题「学术 PDF · 截图 → Markdown」，再下一行小号灰字「v0.1.0-alpha」，旁边一个蓝色胶囊标签「Windows 桌面工具 · PySide6」。

【第一行：五种模式，五张并列卡片，每张卡片左上角一个圆形序号】
① 日常识图 — 截图 → Markdown — 视觉 API · 流式进度
② API 高精度 — PDF 逐页 — 每批 6 页 · 校验合并
③ 快速自动 — Docling / MinerU — 本地解析 · 无需 Key
④ 网页高保真 — Playwright 浏览器 — 站点会话 · 备用通道
⑤ 格式修正 — 已有 .md / .txt — 分块改写 · 完整性门

【第二行左侧：分层架构，五条横向长条自上而下堆叠，右侧一条竖直箭头，条与条之间用小箭头连接】
界面层 MainWindow · 三工作区 · Command Bar
控制器层 识图 / 视觉 / 转换 / 修正（4 个 Controller）
工作线程层 QThread Worker · 主线程不阻塞
服务层 Service · 与 Qt 解耦
引擎与通道层 Docling · MinerU · DeepSeek V4.1 Flash · Playwright

【第二行右侧：真实进度条示意，画成桌面窗口底部的命令栏】
确定进度条推进到约 62%，下方一行百分比数字「62%」，右侧文字「API 高精度 · 第 7/12 页 · 已接收 1280 字」。下面小号注释「真实进度 = 页/批计数 · 流式字数 · 阶段权重；不猜、不回退」。

【第三行左侧：两条流水线，每行四到五个圆点阶段，圆点之间用小箭头】
快速自动：Parse › Assets › Repair › Mirror
API 高精度：Render › Transcribe › Merge › Figures

【第三行中间：格式修正门控，一条横向流程】
分块 8000 字 → DeepSeek 改写 → 完整性门 → 未通过则回滚该段 → 统一公式定界符 → 输出 xxx_修复版.md

【第三行右侧：落盘与续跑，画成紧凑的目录树】
paper_MD/
paper_API视觉/
paper_高保真/
paper_修复版.md
output/_vision_work/ 工作文件
.vision/ 缓存与校验 · 断点续跑

【底部：技术条，一个浅灰长条，图标加文字】
Python · PySide6 · Docling · MinerU · DeepSeek V4.1 Flash · Playwright ｜ 本地优先 · 断点续跑 · 主线程不阻塞

【硬性要求】
所有中文与英文必须书写正确、无错字、无乱码、无多余假字；不要出现重复文字块；不要水印、不要署名、不要二维码、不要手机或人物；不要深色主题、不要霓虹渐变；卡片边框浅灰蓝细线，重点色只用蓝色（少量橙色做强调）；标题与正文层级分明；整体像一张可读性很高的技术总览图。
```

## Brief 2 — refinement pass (reference image = round 1 candidate B)

```text
在这张图上只做一处「图标统一」修改，其余一切都保持完全不变。

把第 ②③④⑤ 四张卡片的图标改成与第 ① 张卡片同款结构：左边是输入物，中间一个向右箭头，右边是一个 MD 文档图标。

② API 高精度：PDF 文件图标 → 向右箭头 → MD 文档图标
③ 快速自动：文档加齿轮图标 → 向右箭头 → MD 文档图标
④ 网页高保真：浏览器窗口图标 → 向右箭头 → MD 文档图标
⑤ 格式修正：.md 文件与 .txt 文件两个图标 → 向右箭头 → MD 文档图标

五张卡片必须看起来是一套统一图标语言：同样的线宽、同样的尺寸、同样的水平对齐。

标题「PDF2MD」、副标题「学术 PDF · 截图 → Markdown」、版本「v0.1.0-alpha」、胶囊标签「Windows 桌面工具 · PySide6」、五张卡片的标题与副标题文字、分层架构五行、进度条窗口、处理流水线、格式修正门控、落盘与续跑、底部技术条，全部逐字保持原样，不得改动、不得增删文字、不得改变布局、配色与字号。所有中文与英文必须书写正确，无错字、无乱码。
```
