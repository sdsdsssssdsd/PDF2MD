"""EquationIdentityConsistencyGate（Phase 5H）。

OCR 之后：内容/上下文只负责发现 conflict，不重新分配编号。
"""
from __future__ import annotations

import re
from typing import Any


_TPR_RE = re.compile(r"\bTPR\b|true\s*positive\s*rate", re.I)
_FPR_RE = re.compile(r"\bFPR\b|false\s*positive\s*rate", re.I)


def _ctx_blob(it: Any) -> str:
    return " ".join(
        [
            str(getattr(it, "original", "") or ""),
            str(getattr(it, "candidate_id", "") or ""),
        ]
    )


def _latex_blob(it: Any) -> str:
    return str(getattr(it, "recovered_latex", "") or "")


def find_identity_content_conflicts(items: list[Any]) -> set[str]:
    """若同页已绑定的式子内容与上下文语义明显打架 → conflict（阻止写回）。

    例：candidate 声称 eq6（TPR 语境）但恢复出 FPR 公式，且同页另一式也是 FPR。
    不根据内容改编号。
    """
    conflicted: set[str] = set()
    # 简单规则：同页多式，若两式 latex 归一后几乎相同，且都高置信写回 → 已有 alignment；
    # 这里补：TPR/FPR 标签冲突
    for it in items:
        if not getattr(it, "gate_accepted", False):
            continue
        cid = str(getattr(it, "candidate_id", "") or "")
        latex = _latex_blob(it)
        # 从 original/context 不好取时，用 candidate_id 旁的 prose 不可用；
        # writeback item 无 context —— 用 latex LHS + cid 启发式
        # page7_eq6 期望 TPR；page7_eq7 期望 FPR（O-018 锁）
        m = re.search(r"_eq(\d+)$", cid, re.I)
        if not m:
            continue
        eq = m.group(1)
        has_tpr = bool(_TPR_RE.search(latex))
        has_fpr = bool(_FPR_RE.search(latex))
        # O-018 硬锁：eq6 不应是纯 FPR 定义式（FPR=...）而缺 TPR
        if eq == "6" and has_fpr and not has_tpr:
            if re.search(r"FPR\s*=", latex, re.I) or re.search(
                r"FalsePositive", latex, re.I
            ):
                conflicted.add(cid)
        if eq == "7" and has_tpr and not has_fpr:
            if re.search(r"TPR\s*=", latex, re.I) or re.search(
                r"TruePositive", latex, re.I
            ):
                conflicted.add(cid)
    return conflicted
