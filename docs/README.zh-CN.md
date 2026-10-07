# 文档资源

根目录 [README.md](../README.md) / [README.zh-CN.md](../README.zh-CN.md) 引用的静态图片。

## `images/`

| 文件 | 用途 |
|------|------|
| `product-promo.png` | 仓库头图 / 社交预览 |
| `product-promo.prompt.md` | 头图的生成提示词留痕（AI 绘制，需随五模式框架同步更新） |
| `product-promo2.png` | 备用宣传图裁剪 |
| `demo-01-pdf-source.png` | README 效果对比 — PDF 原文 |
| `demo-02-markdown-result.png` | README 效果对比 — Markdown 结果 |
| `1.png` / `2.png` | 额外宣传 / 界面裁图（可选） |

仅用于文档展示，**不参与程序运行**。请勿在此目录提交用户 PDF 或转换产物。

## 更新图片

替换 `docs/images/` 下的 PNG 后提交即可。程序运行时不会读取这些文件。

头图 `product-promo.png` 是绘制出来的信息图，不是界面截图；它按
[`images/product-promo.prompt.md`](images/product-promo.prompt.md) 里的提示词生成。
框架变化时（模式、分层、进度模型、落盘布局）请同步改这份提示词并重画，避免图片与 README 表格不一致。
