The proposed stacking ensemble is grounded in established ensemble learning principles, which address the bias-variance trade-off by aggregating diverse base learners under a meta-learner  \( [43] \) . The expected mean squared error (MSE) of a predictive model  \( \hat{f} \)  can be expressed by Eq. (1):


 \[ E\left[\left(\boldsymbol{\mathscr{y}}-\hat{\boldsymbol{f}}\right)^{2}\right]=Bias^{2}+V+\varepsilon \quad (1) \] 


Where  \( \hat{y} \)  is the true target value,  \( \hat{f} \)  is the model's prediction, Bias is the systematic deviation of a model's average predictions from the true values, V is variance and  \( \varepsilon \)  is the random error.


By combining heterogeneous models, the ensemble reduces variance while retaining the low-bias characteristic of strong learners such as gradient boosting methods. The logistic regression meta-learner integrates outputs with stability and interpretability, theoretically minimizing error across heterogeneous predictive functions.


In this study, the stacking ensemble model for predicting student performance on OULAD uses a standardized 80/20 train–test split of 25,786 records, with twenty selected features across seven courses and 22 presentations (2013–2014). Baseline models were trained under the same conditions. The stacking ensemble combines base learners with a logistic regression meta-learner.


This study adopts a two-level stacking architecture. At Level 0 (base learners), four algorithms-XGBoost, LightGBM, Random Forest, and SVM-were trained on the 20 most predictive features. Each was optimized to balance efficiency and generalization: XGBoost tuned with max depth = 6, learning rate = 0.01, and regularization terms; LightGBM configured with gradient boosting (boosting_type = 'gbdt') and leaf-wise tree growth; Random Forest implemented with 500 trees and constrained depth (max_depth = 10); and SVM applied with an RBF kernel and standardized inputs via StandardScaler.


At Level 1 (meta-learner), a Logistic Regression model (L2 penalty, C=0.1) was employed to integrate base learner predictions. Logistic regression was chosen due to its stability, probabilistic interpretability, and resistance to overfitting in meta-learning contexts  \( [44] \) . Robustness was ensured through 5-fold stratified cross-validation, which minimized class imbalance effects, prevented data leakage, and enhanced generalizability.


## 3.5 Evaluation measures


The proposed model was evaluated using a comprehensive set of performance metrics, including accuracy, precision, recall, F1-score, and the area under the ROC curve (AUC), to measure classification effectiveness  \( [45] \) . Additionally, SHAP (Shapley Additive Explanations) provides insights into classification performance. A single metric alone may yield misleading interpretations  \( [46] \) .


## 3.5.1. Classification metrics


The confusion matrix (CM) is a widely used tool for evaluating the performance of classification. It represents four key outcomes: true positives (TP), true negatives (TN), false positives (FP), and false negatives (FN). Several performance metrics are derived from CM:


Accuracy, or error rate, is the ratio of correct predictions to the total number of data points. It can be defined by Eq. (2):


 \[  Accuracy=\frac{TP+TN}{TP+TN+FP+FN} \quad (2) \] 


Precision, also known as positive predictive value, measures the proportion of true positives among all predicted positives. For example, it measures how accurately the classifier model predicts the 'approved' class as a specific class. Precision can be calculated using Eq. (3):


 \[  Precision=\frac{TP}{TP+FP} \quad (3) \] 


Recall, known as sensitivity as well, quantifies the ratio of actual positives that are correctly identified. Recall can be calculated using Eq. (4):


 \[  Recall=\frac{TP}{TP+FN} \quad (4) \] 


The F1-score is the harmonic average of precision and recall, which balances both concerns. It can be calculated from Eq. (5):


 \[  F