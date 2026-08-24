# -*- coding: utf-8 -*-
"""Append harvest reviews for leftover per-paper-5 plus harvest-260 extras (30). Do not train."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path("benchmarks/gold/human_reviews_harvest.json")

NEW = [
    {
        "id": "13_Deep_Sets_p19_eq25_h",
        "action": "verify",
        "gold_latex_raw": r"s(x|X)=\log\frac{p(X\cup\{x\}|\alpha)}{p(X|\alpha)p(\{x\}|\alpha)}",
        "equation_number": "25",
        "notes": "human_from_harvest; complete pointwise score",
    },
    {
        "id": "13_Deep_Sets_p19_eq26_h",
        "action": "verify",
        "gold_latex_raw": r"S(X):=\sum_{m=1}^{M}s(x_{m}|\{x_{m-1},\dots,x_{1}\})=\log p(X|\alpha)-\sum_{m=1}^{M}\log p(\{x_{m}\}|\alpha)",
        "equation_number": "26",
        "notes": "human_from_harvest; complete set score chain",
    },
    {
        "id": "13_Deep_Sets_p19_eq27_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "conjugate-priors lead-in and two defs joined by and",
    },
    {
        "id": "13_Deep_Sets_p19_eq28_h",
        "action": "verify",
        "gold_latex_raw": r"s(X)=h(\alpha+\phi(X),M_{0}+M)+(M-1)h(\alpha,M_{0})-\sum_{m=1}^{M}h(\alpha+\phi(x_{m}),M+1)",
        "equation_number": "28",
        "notes": "human_from_harvest; complete exponential-family score",
    },
    {
        "id": "13_Deep_Sets_p19_eq29_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq", "prose_contaminated"],
        "notes": "sum residue above plus D.2 paragraph below (29)",
    },
    {
        "id": "14_Neural_ODEs_p12_eq27_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "previous-line fragments along the top edge",
    },
    {
        "id": "14_Neural_ODEs_p13_eq28_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "Let f(z)=uh(...) sentence above (28)",
    },
    {
        "id": "14_Neural_ODEs_p13_eq29_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "volume-preserving sentence above the split flow",
    },
    {
        "id": "14_Neural_ODEs_p13_eq30_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "two lines of continuity-equation prose above (30)",
    },
    {
        "id": "14_Neural_ODEs_p13_eq31_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "English underbrace labels plus cancel marks",
    },
    {
        "id": "20_TRPO_p10_eq33_h",
        "action": "verify",
        "gold_latex_raw": r"\mathbb{E}_{s_{t}\sim\tilde{\pi}}[\bar{A}(s_{t})]=P(n_{t}=0)\mathbb{E}_{s_{t}\sim\tilde{\pi}|n_{t}=0}[\bar{A}(s_{t})]+P(n_{t}>0)\mathbb{E}_{s_{t}\sim\tilde{\pi}|n_{t}>0}[\bar{A}(s_{t})]",
        "equation_number": "33",
        "notes": "human_from_harvest; complete tilde-pi total expectation",
    },
    {
        "id": "20_TRPO_p10_eq34_h",
        "action": "verify",
        "gold_latex_raw": r"\mathbb{E}_{s_{t}\sim\pi}[\bar{A}(s_{t})]=P(n_{t}=0)\mathbb{E}_{s_{t}\sim\pi|n_{t}=0}[\bar{A}(s_{t})]+P(n_{t}>0)\mathbb{E}_{s_{t}\sim\pi|n_{t}>0}[\bar{A}(s_{t})]",
        "equation_number": "34",
        "notes": "human_from_harvest; complete pi total expectation",
    },
    {
        "id": "20_TRPO_p10_eq35_h",
        "action": "verify",
        "gold_latex_raw": r"\mathbb{E}_{s_{t}\sim\tilde{\pi}|n_{t}=0}[\bar{A}(s_{t})]=\mathbb{E}_{s_{t}\sim\pi|n_{t}=0}[\bar{A}(s_{t})]",
        "equation_number": "35",
        "notes": "human_from_harvest; complete agree-on-prefix identity",
    },
    {
        "id": "20_TRPO_p10_eq36_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "By definition of alpha sentence below (36)",
    },
    {
        "id": "20_TRPO_p10_eq37_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "By definition of alpha sentence above (37)",
    },
    {
        "id": "27_DDPM_p3_eq13_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "decoder sentence plus two delta piecewise defs around (13)",
    },
    {
        "id": "27_DDPM_p4_eq14_h",
        "action": "verify",
        "gold_latex_raw": r"L_{\mathrm{simple}}(\theta):=\mathbb{E}_{t,\mathbf{x}_{0},\boldsymbol{\epsilon}}\left[\|\boldsymbol{\epsilon}-\boldsymbol{\epsilon}_{\theta}(\sqrt{\bar{\alpha}_{t}}\mathbf{x}_{0}+\sqrt{1-\bar{\alpha}_{t}}\boldsymbol{\epsilon},t)\|^{2}\right]",
        "equation_number": "14",
        "notes": "human_from_harvest; complete expanded L_simple",
    },
    {
        "id": "27_DDPM_p6_eq15_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "tops of the following prose line under (15)",
    },
    {
        "id": "27_DDPM_p6_eq16_h",
        "action": "verify",
        "gold_latex_raw": r"L=D_{\mathrm{KL}}(q(\mathbf{x}_{T})\|p(\mathbf{x}_{T}))+\mathbb{E}_{q}\left[\sum_{t\geq 1}D_{\mathrm{KL}}(q(\mathbf{x}_{t-1}|\mathbf{x}_{t})\|p_{\theta}(\mathbf{x}_{t-1}|\mathbf{x}_{t}))\right]+H(\mathbf{x}_{0})",
        "equation_number": "16",
        "notes": "human_from_harvest; complete reduced ELBO",
    },
    {
        "id": "27_DDPM_p12_eq17_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "top of the next display bracket under (17)",
    },
    {
        "id": "29_Latent_Diffusion_Models_p16_eq14_h",
        "action": "verify",
        "gold_latex_raw": r"\epsilon_{\theta}(x_{t},t)=(x_{t}-\alpha_{t}x_{\theta}(x_{t},t))/\sigma_{t}",
        "equation_number": "14",
        "notes": "human_from_harvest; complete noise from x-pred",
    },
    {
        "id": "29_Latent_Diffusion_Models_p16_eq15_h",
        "action": "verify",
        "gold_latex_raw": r"\|x_{0}-x_{\theta}(\alpha_{t}x_{0}+\sigma_{t}\epsilon,t)\|^{2}=\frac{\sigma_{t}^{2}}{\alpha_{t}^{2}}\|\epsilon-\epsilon_{\theta}(\alpha_{t}x_{0}+\sigma_{t}\epsilon,t)\|^{2}",
        "equation_number": "15",
        "notes": "human_from_harvest; complete x-pred vs eps-pred identity",
    },
    {
        "id": "29_Latent_Diffusion_Models_p17_eq16_h",
        "action": "verify",
        "gold_latex_raw": r"\hat{\epsilon}\leftarrow\epsilon_{\theta}(z_{t},t)+\sqrt{1-\alpha_{t}^{2}}\nabla_{z_{t}}\log p_{\Phi}(y|z_{t})",
        "equation_number": "16",
        "notes": "human_from_harvest; complete classifier-guided noise",
    },
    {
        "id": "29_Latent_Diffusion_Models_p18_eq17_h",
        "action": "verify",
        "gold_latex_raw": r"\log p_{\Phi}(y|z_{t})=-\frac{1}{2}\|y-T(\mathcal{D}(z_{0}(z_{t})))\|_{2}^{2}",
        "equation_number": "17",
        "notes": "human_from_harvest; complete classifier log-likelihood",
    },
    {
        "id": "29_Latent_Diffusion_Models_p24_eq18_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "assignment (18) plus following for-loop header",
    },
    {
        "id": "31_Vision_Transformer_p3_eq2_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "captures numbered ViT (1)(2)(3)",
    },
    {
        "id": "31_Vision_Transformer_p3_eq3_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "captures numbered ViT (2)(3)(4)",
    },
    {
        "id": "31_Vision_Transformer_p3_eq4_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "captures numbered ViT (3) and (4)",
    },
    {
        "id": "31_Vision_Transformer_p12_eq5_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "captures numbered (5) and (6)",
    },
    {
        "id": "31_Vision_Transformer_p12_eq6_h",
        "action": "verify",
        "gold_latex_raw": r"A=\mathrm{softmax}(\mathbf{q}\mathbf{k}^{\top}/\sqrt{D_{h}})\quad A\in\mathbb{R}^{N\times N}",
        "equation_number": "6",
        "notes": "human_from_harvest; complete attention matrix",
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
    spec["created_at"] = "2026-08-23T16:55:00"
    v = sum(1 for r in NEW if r["action"] == "verify")
    r = sum(1 for r in NEW if r["action"] == "reject")
    PATH.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print({"added": added, "verify": v, "reject": r, "total_reviews": len(spec["reviews"])})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
