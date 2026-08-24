# -*- coding: utf-8 -*-
"""Append harvest reviews for the per-paper-4 batch. Do not train."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path("benchmarks/gold/human_reviews_harvest.json")

NEW = [
    {
        "id": "04_Auto_Encoding_Variational_Bayes_p12_eq16_h",
        "action": "verify",
        "gold_latex_raw": r"\mathcal{L}(\boldsymbol{\theta},\phi;\mathbf{x}^{(i)})=\int q_{\phi}(\mathbf{z}|\mathbf{x})\left(\log p_{\boldsymbol{\theta}}(\mathbf{x}^{(i)}|\mathbf{z})+\log p_{\boldsymbol{\theta}}(\mathbf{z})-\log q_{\phi}(\mathbf{z}|\mathbf{x})\right)d\mathbf{z}",
        "equation_number": "16",
        "notes": "human_from_harvest; complete ELBO integral",
    },
    {
        "id": "04_Auto_Encoding_Variational_Bayes_p12_eq17_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "reparameterize sentence above and where-line below (17)",
    },
    {
        "id": "04_Auto_Encoding_Variational_Bayes_p12_eq18_h",
        "action": "verify",
        "gold_latex_raw": r"\mathcal{L}(\boldsymbol{\theta},\phi;\mathbf{x}^{(i)})=\int q_{\phi}(\mathbf{z}|\mathbf{x})\left(\log p_{\boldsymbol{\theta}}(\mathbf{x}^{(i)}|\mathbf{z})+\log p_{\boldsymbol{\theta}}(\mathbf{z})-\log q_{\phi}(\mathbf{z}|\mathbf{x})\right)d\mathbf{z}=\int p(\boldsymbol{\epsilon})\left(\log p_{\boldsymbol{\theta}}(\mathbf{x}^{(i)}|\mathbf{z})+\log p_{\boldsymbol{\theta}}(\mathbf{z})-\log q_{\phi}(\mathbf{z}|\mathbf{x})\right)\big|_{\mathbf{z}=g_{\phi}(\boldsymbol{\epsilon},\mathbf{x}^{(i)})}d\boldsymbol{\epsilon}",
        "equation_number": "18",
        "notes": "human_from_harvest; complete reparam ELBO",
    },
    {
        "id": "04_Auto_Encoding_Variational_Bayes_p12_eq19_h",
        "action": "verify",
        "gold_latex_raw": r"\widetilde{\boldsymbol{\theta}}=h_{\phi}(\boldsymbol{\zeta})\ \mathrm{with}\ \boldsymbol{\zeta}\sim p(\boldsymbol{\zeta})",
        "equation_number": "19",
        "notes": "human_from_harvest; complete parameter reparam",
    },
    {
        "id": "13_Deep_Sets_p13_eq15_h",
        "action": "verify",
        "gold_latex_raw": r"P_{u}(x)=x^{M}-a_{1}x^{M-1}+\cdots(-1)^{M-1}a_{M-1}x+(-1)^{M}a_{M}",
        "equation_number": "15",
        "notes": "human_from_harvest; complete elementary-symmetric poly",
    },
    {
        "id": "13_Deep_Sets_p13_eq16_h",
        "action": "verify",
        "gold_latex_raw": r"a_{m}=\sum_{1\le j_{1}<j_{2}<\dots<j_{m}\le M}u_{j_{1}}u_{j_{2}}\cdots u_{j_{m}}",
        "equation_number": "16",
        "notes": "human_from_harvest; complete elementary symmetric sum",
    },
    {
        "id": "13_Deep_Sets_p13_eq17_h",
        "action": "verify",
        "gold_latex_raw": r"a_{m}=\frac{1}{m}\det\begin{pmatrix}z_{1}&1&0&0&\cdots&0\\z_{2}&z_{1}&1&0&\cdots&0\\z_{3}&z_{2}&z_{1}&1&\cdots&0\\\vdots&\vdots&\vdots&\vdots&\ddots&\vdots\\z_{m-1}&z_{m-2}&z_{m-3}&z_{m-4}&\cdots&1\\z_{m}&z_{m-1}&z_{m-2}&z_{m-3}&\cdots&z_{1}\end{pmatrix}",
        "equation_number": "17",
        "notes": "human_from_harvest; complete Newton-Girard det",
    },
    {
        "id": "13_Deep_Sets_p13_eq18_h",
        "action": "verify",
        "gold_latex_raw": r"f(x_{1},\dots,x_{M})=\rho\left(\sum_{m=1}^{M}\phi(x_{m})\right)",
        "equation_number": "18",
        "notes": "human_from_harvest; complete Deep Sets form",
    },
    {
        "id": "14_Neural_ODEs_p12_eq18_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "captures numbered (17) and (18)",
    },
    {
        "id": "14_Neural_ODEs_p12_eq19_h",
        "action": "verify",
        "gold_latex_raw": r"=-\underbrace{\left(\lim_{\varepsilon\to 0^{+}}\frac{\partial}{\partial\varepsilon}\left|\det\frac{\partial}{\partial\mathbf{z}}T_{\varepsilon}(\mathbf{z}(t))\right|\right)}_{\mathrm{bounded}}\underbrace{\left(\lim_{\varepsilon\to 0^{+}}\frac{1}{\left|\det\frac{\partial}{\partial\mathbf{z}}T_{\varepsilon}(\mathbf{z}(t))\right|}\right)}_{=1}",
        "equation_number": "19",
        "notes": "human_from_harvest; complete underbrace split",
    },
    {
        "id": "14_Neural_ODEs_p12_eq20_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "top edge of previous underbrace labels still in crop",
    },
    {
        "id": "14_Neural_ODEs_p12_eq21_h",
        "action": "verify",
        "gold_latex_raw": r"\frac{\partial\log p(\mathbf{z}(t))}{\partial t}=-\lim_{\varepsilon\to 0^{+}}\mathrm{tr}\left(\mathrm{adj}\left(\frac{\partial}{\partial\mathbf{z}}T_{\varepsilon}(\mathbf{z}(t))\right)\frac{\partial}{\partial\varepsilon}\frac{\partial}{\partial\mathbf{z}}T_{\varepsilon}(\mathbf{z}(t))\right)",
        "equation_number": "21",
        "notes": "human_from_harvest; complete instantaneous change-of-var",
    },
    {
        "id": "15_具有可变延时的四元数神经网络的指数稳定性_p3_eq9_h",
        "action": "reject",
        "crop_quality": ["clipped_left"],
        "notes": "left-clipped tail of a multi-line z_j term",
    },
    {
        "id": "20_TRPO_p9_eq23_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "top fragments of previous display line",
    },
    {
        "id": "20_TRPO_p9_eq24_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "previous bracket/t=0 residue above eta line",
    },
    {
        "id": "20_TRPO_p9_eq25_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "Define A-bar sentence above (25)",
    },
    {
        "id": "20_TRPO_p9_eq26_h",
        "action": "verify",
        "gold_latex_raw": r"\eta(\tilde{\pi})=\eta(\pi)+\mathbb{E}_{\tau\sim\tilde{\pi}}\left[\sum_{t=0}^{\infty}\gamma^{t}\bar{A}(s_{t})\right]",
        "equation_number": "26",
        "notes": "human_from_harvest; complete performance difference",
    },
    {
        "id": "23_DDPG_p3_eq7_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "lead-in 'noise process' sentence above mu'",
    },
    {
        "id": "24_Soft_Actor_Critic_p10_eq18_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq", "prose_contaminated"],
        "notes": "(18) plus following Bellman derivation",
    },
    {
        "id": "24_Soft_Actor_Critic_p10_eq19_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "soft Bellman chain plus following paragraph",
    },
    {
        "id": "24_Soft_Actor_Critic_p11_eq20_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "support/density sentence above Jacobian",
    },
    {
        "id": "24_Soft_Actor_Critic_p11_eq21_h",
        "action": "verify",
        "gold_latex_raw": r"\log\pi(\mathbf{a}|\mathbf{s})=\log\mu(\mathbf{u}|\mathbf{s})-\sum_{i=1}^{D}\log(1-\tanh^{2}(u_{i}))",
        "equation_number": "21",
        "notes": "human_from_harvest; complete tanh Jacobian log-det",
    },
    {
        "id": "25_综合能源系统优化调度策略_p8_eq28_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "left-column Chinese beside ramp inequality",
    },
    {
        "id": "26_StyleGAN2_p17_eq9_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "left-column Jacobian text merged with path integral",
    },
    {
        "id": "27_DDPM_p1_eq4_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "alpha definitions sentence above q(x_t|x_0)",
    },
    {
        "id": "27_DDPM_p2_eq5_h",
        "action": "verify",
        "gold_latex_raw": r"\mathbb{E}_{q}\left[\underbrace{D_{\mathrm{KL}}(q(\mathbf{x}_{T}|\mathbf{x}_{0})\|p(\mathbf{x}_{T}))}_{L_{T}}+\sum_{t>1}\underbrace{D_{\mathrm{KL}}(q(\mathbf{x}_{t-1}|\mathbf{x}_{t},\mathbf{x}_{0})\|p_{\theta}(\mathbf{x}_{t-1}|\mathbf{x}_{t}))}_{L_{t-1}}-\underbrace{\log p_{\theta}(\mathbf{x}_{0}|\mathbf{x}_{1})}_{L_{0}}\right]",
        "equation_number": "5",
        "notes": "human_from_harvest; complete DDPM ELBO split",
    },
    {
        "id": "27_DDPM_p2_eq6_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq", "prose_contaminated"],
        "notes": "conditioned-on sentence plus (6) and (7)",
    },
    {
        "id": "27_DDPM_p2_eq7_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq", "prose_contaminated"],
        "notes": "same (6)+(7) block plus following sentence",
    },
    {
        "id": "28_Improved_DDPM_p1_eq11_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "captures numbered (10)(11)(12)",
    },
    {
        "id": "28_Improved_DDPM_p1_eq12_h",
        "action": "verify",
        "gold_latex_raw": r"q(x_{t-1}|x_{t},x_{0})=\mathcal{N}(x_{t-1};\tilde{\mu}(x_{t},x_{0}),\tilde{\beta}_{t}\mathbf{I})",
        "equation_number": "12",
        "notes": "human_from_harvest; complete posterior Gaussian",
    },
    {
        "id": "28_Improved_DDPM_p1_eq13_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "two sentences about predicting epsilon above mu_theta",
    },
    {
        "id": "28_Improved_DDPM_p1_eq14_h",
        "action": "verify",
        "gold_latex_raw": r"L_{\mathrm{simple}}=\mathbb{E}_{t,x_{0},\epsilon}\left[\|\epsilon-\epsilon_{\theta}(x_{t},t)\|^{2}\right]",
        "equation_number": "14",
        "notes": "human_from_harvest; complete L_simple",
    },
    {
        "id": "29_Latent_Diffusion_Models_p15_eq5_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "captures numbered (5) and (6)",
    },
    {
        "id": "29_Latent_Diffusion_Models_p15_eq6_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "same (5)+(6) block",
    },
    {
        "id": "29_Latent_Diffusion_Models_p15_eq7_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "captures (6) and (7); top of (6) clipped",
    },
    {
        "id": "29_Latent_Diffusion_Models_p15_eq8_h",
        "action": "verify",
        "gold_latex_raw": r"p(x_{0})=\int_{z}p(x_{T})\prod_{t=1}^{T}p(x_{t-1}|x_{t})",
        "equation_number": "8",
        "notes": "human_from_harvest; complete reverse-process integral",
    },
    {
        "id": "31_Vision_Transformer_p3_eq1_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "captures numbered ViT (1) and (2)",
    },
    {
        "id": "47_副产氢金属氢化物分离法净化氢技术经济性分析_p3_eq6_h",
        "action": "verify",
        "gold_latex_raw": r"C_{\mathrm{op},t}=Q_{\mathrm{gas},t}\times P_{\mathrm{gas},t}+Q_{\mathrm{e},t}\times P_{\mathrm{e},t}+Q_{\mathrm{cool},t}\times P_{\mathrm{cool},t}+C_{\mathrm{om},t}+C_{\mathrm{re},t}",
        "equation_number": "6",
        "notes": "human_from_harvest; complete operating-cost sum",
    },
    {
        "id": "49_生命周期视角下氢的制取及其在化工领域的应用_p4_eq4_h",
        "action": "verify",
        "gold_latex_raw": r"\mathrm{CO}+\mathrm{H}_{2}\mathrm{O}\rightarrow\mathrm{H}_{2}+\mathrm{CO}_{2}",
        "equation_number": "4",
        "notes": "human_from_harvest; complete water-gas shift reprint",
    },
    {
        "id": "49_生命周期视角下氢的制取及其在化工领域的应用_p6_eq6_h",
        "action": "verify",
        "gold_latex_raw": r"2\mathrm{H}_{2}\mathrm{O}+\mathrm{I}_{2}+\mathrm{SO}_{2}\rightarrow\mathrm{H}_{2}\mathrm{SO}_{4}+2\mathrm{HI}",
        "equation_number": "6",
        "notes": "human_from_harvest; complete Bunsen reaction",
    },
    {
        "id": "49_生命周期视角下氢的制取及其在化工领域的应用_p6_eq7_h",
        "action": "verify",
        "gold_latex_raw": r"2\mathrm{HI}\rightarrow\mathrm{H}_{2}+\mathrm{I}_{2}",
        "equation_number": "7",
        "notes": "human_from_harvest; complete HI decomposition",
    },
    {
        "id": "49_生命周期视角下氢的制取及其在化工领域的应用_p6_eq8_h",
        "action": "verify",
        "gold_latex_raw": r"\mathrm{H}_{2}\mathrm{SO}_{4}\rightarrow\mathrm{H}_{2}\mathrm{O}+\mathrm{SO}_{2}+\frac{1}{2}\mathrm{O}_{2}",
        "equation_number": "8",
        "notes": "human_from_harvest; complete sulfuric decomposition",
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
