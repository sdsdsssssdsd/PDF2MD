# -*- coding: utf-8 -*-
"""Append this batch of harvest reviews. Do not train. Do not copy machine_pred."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path("benchmarks/gold/human_reviews_harvest.json")

NEW = [
    {
        "id": "04_Auto_Encoding_Variational_Bayes_p11_eq13_h",
        "action": "verify",
        "gold_latex_raw": r"\log p_{\alpha}(\mathbf{X})=D_{KL}(q_{\phi}(\boldsymbol{\theta})||p_{\alpha}(\boldsymbol{\theta}|\mathbf{X}))+\mathcal{L}(\phi;\mathbf{X})",
        "equation_number": "13",
        "notes": "human_from_harvest; complete VAE marginal split",
    },
    {
        "id": "04_Auto_Encoding_Variational_Bayes_p11_eq14_h",
        "action": "verify",
        "gold_latex_raw": r"\mathcal{L}(\phi;\mathbf{X})=\int q_{\phi}(\boldsymbol{\theta})(\log p_{\boldsymbol{\theta}}(\mathbf{X})+\log p_{\boldsymbol{\alpha}}(\boldsymbol{\theta})-\log q_{\phi}(\boldsymbol{\theta}))\,d\boldsymbol{\theta}",
        "equation_number": "14",
        "notes": "human_from_harvest; complete variational integral",
    },
    {
        "id": "04_Auto_Encoding_Variational_Bayes_p11_eq15_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "lead-in sentence plus inline sum above display (15)",
    },
    {
        "id": "13_Deep_Sets_p12_eq12_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq", "prose_contaminated"],
        "notes": "Newton-Girard prose plus two determinant blocks under (12)",
    },
    {
        "id": "13_Deep_Sets_p12_eq13_h",
        "action": "verify",
        "gold_latex_raw": r"Z_{q}:=E_{q}(X):=\sum_{m=1}^{M}(x_{m})^{q},\quad q=0,\dots,M.",
        "equation_number": "13",
        "notes": "human_from_harvest; complete power-sum definition",
    },
    {
        "id": "13_Deep_Sets_p13_eq14_h",
        "action": "verify",
        "gold_latex_raw": r"P_{u}(x)=\prod_{m=1}^{M}(x-u_{m})",
        "equation_number": "14",
        "notes": "human_from_harvest; complete monic product",
    },
    {
        "id": "14_Neural_ODEs_p12_eq15_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "lead-in sentence above change-of-variables limit",
    },
    {
        "id": "14_Neural_ODEs_p12_eq16_h",
        "action": "verify",
        "gold_latex_raw": r"=-\lim_{\varepsilon\to 0^{+}}\frac{\log\left|\det\frac{\partial}{\partial\mathbf{z}}T_{\varepsilon}(\mathbf{z}(t))\right|}{\varepsilon}",
        "equation_number": "16",
        "notes": "human_from_harvest; complete log-det limit line",
    },
    {
        "id": "14_Neural_ODEs_p12_eq17_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "captures numbered (17) and (18) plus L'Hopital gloss",
    },
    {
        "id": "19_PPO_p4_eq10_h",
        "action": "verify",
        "gold_latex_raw": r"\hat{A}_{t}=-V(s_{t})+r_{t}+\gamma r_{t+1}+\cdots+\gamma^{T-t+1}r_{T-1}+\gamma^{T-t}V(s_{T})",
        "equation_number": "10",
        "notes": "human_from_harvest; complete GAE unroll",
    },
    {
        "id": "19_PPO_p4_eq11_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq", "prose_contaminated"],
        "notes": "lead-in plus numbered (11) and (12)",
    },
    {
        "id": "19_PPO_p4_eq12_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq", "prose_contaminated"],
        "notes": "same block as eq11; (11)+(12) plus where",
    },
    {
        "id": "20_TRPO_p9_eq20_h",
        "action": "verify",
        "gold_latex_raw": r"\mathbb{E}_{\tau|\tilde{\pi}}\left[\sum_{t=0}^{\infty}\gamma^{t}A_{\pi}(s_{t},a_{t})\right]",
        "equation_number": "20",
        "notes": "human_from_harvest; complete advantage expectation",
    },
    {
        "id": "20_TRPO_p9_eq21_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "top edge of previous display bracket still in crop",
    },
    {
        "id": "20_TRPO_p9_eq22_h",
        "action": "verify",
        "gold_latex_raw": r"=\mathbb{E}_{\tau|\tilde{\pi}}\left[-V_{\pi}(s_{0})+\sum_{t=0}^{\infty}\gamma^{t}r(s_{t})\right]",
        "equation_number": "22",
        "notes": "human_from_harvest; complete telescoped return",
    },
    {
        "id": "22_Dueling_Networks_p3_eq8_h",
        "action": "verify",
        "gold_latex_raw": r"Q(s,a;\theta,\alpha,\beta)=V(s;\theta,\beta)+\left(A(s,a;\theta,\alpha)-\max_{a'\in|\mathcal{A}|}A(s,a';\theta,\alpha)\right)",
        "equation_number": "8",
        "notes": "human_from_harvest; complete dueling Q max-norm",
    },
    {
        "id": "23_DDPG_p2_eq4_h",
        "action": "verify",
        "gold_latex_raw": r"L(\theta^{Q})=\mathbb{E}_{s_{t}\sim\rho^{\beta},a_{t}\sim\beta,r_{t}\sim E}\left[(Q(s_{t},a_{t}|\theta^{Q})-y_{t})^{2}\right]",
        "equation_number": "4",
        "notes": "human_from_harvest; complete critic MSE",
    },
    {
        "id": "23_DDPG_p2_eq5_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "includes leading where before y_t target",
    },
    {
        "id": "23_DDPG_p2_eq6_h",
        "action": "verify",
        "gold_latex_raw": r"\nabla_{\theta^{\mu}}J\approx\mathbb{E}_{s_{t}\sim\rho^{\beta}}\left[\nabla_{\theta^{\mu}}Q(s,a|\theta^{Q})|_{s=s_{t},a=\mu(s_{t}|\theta^{\mu})}\right]=\mathbb{E}_{s_{t}\sim\rho^{\beta}}\left[\nabla_{a}Q(s,a|\theta^{Q})|_{s=s_{t},a=\mu(s_{t})}\nabla_{\theta^{\mu}}\mu(s|\theta^{\mu})|_{s=s_{t}}\right]",
        "equation_number": "6",
        "notes": "human_from_harvest; complete actor chain-rule gradient",
    },
    {
        "id": "24_Soft_Actor_Critic_p10_eq14_h",
        "action": "verify",
        "gold_latex_raw": r"J(\pi)=\sum_{t=0}^{\infty}\mathbb{E}_{(\mathbf{s}_{t},\mathbf{a}_{t})\sim\rho_{\pi}}\left[\sum_{l=t}^{\infty}\gamma^{l-t}\mathbb{E}_{\mathbf{s}_{l}\sim p,\mathbf{a}_{l}\sim\pi}\left[r(\mathbf{s}_{t},\mathbf{a}_{t})+\alpha\mathcal{H}(\pi(\cdot|\mathbf{s}_{t}))|\mathbf{s}_{t},\mathbf{a}_{t}\right]\right]",
        "equation_number": "14",
        "notes": "human_from_harvest; complete soft objective",
    },
    {
        "id": "24_Soft_Actor_Critic_p10_eq15_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "next-paragraph Sutton & Barto line under Q update",
    },
    {
        "id": "24_Soft_Actor_Critic_p10_eq16_h",
        "action": "verify",
        "gold_latex_raw": r"\pi_{\mathrm{new}}(\cdot|\mathbf{s}_{t})=\arg\min_{\pi'\in\Pi}\mathrm{D}_{\mathrm{KL}}(\pi'(\cdot|\mathbf{s}_{t})\|\exp(Q^{\pi_{\mathrm{old}}}(\mathbf{s}_{t},\cdot)-\log Z^{\pi_{\mathrm{old}}}(\mathbf{s}_{t})))=\arg\min_{\pi'\in\Pi}J_{\pi_{\mathrm{old}}}(\pi'(\cdot|\mathbf{s}_{t}))",
        "equation_number": "16",
        "notes": "human_from_harvest; complete policy KL projection",
    },
    {
        "id": "25_StyleGAN_p5_eq2_h",
        "action": "verify",
        "gold_latex_raw": r"l_{\mathcal{Z}}=\mathbb{E}\left[\frac{1}{\epsilon^{2}}d(G(\mathrm{slerp}(\mathbf{z}_{1},\mathbf{z}_{2};t)),G(\mathrm{slerp}(\mathbf{z}_{1},\mathbf{z}_{2};t+\epsilon)))\right]",
        "equation_number": "2",
        "notes": "human_from_harvest; complete slerp perceptual path",
    },
    {
        "id": "25_综合能源系统优化调度策略_p8_eq25_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "left-column Chinese plus two-line charge/discharge brace",
    },
    {
        "id": "25_综合能源系统优化调度策略_p8_eq26_h",
        "action": "verify",
        "gold_latex_raw": r"C_{\lambda}\mathrm{SOC}_{\lambda}^{\min}\leqslant E_{\lambda}(t)\leqslant C_{\lambda}\mathrm{SOC}_{\lambda}^{\max}",
        "equation_number": "26",
        "notes": "human_from_harvest; complete SOC box",
    },
    {
        "id": "25_综合能源系统优化调度策略_p8_eq27_h",
        "action": "verify",
        "gold_latex_raw": r"E_{\lambda}(0)=E_{\lambda}(T)",
        "equation_number": "27",
        "notes": "human_from_harvest; complete cyclic energy",
    },
    {
        "id": "26_StyleGAN2_p2_eq3_h",
        "action": "verify",
        "gold_latex_raw": r"w''_{ijk}=w'_{ijk}/\sqrt{\sum_{i,k}{w'_{ijk}}^{2}+\epsilon}",
        "equation_number": "3",
        "notes": "human_from_harvest; complete demodulation weight",
    },
    {
        "id": "26_StyleGAN2_p10_eq5_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "Path length regularization heading and paragraph above (5)",
    },
    {
        "id": "26_StyleGAN2_p17_eq8_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "left-column English merged with path-length integral",
    },
    {
        "id": "26_三相四桥臂逆变器控制策略_p3_eq13_h",
        "action": "reject",
        "crop_quality": ["clipped_left", "neighbor_eq"],
        "notes": "left-column clipped fraction beside u_NO",
    },
    {
        "id": "26_三相四桥臂逆变器控制策略_p3_eq14_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "Chinese caption under T_N plus left-column artifact",
    },
    {
        "id": "26_三相四桥臂逆变器控制策略_p3_eq15_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "left-column residue and neighboring (9) beside (15)",
    },
    {
        "id": "27_DDPM_p1_eq1_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "intro paragraph above two-part reverse-process (1)",
    },
    {
        "id": "27_DDPM_p1_eq2_h",
        "action": "verify",
        "gold_latex_raw": r"q(\mathbf{x}_{1:T}|\mathbf{x}_{0}):=\prod_{t=1}^{T}q(\mathbf{x}_{t}|\mathbf{x}_{t-1}),\quad q(\mathbf{x}_{t}|\mathbf{x}_{t-1}):=\mathcal{N}(\mathbf{x}_{t};\sqrt{1-\beta_{t}}\mathbf{x}_{t-1},\beta_{t}\mathbf{I})",
        "equation_number": "2",
        "notes": "human_from_harvest; complete forward diffusion",
    },
    {
        "id": "27_DDPM_p1_eq3_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "next-paragraph beta_t sentence under ELBO (3)",
    },
    {
        "id": "28_Improved_DDPM_p1_eq8_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq", "prose_contaminated"],
        "notes": "lead-in plus numbered (8) and (9)",
    },
    {
        "id": "28_Improved_DDPM_p1_eq9_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq", "prose_contaminated"],
        "notes": "same block as eq8; (8)+(9)",
    },
    {
        "id": "28_Improved_DDPM_p1_eq10_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "captures (10) and clipped (11)",
    },
    {
        "id": "29_Latent_Diffusion_Models_p3_eq2_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "backbone sentence under L_LDM (2)",
    },
    {
        "id": "29_Latent_Diffusion_Models_p4_eq3_h",
        "action": "verify",
        "gold_latex_raw": r"L_{LDM}:=\mathbb{E}_{\mathcal{E}(x),y,\epsilon\sim\mathcal{N}(0,1),t}\left[\|\epsilon-\epsilon_{\theta}(z_{t},t,\tau_{\theta}(y))\|_{2}^{2}\right]",
        "equation_number": "3",
        "notes": "human_from_harvest; complete conditional LDM loss",
    },
    {
        "id": "29_Latent_Diffusion_Models_p15_eq4_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "SNR lead-in sentences above forward process (4)",
    },
    {
        "id": "29_考虑候车时间均衡性的灵活编组方案优化_p2_eq5_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "captures numbered (4) and (5)",
    },
    {
        "id": "35_燃料理化特性与进气压力耦合对碳氢化合物排放的影响_p4_eq5_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "two Chinese explanation lines under P_i",
    },
    {
        "id": "38_基于组合赋权的装配式建筑成本影响因素研究_p2_eq11_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq", "prose_contaminated"],
        "notes": "entropy (11) plus p_ij/k definitions and Chinese",
    },
    {
        "id": "38_基于组合赋权的装配式建筑成本影响因素研究_p2_eq12_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq", "prose_contaminated"],
        "notes": "definitions, 计算熵权, (12), and d_j line",
    },
    {
        "id": "38_基于组合赋权的装配式建筑成本影响因素研究_p2_eq13_h",
        "action": "verify",
        "gold_latex_raw": r"w_{i}=\frac{w_{1}w_{2}w_{3}}{\sum_{n=1}^{n}w_{1}w_{2}w_{3}}",
        "equation_number": "13",
        "notes": "human_from_harvest; complete product-weight line as printed",
    },
    {
        "id": "46_二氧化碳加氢制甲醇研究进展_p3_eq111_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "DFT/MC surface-name sentence, not a display eq",
    },
    {
        "id": "47_副产氢金属氢化物分离法净化氢技术经济性分析_p3_eq3_h",
        "action": "reject",
        "crop_quality": ["clipped_left"],
        "notes": "numerator Chinese clipped at top",
    },
    {
        "id": "47_副产氢金属氢化物分离法净化氢技术经济性分析_p3_eq4_h",
        "action": "verify",
        "gold_latex_raw": r"\mathrm{LCOHP}=\frac{\mathrm{COST}_{\mathrm{total}}}{H_{\mathrm{total}}}",
        "equation_number": "4",
        "notes": "human_from_harvest; complete LCOHP ratio",
    },
    {
        "id": "47_副产氢金属氢化物分离法净化氢技术经济性分析_p3_eq5_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "left table labels plus 式中 under COST_total",
    },
    {
        "id": "48_Ni-CeO2纳米复合材料催化肼硼烷产氢性能分析_p3_eq111_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "TEM lattice figure with Ni(111) annotation",
    },
    {
        "id": "49_生命周期视角下氢的制取及其在化工领域的应用_p3_eq1_h",
        "action": "verify",
        "gold_latex_raw": r"\mathrm{C}+\mathrm{H}_{2}\mathrm{O}\rightarrow\mathrm{H}_{2}+\mathrm{CO}",
        "equation_number": "1",
        "notes": "human_from_harvest; complete water-gas reaction",
    },
    {
        "id": "49_生命周期视角下氢的制取及其在化工领域的应用_p3_eq2_h",
        "action": "verify",
        "gold_latex_raw": r"\mathrm{CO}+\mathrm{H}_{2}\mathrm{O}\rightarrow\mathrm{H}_{2}+\mathrm{CO}_{2}",
        "equation_number": "2",
        "notes": "human_from_harvest; complete water-gas shift",
    },
    {
        "id": "49_生命周期视角下氢的制取及其在化工领域的应用_p4_eq3_h",
        "action": "verify",
        "gold_latex_raw": r"\mathrm{CH}_{4}+\mathrm{H}_{2}\mathrm{O}\rightarrow\mathrm{CO}+3\mathrm{H}_{2}",
        "equation_number": "3",
        "notes": "human_from_harvest; complete steam reforming",
    },
    {
        "id": "50_低能耗电解水制氢耦合体系_p4_eq311_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "XRD peak figure, not a display eq",
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
    spec["created_at"] = "2026-08-23T16:40:00"
    v = sum(1 for r in NEW if r["action"] == "verify")
    r = sum(1 for r in NEW if r["action"] == "reject")
    PATH.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print({"added": added, "verify": v, "reject": r, "total_reviews": len(spec["reviews"])})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
