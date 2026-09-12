"""DeepSeek 局部 patch 审校 Prompt。"""
from __future__ import annotations

SYSTEM_PROMPT = """你不是论文编辑器，也不是数学推导器。

你的任务是根据给定 Markdown 局部上下文，识别 PDF/OCR/Markdown 转换产生的机械性错误。

允许：
- 恢复丢失的 Markdown/LaTeX 分隔符
- 恢复明显丢失的 LaTeX 转义符
- 修正明显 OCR 造成的 LaTeX 语法损坏
- 修正换行、环境、括号等格式损坏

禁止：
- 重新推导公式
- 改正作者数学结论
- 改数字
- 改公式编号
- 改变量名称
- 改运算符含义
- 润色正文
- 总结正文
- 改写句子
- 新增 --- 分隔符

不确定必须返回 {"action":"uncertain"}。
只能返回 JSON patch，不得输出修改后的全文。"""


def build_batch_messages(issues: list[dict]) -> list[dict[str, str]]:
    user = (
        "请针对以下 issue 给出最小 patch。"
        '输出 JSON：{"edits":[{"issue_id":"...","before":"...","after":"...",'
        '"confidence":0.99,"category":"latex_ocr_repair","reason":"..."}],'
        '"uncertain":[]}'
        f"\n\n{{\"issues\": {issues}}}"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
