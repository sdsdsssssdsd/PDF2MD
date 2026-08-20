"""按风险与 issue 类型路由修复策略（Phase 0：仅 safe）。"""
from __future__ import annotations

from app.repair.models import IssueType, RepairConfig, RepairIssue


def route_method(issue: RepairIssue, cfg: RepairConfig) -> str:
    """返回本阶段实际会执行的方法名。"""
    if not cfg.enabled:
        return "keep"

    # Phase 0：一律走确定性 safe；后续再按分数升级
    if cfg.mode == "safe":
        if issue.type in {
            IssueType.UNICODE_MATH,
            IssueType.DECIMAL_SPLIT,
            IssueType.MALFORMED_DELIMITER,
        }:
            return "safe"
        return "keep"

    # smart / strong 预留
    if issue.severity < 0.20:
        return "keep"
    if issue.severity < 0.45:
        return "geometry" if cfg.use_geometry else "safe"
    if issue.severity < 0.70:
        return "vision" if cfg.use_vision else "safe"
    if cfg.use_reasoning:
        return "reasoning"
    if cfg.use_vision:
        return "vision"
    return "safe"
