# 文档资源

根目录 [README.md](../README.md) / [README.zh-CN.md](../README.zh-CN.md) 引用的静态图片。

## `images/`

| 文件 | 用途 |
|------|------|
| `product-promo.png` | 仓库头图 / 社交预览 |
| `product-promo2.png` | 备用宣传图裁剪 |
| `demo-01-pdf-source.png` | README 效果对比 — PDF 原文 |
| `demo-02-markdown-result.png` | README 效果对比 — Markdown 结果 |

仅用于文档展示，**不参与程序运行**。请勿在此目录提交用户 PDF 或转换产物。

## 更新图片后发布

```bash
python scripts/publish_github_submit.py "docs: 更新图片"
```

同步脚本会把 `docs/images/` 镜像到 `github-submit`。
