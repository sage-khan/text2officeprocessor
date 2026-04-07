# Section 1 Summary: Introduction to Machine Learning and AI Models

## Section Overview

Section 1 establishes the technical foundation required for algorithmic auditing. It covers how machine learning systems work, the lifecycle stages where bias can enter, the opacity spectrum that determines auditing approaches, and how decision thresholds directly impact fairness outcomes. This section ensures that every subsequent topic, from fairness metrics to adversarial robustness, is grounded in a clear understanding of the systems being audited.

## Key Concepts Covered

- **Machine Learning vs. Traditional Programming**: ML systems learn decision rules from data rather than following explicitly programmed logic, creating opacity that necessitates systematic auditing.
- **Three Learning Paradigms**: Supervised learning (most common in high-stakes decisions), unsupervised learning (clustering, anomaly detection), and reinforcement learning (sequential decision optimization).
- **ML Lifecycle and Bias Entry Points**: Seven stages (problem definition, data collection, feature engineering, training, evaluation, deployment, monitoring) where bias can enter.
- **Four Types of Data Bias**: Historical bias (40% of incidents, Mehrabi et al., 2022), representation bias, measurement bias, and aggregation bias.
- **Model Opacity Spectrum**: From transparent (linear models) through semi-transparent (tree ensembles) to black-box (deep neural networks).
- **Decision Thresholds and Fairness**: Uniform thresholds applied to groups with different score distributions produce unequal outcome rates. COMPAS demonstrated 45% vs. 23% FPR disparity.
- **Proxy Variables and Indirect Discrimination**: Features correlated with protected attributes (e.g., zip code correlating with race) can transmit discriminatory signal even without explicit protected attribute inclusion.
- **Governance Frameworks Preview**: NIST AI RMF (Govern, Map, Measure, Manage) and ISO/IEC 42001 (Clause 9.2 internal audits) as structural foundations for algorithmic auditing.

## Evidence Sources

- NIST AI RMF 1.0 (2023) - Governance framework structure
- Mehrabi et al. (2022) - Bias survey, 40% historical bias prevalence
- Angwin et al. (2016) - COMPAS investigation, 45% vs 23% FPR
- Dastin (2018) - Amazon hiring bias case
- de Castro Vieira et al. (2025) - Credit scoring bias, threshold optimization
- Bird et al. (2020) - Fairlearn toolkit
- ISO/IEC 42001:2023 - Certifiable AI management system

## Videos in This Section

| Video | Title | Duration | Type |
|-------|-------|----------|------|
| 1.1 | Course Overview | 5 min | PPT + Tool Preview |
| 1.2 | Machine Learning Fundamentals | 8 min | PPT + Browser Demo |
| 1.3 | Understanding Model Behavior in Decision-Making | 7 min | PPT + Code Editor Demo |

**Total Section Duration**: 20 minutes
