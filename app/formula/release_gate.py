"""FormulaReleaseGate：禁止明显坏文档被标成完全成功。"""
from __future__ import annotations

import re

from app.formula.config import FormulaConfig
from app.formula.types import DocumentQuality, FormulaQAReport


def check_release(
    markdown: str,
    report: FormulaQAReport | None = None,
    cfg: FormulaConfig | None = None,
    *,
    writeback_skipped: int = 0,
) -> DocumentQuality:
    cfg = cfg or FormulaConfig()
    reasons: list[str] = []
    failures = 0

    if re.search(r"(?:\\quad\s*){8,}", markdown):
        reasons.append("quad_spam_in_markdown")
        failures += 1

    if "formula-not-decoded" in markdown and (cfg.fallback_mode or "") == "clean":
        # Docling enrich OFF / 未恢复占位：记为未解决，而非 debug 泄漏
        n_left = len(re.findall(r"formula-not-decoded", markdown))
        reasons.append("unresolved_formula_not_decoded")
        failures += n_left
    elif "formula-not-decoded" in markdown:
        reasons.append("unresolved_formula_not_decoded")
        failures += len(re.findall(r"formula-not-decoded", markdown))

    # 超长公式块 + 极少非 spacing 内容
    for m in re.finditer(r"\$\$(.+?)\$\$", markdown, re.S):
        body = m.group(1)
        if len(body) < 300:
            continue
        compact = re.sub(
            r"\\(?:quad|qquad|[,;:!])|\s+",
            "",
            body,
        )
        if len(compact) < 20:
            reasons.append("long_low_info_display")
            failures += 1

    if report:
        failures += int(report.recovery_failed_count or 0)
        if report.recovery_failed_count:
            reasons.append("recovery_failed_count")
        if report.suspected_unwrapped:
            reasons.append("suspected_unwrapped")

    if writeback_skipped > 0:
        failures += int(writeback_skipped)
        reasons.append("writeback_skipped")

    dollars = markdown.count("$")
    if dollars % 2 == 1:
        reasons.append("unbalanced_dollar")
        failures += 1

    # 有未恢复失败 → 不能标 fully-successful
    publishable = failures == 0
    if report and report.recovery_failed_count:
        publishable = False
    status = "ok" if publishable else "formula_incomplete"
    if (cfg.fallback_mode or "").lower() == "strict" and report and report.recovery_failed_count:
        publishable = False
        status = "formula_incomplete"

    return DocumentQuality(
        publishable=publishable,
        formula_failures=failures,
        reasons=list(dict.fromkeys(reasons)),
        status=status,
    )
