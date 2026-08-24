# -*- coding: utf-8 -*-
"""Append harvest reviews for harvest-420 batch (38). Do not train."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path("benchmarks/gold/human_reviews_harvest.json")

NEW = [
    {
        "id": "14_Neural_ODEs_p15_eq48_h",
        "action": "verify",
        "gold_latex_raw": r"\frac{d}{dt}\begin{bmatrix}\mathbf{z}\\\theta\\t\end{bmatrix}(t)=f_{\mathrm{aug}}([\mathbf{z},\theta,t]):=\begin{bmatrix}f([\mathbf{z},\theta,t])\\\mathbf{0}\\1\end{bmatrix},\quad\mathbf{a}_{\mathrm{aug}}:=\begin{bmatrix}\mathbf{a}\\\mathbf{a}_{\theta}\\\mathbf{a}_{t}\end{bmatrix},\quad\mathbf{a}_{\theta}(t):=\frac{dL}{d\theta(t)},\quad\mathbf{a}_{t}(t):=\frac{dL}{dt(t)}",
        "equation_number": "48",
        "notes": "human_from_harvest; complete augmented state and adjoint defs",
    },
    {
        "id": "14_Neural_ODEs_p15_eq49_h",
        "action": "verify",
        "gold_latex_raw": r"\frac{\partial f_{\mathrm{aug}}}{\partial[\mathbf{z},\theta,t]}=\begin{bmatrix}\frac{\partial f}{\partial\mathbf{z}}&\frac{\partial f}{\partial\theta}&\frac{\partial f}{\partial t}\\\mathbf{0}&0&0\\\mathbf{0}&0&0\end{bmatrix}(t)",
        "equation_number": "49",
        "notes": "human_from_harvest; complete augmented Jacobian",
    },
    {
        "id": "14_Neural_ODEs_p15_eq50_h",
        "action": "verify",
        "gold_latex_raw": r"\frac{d\mathbf{a}_{\mathrm{aug}}(t)}{dt}=-[\mathbf{a}(t)\quad\mathbf{a}_{\theta}(t)\quad\mathbf{a}_{t}(t)]\frac{\partial f_{\mathrm{aug}}}{\partial[\mathbf{z},\theta,t]}(t)=-[\mathbf{a}\frac{\partial f}{\partial\mathbf{z}}\quad\mathbf{a}\frac{\partial f}{\partial\theta}\quad\mathbf{a}\frac{\partial f}{\partial t}](t)",
        "equation_number": "50",
        "notes": "human_from_harvest; complete augmented adjoint ODE",
    },
    {
        "id": "14_Neural_ODEs_p15_eq51_h",
        "action": "verify",
        "gold_latex_raw": r"\frac{dL}{d\theta}=\mathbf{a}_{\theta}(t_{0})=-\int_{t_{N}}^{t_{0}}\mathbf{a}(t)\frac{\partial f(\mathbf{z}(t),t,\theta)}{\partial\theta}dt",
        "equation_number": "51",
        "notes": "human_from_harvest; complete parameter adjoint integral",
    },
    {
        "id": "14_Neural_ODEs_p15_eq52_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "two time-adjoint identities sharing (52)",
    },
    {
        "id": "20_TRPO_p12_eq54_h",
        "action": "verify",
        "gold_latex_raw": r"\gamma^{2}|rG\Delta G\Delta\tilde{G}\rho|\leq\gamma\|\gamma rG\Delta\|_{\infty}\|G\Delta\tilde{G}\rho\|_{1}\leq\gamma\|v\Delta\|_{\infty}\|G\Delta\tilde{G}\rho\|_{1}\leq\gamma\cdot 2\alpha\epsilon\cdot\frac{2\alpha}{(1-\gamma)^{2}}=\frac{4\gamma\epsilon}{(1-\gamma)^{2}}\alpha^{2}",
        "equation_number": "54",
        "notes": "human_from_harvest; complete cubic remainder bound",
    },
    {
        "id": "20_TRPO_p12_eq55_h",
        "action": "verify",
        "gold_latex_raw": r"\mathrm{maximize}\ L(\theta)\quad\mathrm{subject\ to}\quad\bar{D}_{\mathrm{KL}}(\theta_{\mathrm{old}},\theta)\leq\delta",
        "equation_number": "55",
        "notes": "human_from_harvest; complete trust-region program",
    },
    {
        "id": "20_TRPO_p13_eq56_h",
        "action": "verify",
        "gold_latex_raw": r"D_{\mathrm{KL}}(\pi_{\theta_{\mathrm{old}}}(\cdot|x)\|\pi_{\theta}(\cdot|x))=\mathrm{kl}(\mu_{\theta}(x),\mu_{\mathrm{old}})",
        "equation_number": "56",
        "notes": "human_from_harvest; complete Gaussian KL reduction",
    },
    {
        "id": "20_TRPO_p13_eq57_h",
        "action": "verify",
        "gold_latex_raw": r"\frac{\partial\mu_{a}(x)}{\partial\theta_{i}}\frac{\partial\mu_{b}(x)}{\partial\theta_{j}}\mathrm{kl}''_{ab}(\mu_{\theta}(x),\mu_{\mathrm{old}})+\frac{\partial^{2}\mu_{a}(x)}{\partial\theta_{i}\partial\theta_{j}}\mathrm{kl}'_{a}(\mu_{\theta}(x),\mu_{\mathrm{old}})",
        "equation_number": "57",
        "notes": "human_from_harvest; complete KL Hessian expansion",
    },
    {
        "id": "39_PaLM_p11_eq4_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "WiC/MultiRC table scores, not a display equation",
    },
    {
        "id": "39_PaLM_p27_eq9_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "translation table scores, not a display equation",
    },
    {
        "id": "42_DPO_p14_eq12_h",
        "action": "reject",
        "crop_quality": ["clipped_left"],
        "notes": "top line of derivation is horizontally clipped",
    },
    {
        "id": "42_DPO_p15_eq13_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq", "prose_contaminated"],
        "notes": "partition-function prose plus stacked identities",
    },
    {
        "id": "42_DPO_p15_eq14_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "min-KL fragment stacked with leftover (14)",
    },
    {
        "id": "42_DPO_p15_eq15_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "Hence we have the optimal solution above (15)",
    },
    {
        "id": "42_DPO_p15_eq16_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "have lead-in above Bradley-Terry (16)",
    },
    {
        "id": "42_DPO_p15_eq17_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq", "prose_contaminated"],
        "notes": "(17) plus Substituting sentence and unnumbered derivation",
    },
    {
        "id": "42_DPO_p15_eq18_h",
        "action": "verify",
        "gold_latex_raw": r"p^{*}(\tau|y_{1},\dots,y_{K},x)=\prod_{k=1}^{K}\frac{\exp(r^{*}(x,y_{\tau(k)}))}{\sum_{j=k}^{K}\exp(r^{*}(x,y_{\tau(j)}))}",
        "equation_number": "18",
        "notes": "human_from_harvest; complete Plackett-Luce ranking",
    },
    {
        "id": "45_RoFormer_p2_eq7_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "W_k and W-tilde resulting in lead-in",
    },
    {
        "id": "45_RoFormer_p2_eq8_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "Equation (6) as lead-in",
    },
    {
        "id": "45_RoFormer_p2_eq9_h",
        "action": "verify",
        "gold_latex_raw": r"\boldsymbol{q}_{m}^{\top}\boldsymbol{k}_{n}=\boldsymbol{x}_{m}^{\top}\mathbf{W}_{q}^{\top}\mathbf{W}_{k}\boldsymbol{x}_{n}+\boldsymbol{p}_{m}^{\top}\mathbf{U}_{q}^{\top}\mathbf{U}_{k}\boldsymbol{p}_{n}+b_{i,j}",
        "equation_number": "9",
        "notes": "human_from_harvest; complete absolute-plus-relative inner product",
    },
    {
        "id": "45_RoFormer_p3_eq10_h",
        "action": "verify",
        "gold_latex_raw": r"\boldsymbol{q}_{m}^{\top}\boldsymbol{k}_{n}=\boldsymbol{x}_{m}^{\top}\mathbf{W}_{q}^{\top}\mathbf{W}_{k}\boldsymbol{x}_{n}+\boldsymbol{x}_{m}^{\top}\mathbf{W}_{q}^{\top}\mathbf{W}_{k}\tilde{\boldsymbol{p}}_{m-n}+\tilde{\boldsymbol{p}}_{m-n}^{\top}\mathbf{W}_{q}^{\top}\mathbf{W}_{k}\boldsymbol{x}_{n}",
        "equation_number": "10",
        "notes": "human_from_harvest; complete relative-position expansion",
    },
    {
        "id": "45_RoFormer_p3_eq11_h",
        "action": "verify",
        "gold_latex_raw": r"\langle f_{q}(\boldsymbol{x}_{m},m),f_{k}(\boldsymbol{x}_{n},n)\rangle=g(\boldsymbol{x}_{m},\boldsymbol{x}_{n},m-n).",
        "equation_number": "11",
        "notes": "human_from_harvest; complete relative inner-product form",
    },
    {
        "id": "45_RoFormer_p3_eq12_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "formulation Equation (11) is lead-in plus three stacked defs",
    },
    {
        "id": "45_RoFormer_p3_eq21_h",
        "action": "verify",
        "gold_latex_raw": r"f_{\{q,k\}}(\boldsymbol{x}_{m},m)=\begin{pmatrix}\cos m\theta&-\sin m\theta\\\sin m\theta&\cos m\theta\end{pmatrix}\begin{pmatrix}W_{\{q,k\}}^{(11)}\\W_{\{q,k\}}^{(21)}\end{pmatrix}",
        "equation_number": "21",
        "notes": "human_from_harvest; complete 2D rotary map",
    },
    {
        "id": "46_RMSNorm_p3_eq7_h",
        "action": "verify",
        "gold_latex_raw": r"\mathbf{y}'=f\left(\frac{\mathbf{W}'\mathbf{x}}{\mathrm{RMS}(\mathbf{a}')}\odot\mathbf{g}+\mathbf{b}\right)=f\left(\frac{\delta\mathbf{W}\mathbf{x}}{\delta\mathrm{RMS}(\mathbf{a})}\odot\mathbf{g}+\mathbf{b}\right)=\mathbf{y}.",
        "equation_number": "7",
        "notes": "human_from_harvest; complete RMS scale invariance",
    },
    {
        "id": "46_RMSNorm_p4_eq8_h",
        "action": "verify",
        "gold_latex_raw": r"\frac{\partial\mathcal{L}}{\partial\mathbf{b}}=\frac{\partial\mathcal{L}}{\partial\mathbf{v}},\quad\frac{\partial\mathcal{L}}{\partial\mathbf{g}}=\frac{\partial\mathcal{L}}{\partial\mathbf{v}}\odot\frac{\mathbf{W}\mathbf{x}}{\mathrm{RMS}(\mathbf{a})},",
        "equation_number": "8",
        "notes": "human_from_harvest; complete bias and gain grads",
    },
    {
        "id": "46_RMSNorm_p4_eq9_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "where joins W-grad to R definition",
    },
    {
        "id": "46_RMSNorm_p4_eq10_h",
        "action": "verify",
        "gold_latex_raw": r"\mathbf{R}'=\frac{1}{\delta\mathrm{RMS}(\mathbf{a})}\left(\mathbf{I}-\frac{(\delta\mathbf{W}\mathbf{x})(\delta\mathbf{W}\mathbf{x})^{T}}{n\delta^{2}\mathrm{RMS}(\mathbf{a})^{2}}\right)=\frac{1}{\delta}\mathbf{R}.",
        "equation_number": "10",
        "notes": "human_from_harvest; complete scaled residual projector",
    },
    {
        "id": "49_Knowledge_Distillation_p1_eq1_h",
        "action": "verify",
        "gold_latex_raw": r"q_{i}=\frac{\exp(z_{i}/T)}{\sum_{j}\exp(z_{j}/T)}",
        "equation_number": "1",
        "notes": "human_from_harvest; complete temperature softmax",
    },
    {
        "id": "49_Knowledge_Distillation_p2_eq2_h",
        "action": "verify",
        "gold_latex_raw": r"\frac{\partial C}{\partial z_{i}}=\frac{1}{T}(q_{i}-p_{i})=\frac{1}{T}\left(\frac{e^{z_{i}/T}}{\sum_{j}e^{z_{j}/T}}-\frac{e^{v_{i}/T}}{\sum_{j}e^{v_{j}/T}}\right)",
        "equation_number": "2",
        "notes": "human_from_harvest; complete distillation gradient",
    },
    {
        "id": "49_Knowledge_Distillation_p2_eq3_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq", "prose_contaminated"],
        "notes": "(3) plus zero-mean logits sentence and (4)",
    },
    {
        "id": "49_Knowledge_Distillation_p2_eq4_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq", "prose_contaminated"],
        "notes": "same crop as (3): two numbered eqs plus prose",
    },
    {
        "id": "49_Knowledge_Distillation_p5_eq5_h",
        "action": "verify",
        "gold_latex_raw": r"KL(\mathbf{p}^{g},\mathbf{q})+\sum_{m\in A_{k}}KL(\mathbf{p}^{m},\mathbf{q})",
        "equation_number": "5",
        "notes": "human_from_harvest; complete specialist ensemble KL",
    },
    {
        "id": "50_Deep_Learning_with_Differential_Privacy_p3_eq3_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq", "prose_contaminated"],
        "notes": "Gaussian-mixture prose plus (3) and (4)",
    },
    {
        "id": "50_Deep_Learning_with_Differential_Privacy_p3_eq4_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq", "prose_contaminated"],
        "notes": "same crop as (3): two numbered eqs plus prose",
    },
    {
        "id": "50_Deep_Learning_with_Differential_Privacy_p12_eq5_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "Thus the third term ... (5) lead-in",
    },
    {
        "id": "50_Deep_Learning_with_Differential_Privacy_p12_eq2_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "three observations sentence, not a display equation",
    },
]


def main() -> int:
    spec = json.loads(PATH.read_text(encoding="utf-8"))
    old_ids = {str(r.get("id") or "") for r in spec.get("reviews") or []}
    added = 0
    for rev in NEW:
        if rev["id"] in old_ids:
            raise SystemExit(f"duplicate review id: {rev['id']}")
        spec["reviews"].append(rev)
        added += 1
    spec["created_at"] = "2026-08-23T17:55:00"
    v = sum(1 for r in NEW if r["action"] == "verify")
    r = sum(1 for r in NEW if r["action"] == "reject")
    PATH.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print({"added": added, "verify": v, "reject": r, "total_reviews": len(spec["reviews"])})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
