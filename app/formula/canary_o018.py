# -*- coding: utf-8 -*-
"""O-018 回归门：7.2/7.3 实验硬约束（k1.md）。"""
from __future__ import annotations

from typing import Any


O018_STEM = "O-018_Abdo2025_Stacking_SHAP"
O018_EXPECTED_ACCEPTED = 7
O018_EXPECTED_REJECTED = 0


class O018RegressionError(AssertionError):
    """O-018 canary 未通过。"""


def check_o018_regression_gate(
    row: dict[str, Any] | Any,
    *,
    raise_on_fail: bool = True,
) -> dict[str, Any]:
    """验收 O-018：accepted==7 且 rejected==0。

    row 可为实验表行 dict（含 accepted/rejected/document）或带同名字段的对象。
    """
    if hasattr(row, "to_dict"):
        data = row.to_dict()
    elif isinstance(row, dict):
        data = row
    else:
        data = {
            "document": getattr(row, "document", ""),
            "accepted": getattr(row, "accepted", None),
            "rejected": getattr(row, "rejected", None),
        }
    doc = str(data.get("document") or data.get("document_id") or "")
    if O018_STEM not in doc and not doc.startswith("O-018"):
        result = {
            "applicable": False,
            "document": doc,
            "pass": True,
            "reason": "not_o018",
        }
        return result

    accepted = data.get("accepted")
    rejected = data.get("rejected")
    ok = (
        accepted is not None
        and rejected is not None
        and int(accepted) == O018_EXPECTED_ACCEPTED
        and int(rejected) == O018_EXPECTED_REJECTED
    )
    result = {
        "applicable": True,
        "document": doc,
        "pass": bool(ok),
        "accepted": accepted,
        "rejected": rejected,
        "expected_accepted": O018_EXPECTED_ACCEPTED,
        "expected_rejected": O018_EXPECTED_REJECTED,
        "gate": "REGRESSION_GATE",
        "checks": {
            "o018_recovery_recall": ok,
        },
    }
    if not ok and raise_on_fail:
        raise O018RegressionError(
            f"O-018 regression: accepted={accepted} rejected={rejected} "
            f"(expected {O018_EXPECTED_ACCEPTED}/{O018_EXPECTED_REJECTED})"
        )
    return result
