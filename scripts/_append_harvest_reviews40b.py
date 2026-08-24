# -*- coding: utf-8 -*-
"""Append harvest reviews for harvest-340 batch (40). Do not train."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path("benchmarks/gold/human_reviews_harvest.json")

NEW = [
    {
        "id": "14_Neural_ODEs_p14_eq37_h",
        "action": "verify",
        "gold_latex_raw": r"\mathbf{z}(t+\varepsilon)=\int_{t}^{t+\varepsilon}f(\mathbf{z}(t),t,\theta)dt+\mathbf{z}(t)=T_{\varepsilon}(\mathbf{z}(t),t)",
        "equation_number": "37",
        "notes": "human_from_harvest; complete Euler flow map",
    },
    {
        "id": "14_Neural_ODEs_p14_eq38_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "or-joined pair plus proof sentence below (38)",
    },
    {
        "id": "14_Neural_ODEs_p14_eq39_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "The proof of (35) lead-in above the limit",
    },
    {
        "id": "14_Neural_ODEs_p14_eq40_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "captures numbered (40) and (41) with annotations",
    },
    {
        "id": "14_Neural_ODEs_p14_eq41_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "(41) plus following expanded numerator",
    },
    {
        "id": "20_TRPO_p11_eq43_h",
        "action": "verify",
        "gold_latex_raw": r"=4\epsilon\alpha\left(\frac{1}{1-\gamma}-\frac{1}{1-\gamma(1-\alpha)}\right)",
        "equation_number": "43",
        "notes": "human_from_harvest; complete geometric-sum closed form",
    },
    {
        "id": "20_TRPO_p11_eq44_h",
        "action": "verify",
        "gold_latex_raw": r"=\frac{4\alpha^{2}\gamma\epsilon}{(1-\gamma)(1-\gamma(1-\alpha))}",
        "equation_number": "44",
        "notes": "human_from_harvest; complete combined fraction",
    },
    {
        "id": "20_TRPO_p11_eq45_h",
        "action": "verify",
        "gold_latex_raw": r"\leq\frac{4\alpha^{2}\gamma\epsilon}{(1-\gamma)^{2}}",
        "equation_number": "45",
        "notes": "human_from_harvest; complete looser gamma bound",
    },
    {
        "id": "20_TRPO_p11_eq46_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "Proof paragraph defining G/G-tilde above (46)",
    },
    {
        "id": "20_TRPO_p11_eq47_h",
        "action": "verify",
        "gold_latex_raw": r"\tilde{G}=G+\gamma G\Delta\tilde{G}",
        "equation_number": "47",
        "notes": "human_from_harvest; complete resolvent identity",
    },
    {
        "id": "27_DDPM_p13_eq23_h",
        "action": "verify",
        "gold_latex_raw": r"L=\mathbb{E}_{q}\left[-\log p(\mathbf{x}_{T})-\sum_{t\geq 1}\log\frac{p_{\theta}(\mathbf{x}_{t-1}|\mathbf{x}_{t})}{q(\mathbf{x}_{t}|\mathbf{x}_{t-1})}\right]",
        "equation_number": "23",
        "notes": "human_from_harvest; complete appendix ELBO start",
    },
    {
        "id": "27_DDPM_p13_eq24_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "top of the next display bracket under (24)",
    },
    {
        "id": "27_DDPM_p13_eq25_h",
        "action": "verify",
        "gold_latex_raw": r"=\mathbb{E}_{q}\left[-\log\frac{p(\mathbf{x}_{T})}{q(\mathbf{x}_{T})}-\sum_{t\geq 1}\log\frac{p_{\theta}(\mathbf{x}_{t-1}|\mathbf{x}_{t})}{q(\mathbf{x}_{t-1}|\mathbf{x}_{t})}-\log q(\mathbf{x}_{0})\right]",
        "equation_number": "25",
        "notes": "human_from_harvest; complete telescoped ELBO",
    },
    {
        "id": "27_DDPM_p13_eq26_h",
        "action": "verify",
        "gold_latex_raw": r"=D_{\mathrm{KL}}(q(\mathbf{x}_{T})\|p(\mathbf{x}_{T}))+\mathbb{E}_{q}\left[\sum_{t\geq 1}D_{\mathrm{KL}}(q(\mathbf{x}_{t-1}|\mathbf{x}_{t})\|p_{\theta}(\mathbf{x}_{t-1}|\mathbf{x}_{t}))\right]+H(\mathbf{x}_{0})",
        "equation_number": "26",
        "notes": "human_from_harvest; complete KL+entropy ELBO",
    },
    {
        "id": "29_Latent_Diffusion_Models_p24_eq24_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "shows numbered (23) with leftover (24)",
    },
    {
        "id": "29_Latent_Diffusion_Models_p28_eq25_h",
        "action": "verify",
        "gold_latex_raw": r"L_{\mathrm{Autoencoder}}=\min_{\mathcal{E},\mathcal{D}}\max_{\psi}\left(L_{\mathrm{rec}}(x,\mathcal{D}(\mathcal{E}(x)))-L_{\mathrm{adv}}(\mathcal{D}(\mathcal{E}(x)))+\log D_{\psi}(x)+L_{\mathrm{reg}}(x;\mathcal{E},\mathcal{D})\right)",
        "equation_number": "25",
        "notes": "human_from_harvest; complete autoencoder min-max",
    },
    {
        "id": "38_Chinchilla_p6_eq4_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "where/and chain of five defs on one line",
    },
    {
        "id": "38_Chinchilla_p23_eq5_h",
        "action": "verify",
        "gold_latex_raw": r"\hat{L}(N,D)\triangleq E+\frac{A}{N^{\alpha}}+\frac{B}{D^{\beta}}",
        "equation_number": "5",
        "notes": "human_from_harvest; complete parametric loss form",
    },
    {
        "id": "38_Chinchilla_p23_eq6_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "two defs joined by and set",
    },
    {
        "id": "38_Chinchilla_p23_eq7_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "restricted functional space sentence above (7)",
    },
    {
        "id": "38_Chinchilla_p24_eq8_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "two defs joined by setting",
    },
    {
        "id": "39_PaLM_p11_eq1_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "TriviaQA table row, not a display equation",
    },
    {
        "id": "39_PaLM_p11_eq64_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "benchmark table scores, not a display equation",
    },
    {
        "id": "39_PaLM_p11_eq15_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "Lambada/HellaSwag table scores",
    },
    {
        "id": "39_PaLM_p11_eq8_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "Lambada/HellaSwag table scores",
    },
    {
        "id": "39_PaLM_p11_eq20_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "Lambada/HellaSwag table scores",
    },
    {
        "id": "42_DPO_p2_eq1_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "static-dataset sentence below Bradley-Terry (1)",
    },
    {
        "id": "42_DPO_p2_eq2_h",
        "action": "verify",
        "gold_latex_raw": r"\mathcal{L}_{R}(r_{\phi},\mathcal{D})=-\mathbb{E}_{(x,y_{w},y_{l})\sim\mathcal{D}}[\log\sigma(r_{\phi}(x,y_{w})-r_{\phi}(x,y_{l}))]",
        "equation_number": "2",
        "notes": "human_from_harvest; complete reward BT loss",
    },
    {
        "id": "42_DPO_p2_eq3_h",
        "action": "verify",
        "gold_latex_raw": r"\max_{\pi_{\theta}}\mathbb{E}_{x\sim\mathcal{D},y\sim\pi_{\theta}(y|x)}[r_{\phi}(x,y)]-\beta D_{\mathrm{KL}}[\pi_{\theta}(y|x)\|\pi_{\mathrm{ref}}(y|x)]",
        "equation_number": "3",
        "notes": "human_from_harvest; complete KL-constrained RL",
    },
    {
        "id": "42_DPO_p3_eq4_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "takes the form lead-in and where Z(x) below (4)",
    },
    {
        "id": "42_DPO_p3_eq5_h",
        "action": "verify",
        "gold_latex_raw": r"r(x,y)=\beta\log\frac{\pi_{r}(y|x)}{\pi_{\mathrm{ref}}(y|x)}+\beta\log Z(x)",
        "equation_number": "5",
        "notes": "human_from_harvest; complete reward reparameterization",
    },
    {
        "id": "43_FlashAttention_p17_eq1_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq", "prose_contaminated"],
        "notes": "S/P/O defs plus Define sentence above L_i",
    },
    {
        "id": "43_FlashAttention_p17_eq2_h",
        "action": "verify",
        "gold_latex_raw": r"o_{i}=P_{i:}\mathbf{V}=\sum_{j}P_{ij}v_{j}=\sum_{j}\frac{e^{q_{i}^{T}k_{j}}}{L_{i}}v_{j}",
        "equation_number": "2",
        "notes": "human_from_harvest; complete attention output",
    },
    {
        "id": "43_FlashAttention_p17_eq3_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "dV autodiff sentence above (3)",
    },
    {
        "id": "43_FlashAttention_p18_eq4_h",
        "action": "verify",
        "gold_latex_raw": r"D_{i}=P_{i:}^{T}dP_{i:}=\sum_{j}\frac{e^{q_{i}^{T}k_{j}}}{L_{i}}do_{i}^{T}v_{j}=do_{i}^{T}\sum_{j}\frac{e^{q_{i}^{T}k_{j}}}{L_{i}}v_{j}=do_{i}^{T}o_{i}",
        "equation_number": "4",
        "notes": "human_from_harvest; complete softmax Jacobian scalar",
    },
    {
        "id": "43_FlashAttention_p18_eq5_h",
        "action": "verify",
        "gold_latex_raw": r"dq_{i}=\sum_{j}dS_{ij}k_{j}=\sum_{j}P_{ij}(dP_{ij}-D_{i})k_{j}=\sum_{j}\frac{e^{q_{i}^{T}k_{j}}}{L_{i}}(do_{i}^{T}v_{j}-D_{i})k_{j}",
        "equation_number": "5",
        "notes": "human_from_harvest; complete dq backward",
    },
    {
        "id": "44_FlashAttention2_p3_eq1_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "three stacked softmax-split lines, no single number",
    },
    {
        "id": "44_FlashAttention2_p3_eq2_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "split O concatenation fragment",
    },
    {
        "id": "44_FlashAttention2_p5_eq2_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "online softmax update block",
    },
    {
        "id": "44_FlashAttention2_p5_eq0_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "algorithm prose plus init, not a display eq",
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
    spec["created_at"] = "2026-08-23T17:15:00"
    v = sum(1 for r in NEW if r["action"] == "verify")
    r = sum(1 for r in NEW if r["action"] == "reject")
    PATH.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print({"added": added, "verify": v, "reject": r, "total_reviews": len(spec["reviews"])})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
