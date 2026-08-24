# -*- coding: utf-8 -*-
"""Append harvest reviews for harvest-380 batch (40). Do not train."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path("benchmarks/gold/human_reviews_harvest.json")

NEW = [
    {
        "id": "14_Neural_ODEs_p14_eq42_h",
        "action": "verify",
        "gold_latex_raw": r"=\lim_{\varepsilon\to 0^{+}}\frac{\mathbf{a}(t+\varepsilon)-\mathbf{a}(t+\varepsilon)\left(I+\varepsilon\frac{\partial f(\mathbf{z}(t),t,\theta)}{\partial\mathbf{z}(t)}+\mathcal{O}(\varepsilon^{2})\right)}{\varepsilon}",
        "equation_number": "42",
        "notes": "human_from_harvest; complete adjoint Euler increment",
    },
    {
        "id": "14_Neural_ODEs_p14_eq43_h",
        "action": "verify",
        "gold_latex_raw": r"=\lim_{\varepsilon\to 0^{+}}\frac{-\varepsilon\mathbf{a}(t+\varepsilon)\frac{\partial f(\mathbf{z}(t),t,\theta)}{\partial\mathbf{z}(t)}+\mathcal{O}(\varepsilon^{2})}{\varepsilon}",
        "equation_number": "43",
        "notes": "human_from_harvest; complete cancelled adjoint increment",
    },
    {
        "id": "14_Neural_ODEs_p14_eq44_h",
        "action": "verify",
        "gold_latex_raw": r"=\lim_{\varepsilon\to 0^{+}}-\mathbf{a}(t+\varepsilon)\frac{\partial f(\mathbf{z}(t),t,\theta)}{\partial\mathbf{z}(t)}+\mathcal{O}(\varepsilon)",
        "equation_number": "44",
        "notes": "human_from_harvest; complete adjoint limit form",
    },
    {
        "id": "14_Neural_ODEs_p14_eq45_h",
        "action": "verify",
        "gold_latex_raw": r"=-\mathbf{a}(t)\frac{\partial f(\mathbf{z}(t),t,\theta)}{\partial\mathbf{z}(t)}",
        "equation_number": "45",
        "notes": "human_from_harvest; complete adjoint vector field",
    },
    {
        "id": "14_Neural_ODEs_p14_eq46_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "two adjoint identities plus cropped underbrace labels",
    },
    {
        "id": "14_Neural_ODEs_p14_eq47_h",
        "action": "verify",
        "gold_latex_raw": r"\frac{\partial\theta(t)}{\partial t}=\mathbf{0}\quad\frac{dt(t)}{dt}=1",
        "equation_number": "47",
        "notes": "human_from_harvest; complete augmented time/param dynamics",
    },
    {
        "id": "20_TRPO_p11_eq48_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "Substituting ... gives lead-in above (48)",
    },
    {
        "id": "20_TRPO_p11_eq49_h",
        "action": "verify",
        "gold_latex_raw": r"\eta(\tilde{\pi})-\eta(\pi)=r(\tilde{G}-G)\rho=\gamma rG\Delta G\rho_{0}+\gamma^{2}rG\Delta G\Delta\tilde{G}\rho_{0}",
        "equation_number": "49",
        "notes": "human_from_harvest; complete performance-difference expansion",
    },
    {
        "id": "20_TRPO_p12_eq50_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "advantage sentence above five-line derivation (50)",
    },
    {
        "id": "20_TRPO_p12_eq51_h",
        "action": "verify",
        "gold_latex_raw": r"|(\gamma v\Delta)_{s}|=\left|\sum_{a}(\tilde{\pi}(s,a)-\pi(s,a))Q_{\pi}(s,a)\right|=\left|\sum_{a}(\tilde{\pi}(s,a)-\pi(s,a))A_{\pi}(s,a)\right|\leq\sum_{a}|\tilde{\pi}(s,a)-\pi(s,a)|\cdot\max_{a}|A_{\pi}(s,a)|\leq 2\alpha\epsilon",
        "equation_number": "51",
        "notes": "human_from_harvest; complete advantage coupling bound",
    },
    {
        "id": "20_TRPO_p12_eq52_h",
        "action": "verify",
        "gold_latex_raw": r"\|A\|_{1}=\sup_{\rho}\left\{\frac{\|A\rho\|_{1}}{\|\rho\|_{1}}\right\}",
        "equation_number": "52",
        "notes": "human_from_harvest; complete induced 1-norm",
    },
    {
        "id": "20_TRPO_p12_eq53_h",
        "action": "verify",
        "gold_latex_raw": r"=\frac{1}{1-\gamma}\cdot 2\alpha\cdot\frac{1}{1-\gamma}\cdot 1",
        "equation_number": "53",
        "notes": "human_from_harvest; complete discounted 1-norm product",
    },
    {
        "id": "38_Chinchilla_p24_eq9_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "Bayes-classifier decomposition sentence above (9)",
    },
    {
        "id": "38_Chinchilla_p24_eq10_h",
        "action": "verify",
        "gold_latex_raw": r"L(N,D)=E+\frac{A}{N^{0.34}}+\frac{B}{D^{0.28}},",
        "equation_number": "10",
        "notes": "human_from_harvest; complete fitted scaling exponents",
    },
    {
        "id": "38_Chinchilla_p24_eq11_h",
        "action": "verify",
        "gold_latex_raw": r"\min_{a,b,e,\alpha,\beta}\sum_{\mathrm{Run}\ i}\mathrm{Huber}_{\delta}(\mathrm{LSE}(a-\alpha\log N_{i},b-\beta\log D_{i},e)-\log L_{i}),",
        "equation_number": "11",
        "notes": "human_from_harvest; complete LSE Huber fit",
    },
    {
        "id": "39_PaLM_p11_eq5_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "Lambada/HellaSwag table scores, not a display equation",
    },
    {
        "id": "39_PaLM_p11_eq2_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "Drop/CoQA table scores, not a display equation",
    },
    {
        "id": "39_PaLM_p11_eq10_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "QuAC/SQuADv2 table scores, not a display equation",
    },
    {
        "id": "39_PaLM_p11_eq3_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "ARC table scores, not a display equation",
    },
    {
        "id": "39_PaLM_p11_eq100_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "ARC-c/OpenbookQA table scores, not a display equation",
    },
    {
        "id": "39_PaLM_p11_eq32_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "ARC-c/OpenbookQA table scores, not a display equation",
    },
    {
        "id": "42_DPO_p3_eq6_h",
        "action": "verify",
        "gold_latex_raw": r"p^{*}(y_{1}\succ y_{2}|x)=\frac{1}{1+\exp\left(\beta\log\frac{\pi^{*}(y_{2}|x)}{\pi_{\mathrm{ref}}(y_{2}|x)}-\beta\log\frac{\pi^{*}(y_{1}|x)}{\pi_{\mathrm{ref}}(y_{1}|x)}\right)}",
        "equation_number": "6",
        "notes": "human_from_harvest; complete BT preference from optimal policy",
    },
    {
        "id": "42_DPO_p3_eq7_h",
        "action": "verify",
        "gold_latex_raw": r"\mathcal{L}_{\mathrm{DPO}}(\pi_{\theta};\pi_{\mathrm{ref}})=-\mathbb{E}_{(x,y_{w},y_{l})\sim\mathcal{D}}\left[\log\sigma\left(\beta\log\frac{\pi_{\theta}(y_{w}|x)}{\pi_{\mathrm{ref}}(y_{w}|x)}-\beta\log\frac{\pi_{\theta}(y_{l}|x)}{\pi_{\mathrm{ref}}(y_{l}|x)}\right)\right].",
        "equation_number": "7",
        "notes": "human_from_harvest; complete DPO loss",
    },
    {
        "id": "42_DPO_p5_eq8_h",
        "action": "verify",
        "gold_latex_raw": r"f(r;\pi_{\mathrm{ref}},\beta)(x,y)=r(x,y)-\beta\log\sum_{y}\pi_{\mathrm{ref}}(y|x)\exp\left(\frac{1}{\beta}r(x,y)\right)",
        "equation_number": "8",
        "notes": "human_from_harvest; complete reward change of variables",
    },
    {
        "id": "42_DPO_p5_eq9_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "underbrace Thm.1 prose plus descenders above (9)",
    },
    {
        "id": "42_DPO_p5_eq10_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "two underbrace labels plus descenders above (10)",
    },
    {
        "id": "42_DPO_p14_eq11_h",
        "action": "verify",
        "gold_latex_raw": r"\max_{\pi}\mathbb{E}_{x\sim\mathcal{D},y\sim\pi}[r(x,y)]-\beta D_{\mathrm{KL}}[\pi(y|x)\|\pi_{\mathrm{ref}}(y|x)]",
        "equation_number": "11",
        "notes": "human_from_harvest; complete KL-regularized RL objective",
    },
    {
        "id": "43_FlashAttention_p18_eq6_h",
        "action": "verify",
        "gold_latex_raw": r"dk_{j}=\sum_{i}dS_{ij}q_{i}=\sum_{i}P_{ij}(dP_{ij}-D_{i})q_{i}=\sum_{i}\frac{e^{q_{i}^{T}k_{j}}}{L_{i}}(do_{i}^{T}v_{j}-D_{i})q_{i}.",
        "equation_number": "6",
        "notes": "human_from_harvest; complete dk backward",
    },
    {
        "id": "45_RoFormer_p1_eq1_h",
        "action": "verify",
        "gold_latex_raw": r"\boldsymbol{q}_{m}=f_{q}(\boldsymbol{x}_{m},m),\quad\boldsymbol{k}_{n}=f_{k}(\boldsymbol{x}_{n},n),\quad\boldsymbol{v}_{n}=f_{v}(\boldsymbol{x}_{n},n),",
        "equation_number": "1",
        "notes": "human_from_harvest; complete qkv position maps",
    },
    {
        "id": "45_RoFormer_p2_eq2_h",
        "action": "verify",
        "gold_latex_raw": r"a_{m,n}=\frac{\exp(\boldsymbol{q}_{m}^{\top}\boldsymbol{k}_{n}/\sqrt{d})}{\sum_{j=1}^{N}\exp(\boldsymbol{q}_{m}^{\top}\boldsymbol{k}_{j}/\sqrt{d})},\quad\boldsymbol{o}_{m}=\sum_{n=1}^{N}a_{m,n}\boldsymbol{v}_{n}",
        "equation_number": "2",
        "notes": "human_from_harvest; complete attention weights and output",
    },
    {
        "id": "45_RoFormer_p2_eq3_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "A typical choice of Equation (1) is lead-in",
    },
    {
        "id": "45_RoFormer_p2_eq4_h",
        "action": "verify",
        "gold_latex_raw": r"\boldsymbol{p}_{i,2t}=\sin(k/10000^{2t/d}),\quad\boldsymbol{p}_{i,2t+1}=\cos(k/10000^{2t/d})",
        "equation_number": "4",
        "notes": "human_from_harvest; complete sinusoidal position pair",
    },
    {
        "id": "45_RoFormer_p2_eq5_h",
        "action": "verify",
        "gold_latex_raw": r"f_{q}(\boldsymbol{x}_{m}):=\boldsymbol{W}_{q}\boldsymbol{x}_{m},\quad f_{k}(\boldsymbol{x}_{n},n):=\boldsymbol{W}_{k}(\boldsymbol{x}_{n}+\tilde{\boldsymbol{p}}_{r}^{k}),\quad f_{v}(\boldsymbol{x}_{n},n):=\boldsymbol{W}_{v}(\boldsymbol{x}_{n}+\tilde{\boldsymbol{p}}_{r}^{v})",
        "equation_number": "5",
        "notes": "human_from_harvest; complete absolute-plus-relative maps",
    },
    {
        "id": "45_RoFormer_p2_eq6_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "decompose Equation (2) sentence above (6)",
    },
    {
        "id": "46_RMSNorm_p2_eq1_h",
        "action": "verify",
        "gold_latex_raw": r"a_{i}=\sum_{j=1}^{m}w_{ij}x_{j},\quad y_{i}=f(a_{i}+b_{i}),",
        "equation_number": "1",
        "notes": "human_from_harvest; complete affine neuron pair",
    },
    {
        "id": "46_RMSNorm_p2_eq2_h",
        "action": "verify",
        "gold_latex_raw": r"\bar{a}_{i}=\frac{a_{i}-\mu}{\sigma}g_{i},\quad y_{i}=f(\bar{a}_{i}+b_{i}),",
        "equation_number": "2",
        "notes": "human_from_harvest; complete LayerNorm pair",
    },
    {
        "id": "46_RMSNorm_p2_eq3_h",
        "action": "verify",
        "gold_latex_raw": r"\mu=\frac{1}{n}\sum_{i=1}^{n}a_{i},\quad\sigma=\sqrt{\frac{1}{n}\sum_{i=1}^{n}(a_{i}-\mu)^{2}}.",
        "equation_number": "3",
        "notes": "human_from_harvest; complete mean and std",
    },
    {
        "id": "46_RMSNorm_p2_eq4_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "where joins RMS definition to (4)",
    },
    {
        "id": "46_RMSNorm_p3_eq5_h",
        "action": "verify",
        "gold_latex_raw": r"\mathbf{y}=f\left(\frac{\mathbf{W}\mathbf{x}}{\mathrm{RMS}(a)}\odot\mathbf{g}+\mathbf{b}\right),",
        "equation_number": "5",
        "notes": "human_from_harvest; complete RMSNorm layer",
    },
    {
        "id": "46_RMSNorm_p3_eq6_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "property of RMS lead-in above (6)",
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
    spec["created_at"] = "2026-08-23T17:45:00"
    v = sum(1 for r in NEW if r["action"] == "verify")
    r = sum(1 for r in NEW if r["action"] == "reject")
    PATH.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print({"added": added, "verify": v, "reject": r, "total_reviews": len(spec["reviews"])})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
