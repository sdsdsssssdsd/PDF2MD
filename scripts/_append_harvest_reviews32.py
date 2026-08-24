# -*- coding: utf-8 -*-
"""Append harvest reviews for the per-paper-5 batch (32). Do not train."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path("benchmarks/gold/human_reviews_harvest.json")

NEW = [
    {
        "id": "04_Auto_Encoding_Variational_Bayes_p12_eq20_h",
        "action": "verify",
        "gold_latex_raw": r"\mathcal{L}(\phi;\mathbf{X})=\int q_{\phi}(\boldsymbol{\theta})(\log p_{\boldsymbol{\theta}}(\mathbf{X})+\log p_{\boldsymbol{\alpha}}(\boldsymbol{\theta})-\log q_{\phi}(\boldsymbol{\theta}))d\boldsymbol{\theta}=\int p(\boldsymbol{\zeta})(\log p_{\boldsymbol{\theta}}(\mathbf{X})+\log p_{\boldsymbol{\alpha}}(\boldsymbol{\theta})-\log q_{\phi}(\boldsymbol{\theta}))\big|_{\boldsymbol{\theta}=h_{\phi}(\boldsymbol{\zeta})}d\boldsymbol{\zeta}",
        "equation_number": "20",
        "notes": "human_from_harvest; complete hierarchical ELBO reparam",
    },
    {
        "id": "04_Auto_Encoding_Variational_Bayes_p12_eq21_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "shorthand sentence above and Monte Carlo sentence below (21)",
    },
    {
        "id": "04_Auto_Encoding_Variational_Bayes_p12_eq22_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "datapoint lead-in above MC estimate (22)",
    },
    {
        "id": "04_Auto_Encoding_Variational_Bayes_p12_eq23_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "two stacked Gaussian log-densities share one crop",
    },
    {
        "id": "13_Deep_Sets_p14_eq19_h",
        "action": "verify",
        "gold_latex_raw": r"f(x_{1},\dots,x_{M})=\rho\left(\sum_{m=1}^{M}\lambda_{m}\phi(x_{m})\right)",
        "equation_number": "19",
        "notes": "human_from_harvest; complete weighted Deep Sets form",
    },
    {
        "id": "13_Deep_Sets_p16_eq20_h",
        "action": "verify",
        "gold_latex_raw": r"f_{\Theta}(\mathbf{x})\doteq\sigma(\Theta\mathbf{x})\quad\Theta\in\mathbb{R}^{M\times M}",
        "equation_number": "20",
        "notes": "human_from_harvest; complete equivariant map plus domain",
    },
    {
        "id": "13_Deep_Sets_p17_eq21_h",
        "action": "verify",
        "gold_latex_raw": r"f_{\Theta}(\mathbf{x})=\sigma(\Theta\mathbf{x})",
        "equation_number": "21",
        "notes": "human_from_harvest; complete equivariant map",
    },
    {
        "id": "13_Deep_Sets_p18_eq23_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "maxpool factoring paragraph above (23)",
    },
    {
        "id": "13_Deep_Sets_p19_eq24_h",
        "action": "verify",
        "gold_latex_raw": r"p(X|\alpha)=\int d\theta\left[\prod_{m=1}^{M}p(x_{m}|\theta)\right]p(\theta|\alpha)",
        "equation_number": "24",
        "notes": "human_from_harvest; complete exchangeable likelihood integral",
    },
    {
        "id": "14_Neural_ODEs_p12_eq22_h",
        "action": "verify",
        "gold_latex_raw": r"=-\mathrm{tr}\left(\underbrace{\left(\lim_{\varepsilon\to 0^{+}}\mathrm{adj}\left(\frac{\partial}{\partial\mathbf{z}}T_{\varepsilon}(\mathbf{z}(t))\right)\right)}_{=I}\left(\lim_{\varepsilon\to 0^{+}}\frac{\partial}{\partial\varepsilon}\frac{\partial}{\partial\mathbf{z}}T_{\varepsilon}(\mathbf{z}(t))\right)\right)",
        "equation_number": "22",
        "notes": "human_from_harvest; complete adj=I split",
    },
    {
        "id": "14_Neural_ODEs_p12_eq23_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "previous underbrace =I residue above (23)",
    },
    {
        "id": "14_Neural_ODEs_p12_eq24_h",
        "action": "verify",
        "gold_latex_raw": r"\frac{\partial\log p(\mathbf{z}(t))}{\partial t}=-\mathrm{tr}\left(\lim_{\varepsilon\to 0^{+}}\frac{\partial}{\partial\varepsilon}\frac{\partial}{\partial\mathbf{z}}\left(\mathbf{z}+\varepsilon f(\mathbf{z}(t),t)+\mathcal{O}(\varepsilon^{2})+\mathcal{O}(\varepsilon^{3})+\ldots\right)\right)",
        "equation_number": "24",
        "notes": "human_from_harvest; complete flow expansion",
    },
    {
        "id": "14_Neural_ODEs_p12_eq25_h",
        "action": "verify",
        "gold_latex_raw": r"=-\mathrm{tr}\left(\lim_{\varepsilon\to 0^{+}}\frac{\partial}{\partial\varepsilon}\left(I+\frac{\partial}{\partial\mathbf{z}}\varepsilon f(\mathbf{z}(t),t)+\mathcal{O}(\varepsilon^{2})+\mathcal{O}(\varepsilon^{3})+\dots\right)\right)",
        "equation_number": "25",
        "notes": "human_from_harvest; complete I+Df expansion",
    },
    {
        "id": "14_Neural_ODEs_p12_eq26_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "previous-line fragments along the top edge",
    },
    {
        "id": "15_具有可变延时的四元数神经网络的指数稳定性_p3_eq10_h",
        "action": "reject",
        "crop_quality": ["clipped_left"],
        "notes": "left-clipped tail of a multi-line z_j term",
    },
    {
        "id": "15_具有可变延时的四元数神经网络的指数稳定性_p3_eq11_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq", "prose_contaminated"],
        "notes": "(11) plus following F/J definitions and 4n blocks",
    },
    {
        "id": "20_TRPO_p9_eq27_h",
        "action": "verify",
        "gold_latex_raw": r"L_{\pi}(\tilde{\pi})=\eta(\pi)+\mathbb{E}_{\tau\sim\pi}\left[\sum_{t=0}^{\infty}\gamma^{t}\bar{A}(s_{t})\right]",
        "equation_number": "27",
        "notes": "human_from_harvest; complete local approximation L",
    },
    {
        "id": "20_TRPO_p10_eq28_h",
        "action": "verify",
        "gold_latex_raw": r"|\bar{A}(s)|\leq 2\alpha\max_{s,a}|A_{\pi}(s,a)|",
        "equation_number": "28",
        "notes": "human_from_harvest; complete advantage coupling bound",
    },
    {
        "id": "20_TRPO_p10_eq29_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq", "prose_contaminated"],
        "notes": "(29) plus since-clause and numbered (30)",
    },
    {
        "id": "20_TRPO_p10_eq30_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "captures numbered (29)(30)(31)",
    },
    {
        "id": "20_TRPO_p10_eq31_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "captures numbered (30) and (31)",
    },
    {
        "id": "27_DDPM_p2_eq8_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq", "prose_contaminated"],
        "notes": "parameterization prose plus (8) and (9)",
    },
    {
        "id": "27_DDPM_p2_eq9_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq", "prose_contaminated"],
        "notes": "reparam sentence above (9) and top of (10)",
    },
    {
        "id": "27_DDPM_p2_eq10_h",
        "action": "verify",
        "gold_latex_raw": r"=\mathbb{E}_{\mathbf{x}_{0},\boldsymbol{\epsilon}}\left[\frac{1}{2\sigma_{t}^{2}}\left\|\frac{1}{\sqrt{\alpha_{t}}}\left(\mathbf{x}_{t}(\mathbf{x}_{0},\boldsymbol{\epsilon})-\frac{\beta_{t}}{\sqrt{1-\bar{\alpha}_{t}}}\boldsymbol{\epsilon}\right)-\boldsymbol{\mu}_{\theta}(\mathbf{x}_{t}(\mathbf{x}_{0},\boldsymbol{\epsilon}),t)\right\|^{2}\right]",
        "equation_number": "10",
        "notes": "human_from_harvest; complete expanded L_{t-1}",
    },
    {
        "id": "27_DDPM_p3_eq11_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "algorithms plus parameterization sentence around (11)",
    },
    {
        "id": "27_DDPM_p3_eq12_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "Langevin paragraph above and score-matching sentence below (12)",
    },
    {
        "id": "28_Improved_DDPM_p3_eq17_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "schedule-in-terms-of lead-in above cosine (17)",
    },
    {
        "id": "29_Latent_Diffusion_Models_p15_eq9_h",
        "action": "verify",
        "gold_latex_raw": r"-\log p(x_{0})\leq\mathrm{KL}(q(x_{T}|x_{0})|p(x_{T}))+\sum_{t=1}^{T}\mathbb{E}_{q(x_{t}|x_{0})}\mathrm{KL}(q(x_{t-1}|x_{t},x_{0})|p(x_{t-1}|x_{t}))",
        "equation_number": "9",
        "notes": "human_from_harvest; complete variational bound",
    },
    {
        "id": "29_Latent_Diffusion_Models_p15_eq10_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "captures numbered (10) and (11)",
    },
    {
        "id": "29_Latent_Diffusion_Models_p15_eq11_h",
        "action": "verify",
        "gold_latex_raw": r"=\mathcal{N}\left(x_{t-1}|\mu_{\theta}(x_{t},t),\sigma_{t|t-1}^{2}\frac{\sigma_{t-1}^{2}}{\sigma_{t}^{2}}\mathbf{I}\right)",
        "equation_number": "11",
        "notes": "human_from_harvest; complete reverse Gaussian",
    },
    {
        "id": "29_Latent_Diffusion_Models_p15_eq12_h",
        "action": "verify",
        "gold_latex_raw": r"\mu_{\theta}(x_{t},t)=\frac{\alpha_{t|t-1}\sigma_{t-1}^{2}}{\sigma_{t}^{2}}x_{t}+\frac{\alpha_{t-1}\sigma_{t|t-1}^{2}}{\sigma_{t}^{2}}x_{\theta}(x_{t},t)",
        "equation_number": "12",
        "notes": "human_from_harvest; complete reverse mean",
    },
    {
        "id": "29_Latent_Diffusion_Models_p16_eq13_h",
        "action": "verify",
        "gold_latex_raw": r"=\sum_{t=1}^{T}\mathbb{E}_{\mathcal{N}(\epsilon|0,\mathbf{I})}\frac{1}{2}(\mathrm{SNR}(t-1)-\mathrm{SNR}(t))\|x_{0}-x_{\theta}(\alpha_{t}x_{0}+\sigma_{t}\epsilon,t)\|^{2}",
        "equation_number": "13",
        "notes": "human_from_harvest; complete SNR-weighted reconstruction",
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
    spec["created_at"] = "2026-08-23T16:50:00"
    v = sum(1 for r in NEW if r["action"] == "verify")
    r = sum(1 for r in NEW if r["action"] == "reject")
    PATH.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print({"added": added, "verify": v, "reject": r, "total_reviews": len(spec["reviews"])})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
