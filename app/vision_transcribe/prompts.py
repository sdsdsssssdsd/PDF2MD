"""Prompt 版本化（高保真转录，禁止二次 AI 润色语义）。"""
from __future__ import annotations

PROMPT_VERSION = "vision-transcribe-v2.1"

_PROMPT_BODY = """你正在执行 PDF → Markdown 高保真内容转录任务。

输入为连续 PDF 页面图片，页面顶部存在 PDF2MD PAGE XXXX 标识。

目标：
完整保留页面中所有实际内容，不得遗漏、概括、润色、纠错、改写或自行补充。
只允许将原内容转换为 Typora 可正确显示的 Markdown/LaTeX 表达。

规则：

1. 必须严格按照页面从低到高的顺序转换。

2. 每进入一个新页面时必须留下页面标记：
<!-- PDF2MD:PAGE:XXXX -->
并在该页全部内容输出完毕后立刻留下结束标记：
<!-- PDF2MD:PAGE_END:XXXX -->

3. 标题、正文、脚注、参考文献、图题、表题、编号、公式编号等实际内容必须完整保留。

4. 不要输出 PDF 本身的物理页码和重复性的页眉页脚。
但正文中的编号、章节号、公式号、引用号不得删除。

5. 行内数学公式使用：
$...$

6. 独立数学公式必须使用多行 $$ 围栏，禁止单行横排：
$$
...
$$

7. 公式编号以论文原图内容为准（不得为整齐而统一加号或去掉已有编号）：
- 若原式右侧/下方有 (1)、(2) 等编号，在 $$ 块内用 \\tag{{1}}、\\tag{{2}} 还原；
- 若原式无编号，禁止添加 \\tag{{}} 或行末 (n)。

8. 原文明确为多行对齐公式时可以使用 aligned。
不得为了排版美观自行改变公式结构。

9. 公式内容不得纠错、简化、补充或重新推导。

10. 下划线字符 _ 必须保留，不得错误转换为 *。

11. 表格转换为普通 Markdown 表格。
不要求还原原版视觉样式和合并单元格效果，
但所有表格文字、数字、公式、表头、单元格内容必须完整保留。
遇到合并单元格时可通过重复内容或普通单元格展开，禁止因为 Markdown 表格限制而遗漏内容。

12. 遇到需要保留的图、照片、曲线图、结构图、流程图等非文本视觉内容，不要自行描述代替原图。
禁止输出 example.com 或任何虚构图片 URL。
在正文对应位置留下：
<!-- PDF2MD:FIGURE:pXXXX:fYY -->

同一页面按从上到下、从左到右依次编号 f01、f02……

13. 章节标题必须写成 Markdown 标题（如 ## 1 Introduction、### 2.1 Title），不得把标题与正文粘在同一行。

14. 表格必须输出为标准 Markdown 表格（| 列 | 列 |），不得把表格压成一行纯文本。

15. 图片标题和图片说明仍作为普通正文完整转录，不能因为留下 Figure 标记而省略。

16. 不使用 --- 分隔符。

17. 不得输出：
“以下内容省略”
“同上”
“其余类似”
“内容如图”
或任何原页面不存在的总结性文字。

18. 不允许因为跨页而遗漏句子。
即使一个段落、公式或表格跨页，也必须继续完整转录。

19. 只输出转换后的 Markdown 内容，不要解释转换过程。
不要用 markdown 代码围栏包裹全文。

20. 本批次全部页面输出完毕后，必须在最后一行输出批次结束标记：
<!-- PDF2MD:BATCH_END:{batch_id:04d} -->

本批次为 PAGE {start:04d} 至 PAGE {end:04d}（批次编号 {batch_id}）。
输出必须包含该范围内每一页对应的 PAGE 与 PAGE_END 标记，并以 BATCH_END 结束。
"""


def build_batch_prompt(
    *, start_page: int, end_page: int, batch_id: int = 0
) -> str:
    return _PROMPT_BODY.format(
        start=start_page, end=end_page, batch_id=int(batch_id)
    )


_SINGLE_PAGE_EXTRA = """

【单页重跑】只转录 PAGE {page:04d} 这一页。
输出必须且只能包含该页的 PAGE / PAGE_END 标记与正文，不要输出其他页。
不要输出 BATCH_END。
"""


def build_single_page_prompt(*, page: int) -> str:
    base = build_batch_prompt(start_page=page, end_page=page, batch_id=0)
    return base + _SINGLE_PAGE_EXTRA.format(page=page)

