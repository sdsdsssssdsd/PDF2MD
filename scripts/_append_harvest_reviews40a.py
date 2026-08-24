# -*- coding: utf-8 -*-
"""Append harvest reviews for harvest-300 batch (40). Do not train."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path("benchmarks/gold/human_reviews_harvest.json")

NEW = [
    {
        "id": "13_Deep_Sets_p19_eq30_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "abuse-of-notation paragraph below (30)",
    },
    {
        "id": "13_Deep_Sets_p19_eq31_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "three lead-in lines above two-line score (31)",
    },
    {
        "id": "13_Deep_Sets_p19_eq32_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "previous-line Gamma remainder above cases (32)",
    },
    {
        "id": "13_Deep_Sets_p20_eq33_h",
        "action": "verify",
        "gold_latex_raw": r"s(x|X)=1^{\top}\left[\sigma\left(\sum_{m=1}^{M}\phi(x_{m})+\phi(x)+\beta\right)-\sigma(\phi(x)+\beta)\right]",
        "equation_number": "33",
        "notes": "human_from_harvest; complete softmax-style score",
    },
    {
        "id": "13_Deep_Sets_p20_eq34_h",
        "action": "verify",
        "gold_latex_raw": r"s(x|X)=\sigma\left(\sum_{m=1}^{M}\phi(x_{m})+\phi(x)+\beta\right)-\sigma(\phi(x)+\beta)",
        "equation_number": "34",
        "notes": "human_from_harvest; complete sigmoid-style score",
    },
    {
        "id": "14_Neural_ODEs_p13_eq32_h",
        "action": "verify",
        "gold_latex_raw": r"\frac{\partial\log p(\mathbf{z}(t),t)}{\partial t}=\frac{1}{p(\mathbf{z}(t),t)}\frac{\partial p(\mathbf{z}(t),t)}{\partial t}=-\sum_{i=1}^{D}\frac{\partial f_{i}(\mathbf{z}(t),t)}{\partial\mathbf{z}_{i}}",
        "equation_number": "32",
        "notes": "human_from_harvest; complete log-density identity",
    },
    {
        "id": "14_Neural_ODEs_p13_eq33_h",
        "action": "verify",
        "gold_latex_raw": r"\frac{d}{dt}\begin{bmatrix}\mathbf{z}(t)\\\log p(\mathbf{z}(t),t)\end{bmatrix}=\begin{bmatrix}f(\mathbf{z}(t),t)\\-\sum_{i=1}^{D}\frac{\partial f_{i}(\mathbf{z}(t),t)}{\partial z_{i}}\end{bmatrix}",
        "equation_number": "33",
        "notes": "human_from_harvest; complete augmented NODE",
    },
    {
        "id": "14_Neural_ODEs_p14_eq34_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "Let z follow / we define adjoint sentences above (34)",
    },
    {
        "id": "14_Neural_ODEs_p14_eq35_h",
        "action": "verify",
        "gold_latex_raw": r"\frac{d\mathbf{a}(t)}{dt}=-\mathbf{a}(t)\frac{\partial f(\mathbf{z}(t),t,\theta)}{\partial\mathbf{z}(t)}",
        "equation_number": "35",
        "notes": "human_from_harvest; complete adjoint ODE",
    },
    {
        "id": "14_Neural_ODEs_p14_eq36_h",
        "action": "verify",
        "gold_latex_raw": r"\frac{dL}{d\mathbf{h}_{t}}=\frac{dL}{d\mathbf{h}_{t+1}}\frac{d\mathbf{h}_{t+1}}{d\mathbf{h}_{t}}",
        "equation_number": "36",
        "notes": "human_from_harvest; complete discrete chain rule",
    },
    {
        "id": "20_TRPO_p10_eq38_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "captures numbered (38) and (39)",
    },
    {
        "id": "20_TRPO_p10_eq39_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "same (38)+(39) bound chain",
    },
    {
        "id": "20_TRPO_p10_eq40_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "Plugging Equation lead-in above (40)",
    },
    {
        "id": "20_TRPO_p11_eq41_h",
        "action": "verify",
        "gold_latex_raw": r"|\eta(\tilde{\pi})-L_{\pi}(\tilde{\pi})|=\sum_{t=0}^{\infty}\gamma^{t}|\mathbb{E}_{\tau\sim\tilde{\pi}}[\bar{A}(s_{t})]-\mathbb{E}_{\tau\sim\pi}[\bar{A}(s_{t})]|",
        "equation_number": "41",
        "notes": "human_from_harvest; complete eta minus L identity",
    },
    {
        "id": "20_TRPO_p11_eq42_h",
        "action": "verify",
        "gold_latex_raw": r"\leq\sum_{t=0}^{\infty}\gamma^{t}\cdot 4\epsilon\alpha(1-(1-\alpha)^{t})",
        "equation_number": "42",
        "notes": "human_from_harvest; complete discounted bound series",
    },
    {
        "id": "27_DDPM_p12_eq18_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "top of the next display bracket under (18)",
    },
    {
        "id": "27_DDPM_p12_eq19_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "top of the next display bracket under (19)",
    },
    {
        "id": "27_DDPM_p12_eq20_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "next-line E/[ residue under (20)",
    },
    {
        "id": "27_DDPM_p12_eq21_h",
        "action": "verify",
        "gold_latex_raw": r"=\mathbb{E}_{q}\left[-\log\frac{p(\mathbf{x}_{T})}{q(\mathbf{x}_{T}|\mathbf{x}_{0})}-\sum_{t>1}\log\frac{p_{\theta}(\mathbf{x}_{t-1}|\mathbf{x}_{t})}{q(\mathbf{x}_{t-1}|\mathbf{x}_{t},\mathbf{x}_{0})}-\log p_{\theta}(\mathbf{x}_{0}|\mathbf{x}_{1})\right]",
        "equation_number": "21",
        "notes": "human_from_harvest; complete Bayes-rewritten ELBO",
    },
    {
        "id": "27_DDPM_p13_eq22_h",
        "action": "verify",
        "gold_latex_raw": r"=\mathbb{E}_{q}\left[D_{\mathrm{KL}}(q(\mathbf{x}_{T}|\mathbf{x}_{0})\|p(\mathbf{x}_{T}))+\sum_{t>1}D_{\mathrm{KL}}(q(\mathbf{x}_{t-1}|\mathbf{x}_{t},\mathbf{x}_{0})\|p_{\theta}(\mathbf{x}_{t-1}|\mathbf{x}_{t}))-\log p_{\theta}(\mathbf{x}_{0}|\mathbf{x}_{1})\right]",
        "equation_number": "22",
        "notes": "human_from_harvest; complete KL form of ELBO",
    },
    {
        "id": "29_Latent_Diffusion_Models_p24_eq19_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "for-loop plus numbered (19) and (20)",
    },
    {
        "id": "29_Latent_Diffusion_Models_p24_eq20_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "algorithm block with neighboring assignments",
    },
    {
        "id": "29_Latent_Diffusion_Models_p24_eq21_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "algorithm block with neighboring assignments",
    },
    {
        "id": "29_Latent_Diffusion_Models_p24_eq22_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "algorithm block with neighboring assignments",
    },
    {
        "id": "29_Latent_Diffusion_Models_p24_eq23_h",
        "action": "reject",
        "crop_quality": ["neighbor_eq"],
        "notes": "MLP assignment plus following LayerNorm line",
    },
    {
        "id": "31_Vision_Transformer_p12_eq7_h",
        "action": "verify",
        "gold_latex_raw": r"\mathrm{SA}(\mathbf{z})=A\mathbf{v}",
        "equation_number": "7",
        "notes": "human_from_harvest; complete single-head attention",
    },
    {
        "id": "31_Vision_Transformer_p12_eq8_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "parameters-constant sentence above MSA concat",
    },
    {
        "id": "32_Swin_Transformer_p3_eq1_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated", "neighbor_eq"],
        "notes": "left column plus numbered (1) and (2)",
    },
    {
        "id": "32_Swin_Transformer_p3_eq2_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated", "neighbor_eq"],
        "notes": "left column plus (1)(2) and where-line",
    },
    {
        "id": "32_Swin_Transformer_p3_eq3_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "left-column heading beside four-line block (3)",
    },
    {
        "id": "35_LoRA_p2_eq1_h",
        "action": "verify",
        "gold_latex_raw": r"\max_{\Phi}\sum_{(x,y)\in\mathcal{Z}}\sum_{t=1}^{|y|}\log(P_{\Phi}(y_{t}|x,y_{<t}))",
        "equation_number": "1",
        "notes": "human_from_harvest; complete autoregressive MLE",
    },
    {
        "id": "35_LoRA_p2_eq2_h",
        "action": "verify",
        "gold_latex_raw": r"\max_{\Theta}\sum_{(x,y)\in\mathcal{Z}}\sum_{t=1}^{|y|}\log\left(p_{\Phi_{0}+\Delta\Phi(\Theta)}(y_{t}|x,y_{<t})\right)",
        "equation_number": "2",
        "notes": "human_from_harvest; complete LoRA fine-tune MLE",
    },
    {
        "id": "35_LoRA_p3_eq3_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "initialization paragraph below h=W0x+BAx",
    },
    {
        "id": "35_LoRA_p10_eq4_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "Appendix G sentence above subspace overlap",
    },
    {
        "id": "36_GPT3_p36_eq12_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "table adjective list, not a display equation",
    },
    {
        "id": "36_GPT3_p36_eq13_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "table adjective list, not a display equation",
    },
    {
        "id": "36_GPT3_p36_eq10_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "table adjective list, not a display equation",
    },
    {
        "id": "38_Chinchilla_p1_eq1_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "FLOPs(N,D)=C lead-in above argmin",
    },
    {
        "id": "38_Chinchilla_p5_eq2_h",
        "action": "reject",
        "crop_quality": ["prose_contaminated"],
        "notes": "we propose the following functional form above (2)",
    },
    {
        "id": "38_Chinchilla_p5_eq3_h",
        "action": "verify",
        "gold_latex_raw": r"\min_{A,B,E,\alpha,\beta}\sum_{\mathrm{Runs}\ i}\mathrm{Huber}_{\delta}(\log\hat{L}(N_{i},D_{i})-\log L_{i})",
        "equation_number": "3",
        "notes": "human_from_harvest; complete scaling-law Huber fit",
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
    spec["created_at"] = "2026-08-23T17:05:00"
    v = sum(1 for r in NEW if r["action"] == "verify")
    r = sum(1 for r in NEW if r["action"] == "reject")
    PATH.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print({"added": added, "verify": v, "reject": r, "total_reviews": len(spec["reviews"])})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
