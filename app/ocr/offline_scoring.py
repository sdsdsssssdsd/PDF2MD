"""Phase 3B：离线评分与 Acceptance Gate 校准（不重跑 OCR）。"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from app.formula.config import FormulaConfig
from app.formula.gain import evaluate_recovery_gain
from app.formula.types import FormulaQuality
from app.formula.validator import validate_latex
from app.ocr.deepseek_benchmark import DEFAULT_O018_CASES
from app.ocr.extractor import EquationExtractor
from app.ocr.match_eval import FormulaMatchEvaluator, MatchReport
from app.utils.paths import BENCHMARK_DIR, BENCHMARK_RUNS, ensure_dirs

FIXTURES_DIR = BENCHMARK_DIR / "fixtures"
NEGATIVE_DIR = FIXTURES_DIR / "negative"


@dataclass
class GateCase:
    name: str
    latex: str
    context_before: str
    expect_accept: bool
    before_latex: str = r"\quad\quad\quad\quad garbage \omega_{nd}"
    before_corruption: float = 0.95
    note: str = ""


@dataclass
class ConfusionMatrix:
    true_accept: int = 0
    false_accept: int = 0
    true_reject: int = 0
    false_reject: int = 0
    rows: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        n = self.true_accept + self.false_accept + self.true_reject + self.false_reject
        return {
            "true_accept": self.true_accept,
            "false_accept": self.false_accept,
            "true_reject": self.true_reject,
            "false_reject": self.false_reject,
            "n": n,
            "false_accept_rate": round(self.false_accept / max(1, n), 3),
            "false_reject_rate": round(self.false_reject / max(1, n), 3),
            "rows": self.rows,
        }


def default_positive_gate_cases() -> list[GateCase]:
    """人工可用的正确公式 → 期望 accept（在 corruption 高的 before 下）。"""
    return [
        GateCase(
            name="pos_eq1_bias",
            latex=r"E\left[\left(y-\hat{f}\right)^{2}\right]=Bias^{2}+V+\varepsilon",
            context_before="The expected mean squared error (MSE) can be expressed by Eq. (1):",
            expect_accept=True,
        ),
        GateCase(
            name="pos_eq4_recall",
            latex=r"Recall=\frac{TP}{TP+FN}",
            context_before="Recall can be calculated using Eq. (4):",
            expect_accept=True,
        ),
        GateCase(
            name="pos_eq5_f1",
            latex=r"F1=2\times\frac{Precision\times Recall}{Precision+Recall}",
            context_before="It can be calculated from Eq. (5):",
            expect_accept=True,
        ),
        GateCase(
            name="pos_eq6_tpr",
            latex=r"TPR=\frac{TP}{TP+FN}",
            context_before="True Positive Rate (TPR), which can be calculated using Eq. (6)",
            expect_accept=True,
        ),
        GateCase(
            name="pos_eq7_fpr",
            latex=r"FPR=\frac{FP}{FP+TN}",
            context_before="False Positive Rate (FPR) using Eq. (7)",
            expect_accept=True,
        ),
    ]


def default_negative_gate_cases() -> list[GateCase]:
    """幻觉 / 无关公式 → 期望 reject。"""
    ctx_recall = "Recall can be calculated using Eq. (4):"
    ctx_tpr = "True Positive Rate (TPR) Eq. (6)"
    return [
        GateCase(
            name="neg_omega",
            latex=r"\frac{\omega_{nd}^n}{\omega}",
            context_before=ctx_recall,
            expect_accept=False,
            note="classic hallucination",
        ),
        GateCase(
            name="neg_mu",
            latex=r"\frac{n}{n+\mu_0}",
            context_before=ctx_recall,
            expect_accept=False,
        ),
        GateCase(
            name="neg_sinn",
            latex=r"\frac{n\sin^n(n+1)}{n+n}",
            context_before=ctx_tpr,
            expect_accept=False,
        ),
        GateCase(
            name="neg_u_loop",
            latex=r"\frac{1}{u}\frac{u}{u}\frac{u}{u}",
            context_before=ctx_recall,
            expect_accept=False,
        ),
        GateCase(
            name="neg_gamma_noise",
            latex=r"\Gamma\quad\quad\quad\quad\quad",
            context_before=ctx_tpr,
            expect_accept=False,
        ),
    ]


def ensure_negative_fixtures() -> None:
    NEGATIVE_DIR.mkdir(parents=True, exist_ok=True)
    for c in default_negative_gate_cases():
        p = NEGATIVE_DIR / f"{c.name}.tex"
        if not p.exists():
            p.write_text(c.latex + "\n", encoding="utf-8")


def replay_gate_cases(
    cases: list[GateCase] | None = None,
    *,
    cfg: FormulaConfig | None = None,
) -> ConfusionMatrix:
    cfg = cfg or FormulaConfig()
    cases = cases or (default_positive_gate_cases() + default_negative_gate_cases())
    cm = ConfusionMatrix()
    for c in cases:
        before_q = FormulaQuality(
            syntax_score=0.1,
            corruption_score=c.before_corruption,
            semantic_score=0.2,
            valid=False,
            recoverable=True,
            reasons=["fixture_corrupted"],
        )
        vr = validate_latex(
            c.latex,
            cfg,
            context_before=c.context_before,
            context_after="",
        )
        gain = evaluate_recovery_gain(
            before_quality=before_q,
            after_quality=vr.quality,
            before_latex=c.before_latex,
            after_latex=c.latex,
            context_before=c.context_before,
            context_after="",
            after_valid=bool(c.latex) and vr.valid,
        )
        got = bool(gain.accept)
        exp = bool(c.expect_accept)
        if got and exp:
            cm.true_accept += 1
            bucket = "true_accept"
        elif got and not exp:
            cm.false_accept += 1
            bucket = "false_accept"
        elif (not got) and (not exp):
            cm.true_reject += 1
            bucket = "true_reject"
        else:
            cm.false_reject += 1
            bucket = "false_reject"
        cm.rows.append(
            {
                "name": c.name,
                "expect_accept": exp,
                "got_accept": got,
                "bucket": bucket,
                "reasons": list(gain.reasons),
                "valid": vr.valid,
                "corruption": round(float(vr.quality.corruption_score) if vr.quality else 1.0, 3),
                "note": c.note,
            }
        )
    return cm


def offline_fixture_scoring(
    *,
    fixtures_dir: Path | None = None,
) -> dict[str, Any]:
    """对 O-018 DeepSeek fixtures 全量离线重放：Extractor + MatchEvaluator。"""
    ensure_dirs()
    ensure_negative_fixtures()
    root = fixtures_dir or FIXTURES_DIR
    matcher = FormulaMatchEvaluator()
    extractor = EquationExtractor()
    rows: list[dict[str, Any]] = []
    by_mode: dict[str, dict[str, int]] = {}

    for spec in DEFAULT_O018_CASES:
        n = str(spec["eq_number"])
        gold = str(spec["gold_latex"])
        ctx = str(spec.get("context_before") or "")
        for mode in ("formula", "region", "page"):
            path = root / f"o018_eq{n}_deepseek_{mode}.md"
            if not path.exists():
                continue
            raw = path.read_text(encoding="utf-8")
            er = extractor.extract(raw, eq_number=n, context_before=ctx)
            selected = er.latex
            sel_match = matcher.compare(selected, gold)
            raw_layer = matcher.layer_report(raw_ocr=raw, selected=selected, gold=gold)
            slot = by_mode.setdefault(
                mode,
                {
                    "n": 0,
                    "exact": 0,
                    "structural": 0,
                    "token": 0,
                    "human_usable": 0,
                    "extractor_success": 0,
                    "extractor_failure": 0,
                    "ocr_failure": 0,
                },
            )
            slot["n"] += 1
            slot["exact"] += int(sel_match.exact_normalized_match)
            slot["structural"] += int(sel_match.structural_match)
            slot["token"] += int(sel_match.token_match)
            slot["human_usable"] += int(sel_match.human_usable)
            if raw_layer.layer in slot:
                slot[raw_layer.layer] += 1

            rows.append(
                {
                    "eq": n,
                    "mode": mode,
                    "file": path.name,
                    "extractor_method": er.method,
                    "extractor_failure_reason": er.failure_reason,
                    "selected_latex": selected[:200],
                    "match": sel_match.to_dict(),
                    "layer": raw_layer.to_dict(),
                }
            )

    return {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "phase": "3B_offline_scoring",
        "by_mode": by_mode,
        "rows": rows,
    }


def run_phase3b_offline(*, out_path: Path | None = None) -> dict[str, Any]:
    ensure_dirs()
    ensure_negative_fixtures()
    scoring = offline_fixture_scoring()
    gate_cm = replay_gate_cases()
    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "phase": "3B",
        "notes": [
            "未重跑 DeepSeek-OCR；仅 fixtures + Gate 离线重放。",
            "MatchEvaluator 仅用于 benchmark，不写回生产 Markdown。",
            "region 保留实验；Scheduler 第一版建议仅 formula + page。",
        ],
        "fixture_scoring": scoring,
        "gate_confusion": gate_cm.to_dict(),
        "policy": {
            "default_single_formula_path": "deepseek_formula",
            "scheduler_v1_modes": ["formula", "page"],
            "region_default": False,
        },
    }
    dest = out_path or (
        BENCHMARK_RUNS / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_phase3b_offline.json"
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    payload["output_path"] = str(dest)
    return payload


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="Phase 3B offline formula scoring (no OCR)")
    p.add_argument("--out", type=str, default="")
    args = p.parse_args(argv)
    payload = run_phase3b_offline(out_path=Path(args.out) if args.out else None)
    print("wrote", payload["output_path"])
    print(json.dumps(payload["fixture_scoring"]["by_mode"], ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in payload["gate_confusion"].items() if k != "rows"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
