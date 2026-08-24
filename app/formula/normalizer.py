"""Normalizer：只规范已验证的 LaTeX。NEVER guesses formulas."""
from __future__ import annotations

import re

from app.formula.config import FormulaConfig


def normalize_validated_latex(body: str, cfg: FormulaConfig | None = None) -> str:
    """轻量规范：空白、已知布局 scrap、命令贴紧。

    禁止：根据上下文“猜”出完整公式；禁止把正文 Unicode 整段改成公式。
    """
    cfg = cfg or FormulaConfig()
    if not cfg.normalize_validated:
        return body
    s = body.strip()

    # 去掉明确布局 scrap（已通过 validator 的块里偶发残留）
    s = re.sub(r"\\intertext\s*\{[^}]*\}", "", s, flags=re.I)
    s = re.sub(
        r"\\text\s*\{\s*(?:red|al|bottom|top|wein|weighted|equative)\s*\}",
        "",
        s,
        flags=re.I,
    )
    # 压缩过量 \quad
    s = re.sub(r"(?:\\quad\s*){3,}", r"\\quad ", s)
    # 命令名后空格：\hat {x} → \hat{x}
    s = re.sub(r"\\([A-Za-z]+)\s*\{\s*", r"\\\1{", s)
    s = re.sub(r"[ \t]{2,}", " ", s)
    s = re.sub(r"\s*\\\\\s*", r" \\\\ ", s)

    from app.utils.typora_math_repair import repair_typora_math_body

    s = repair_typora_math_body(s)
    return s.strip()
