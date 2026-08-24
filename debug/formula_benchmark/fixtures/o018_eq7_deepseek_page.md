\[  TPR=\frac{TP}{TP+FN} \quad (6) \] 


 \[  FPR=\frac{FP}{FP+TN} \quad (7) \] 


## 3.5.3. Model interpretability with SHAP


The Shapley Additive Explanations (SHAP) framework was employed to interpret the contribution of individual features to the model's predictions  \( [48] \) . SHAP provides both global interpretability-by identifying the most influential predictors across the dataset-and local interpretability-by decomposing each prediction into additive feature contributions at the student level.


This dual capability enhances transparency and strengthens educational value by clarifying the determinants of academic achievement. Beyond feature ranking, SHAP interaction values and dependence plots were examined to capture the joint influence of predictors. These analyses reveal nonlinear relationships and interaction effects (e.g., how timely submissions and assessment scores jointly shape learning outcomes).


Such insights are particularly valuable in educational contexts, where interactions between engagement and assessment behaviours reflect established pedagogical principles. Importantly, SHAP interpretability is grounded in cooperative game theory, where each feature is assigned a fair attribution value proportional to its marginal contribution across all possible feature coalitions. This ensures both statistical validity and pedagogical transparency. The identification of assessment-related variables and temporal engagement indicators as highly influential aligns with self-regulated learning theory  \( [24] \)  and engagement theory  \( [25] \) , validating the model by linking its outputs to established educational constructs.


## 3.5.4. Statistical significance testing


To evaluate whether the observed improvements in predictive performance were meaningful, paired t-tests were conducted to compare the stacking ensemble against each base learner. The tests were applied across cross-validated folds for F1 score, ROC-AUC, and balanced accuracy, following established guidelines for classifier comparison  \( [49, 50] \) . Statistical significance was assessed at  \( \alpha = 0.05 \) , with p < 0.05 indicating that the improvements of the stacking model were statistically significant compared to the baseline models. In this procedure, both the stacking model and the base learners were evaluated on identical resampled test sets, producing paired performance observations.


<table><tr><td colspan="5">Table 2. Performance metrics across models</td></tr><tr><td colspan="5">Evaluation Metric</td></tr><tr><td>Model</td><td>Accuracy</td><td>Precision</td><td>F1</td><td>ROC-AUC</td></tr><tr><td>XGBoost</td><td>0.926522</td><td>0.925260</td><td>0.953836</td><td>0.939331</td></tr><tr><td>LGBM</td><td>0.925746</td><td>0.925973</td><td>0.951560</td><td>0.938592</td></tr><tr><td>RF</td><td>0.925940</td><td>0.914462</td><td>0.966190</td><td>0.939614</td></tr><tr><td>SVM</td><td>0.922644</td><td>0.916589</td><td>0.957412</td><td>0.936556</td></tr><tr><td>Stacking Testing</td><td>0.927297</td><td>0.922427</td><td>0.958713</td><td>0.940220</td></tr><tr><td>Stacking Training</td><td>0.945172</td><td>0.935308</td><td>0.975530</td><td>0.954996</td></tr></table><｜end▁of▁sentence｜>