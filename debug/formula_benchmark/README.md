# 公式实验室 / Formula Benchmark

日常转换不要在这里调参。主窗口用 **快速 / 均衡 / 精细** 即可。

这个文件夹只做一件事：弄清 `2× / 3× / padding / contrast` 在**你自己的论文 PDF** 上有没有收益。

## 目录

| 路径 | 用途 |
| --- | --- |
| `corpus/` | 把要测的 PDF 拷进来（不会提交到 git） |
| `runs/` | 点「保存到 runs/」后的 JSON 结果 |
| `expected/` | 可选：手写 gold LaTeX，方便对照 |

## 怎么用

1. 启动 GUI → 工具栏 **公式实验室**
2. 选 PDF（或点 `corpus`）→ **扫描编号**
3. 选页码和 `Eq. (n)` → **预览裁图**（确认框到了公式，而不是页眉）
4. 把 `.raw.md` 里的原公式贴到 Parser 框；前文贴 `Recall can be calculated using Eq. (4):` 这类句子
5. 若你知道正确答案，填 Gold（否则只能看 GainEvaluator 的 accept，那不是人工正确率）
6. 勾选矩阵 → **Run benchmark**
7. 看表：耗时、对照、accept/reject
8. 保存 JSON，对比多篇论文后再决定要不要改默认 Balanced

## 怎么读结果

- **accept**：通过 Validator + Gain + 上下文词元否决，仍可能是错公式
- **gold yes**：和你填的正确答案对得上，这才接近「真恢复」
- **Pareto**：不要追最高准确率。若 2.5× 只比 2.0× 多 2% 命中却慢一倍，默认应保持 2.0×
- 完整矩阵 4×3×3 = **36 次 OCR**，首次还会加载 UniMERNet，只在你愿意等的时候勾

## 和主程序的关系

实验室调用同一套：

- `app/formula/benchmark.py` 矩阵引擎
- `UniMERNetRecognizer`（默认，GPU；忽略 context，不猜写）
- `RecoveryGainEvaluator` + `ContextTokenConsistency`

它**不会**修改主窗口当前的 Fast/Balanced/Quality。你看完数据，再决定要不要改 `app/formula/config.py` 里的 preset。
