# Section 1 Slides: Introduction to Machine Learning and AI Models

## Slide Map (Template Index → Content)

This file defines the slide content for Section 1, mapped to template slide types.
The Python converter reads this file and generates a PPTX using the template.

---

## SLIDE 1 — template_index: 0 (Section Header)
- placeholder: "Section Name Here" → "Introduction to Machine Learning and AI Models"
- placeholder: "SECTION Number" → "SECTION 1"

---

## SLIDE 2 — template_index: 1 (Video Title)
- placeholder: "Video Name" → "Course Overview"
- placeholder: "Section Name" → "Introduction to Machine Learning and AI Models"
- placeholder: "Video Number" → "Video 1.1"

---

## SLIDE 3 — template_index: 3 (Multi Point)
- placeholder: "Multi Point Slide" → "Why Algorithmic Auditing Matters"
- bullets:
  - "COMPAS recidivism algorithm: 45% false positive rate for Black defendants vs 23% for white defendants (ProPublica, 2016)"
  - "Amazon hiring algorithm systematically penalized applications mentioning women, trained on decade of male-dominated resumes"
  - "Mobley v. Workday (2025): Legal precedent for joint liability of AI vendors and deployers for discriminatory outcomes"
  - "EU AI Act penalties: Up to 35 million euros or 7% of global revenue for non-compliance"
  - "NIST AI RMF and ISO/IEC 42001 provide structured governance and certifiable management systems"

---

## SLIDE 4 — template_index: 7 (Key Highlights — 4 columns)
- placeholder: "Key Highlights" → "What You Will Learn"
- placeholder: "Enter your subhead line here" → "9 Sections Covering the Full Algorithmic Auditing Lifecycle"
- card_1_title: "Foundations (Sec 1-3)"
- card_1_body: "ML fundamentals, algorithmic auditing definition, ethical principles driving accountability"
- card_2_title: "Legal & Compliance (Sec 4)"
- card_2_body: "GDPR Article 22, EU AI Act, NIST AI RMF, ISO/IEC 42001, hands-on compliance reporting"
- card_3_title: "Bias & Explainability (Sec 5-6)"
- card_3_body: "Fairness metrics, COMPAS case study, SHAP, LIME, Integrated Gradients with hands-on labs"
- card_4_title: "Advanced & Applied (Sec 7-9)"
- card_4_body: "Adversarial robustness, critical infrastructure audits, end-to-end audit with Fairlearn and AIF360"

---

## SLIDE 5 — template_index: 11 (Excellence Grid — 3 items)
- placeholder: "EXCELLENCE IN THE" → "Course Approach"
- item_01_title: "Evidence-Based Rigor"
- item_01_body: "90+ sources including 75 academic papers and 15 regulatory documents. Every claim is traceable."
- item_02_title: "Hands-On Implementation"
- item_02_body: "Fairlearn, AIF360, SHAP, LIME, and Adversarial Robustness Toolbox on real datasets from Section 4 onward."
- item_03_title: "Security-First Perspective"
- item_03_body: "ISO 27001 auditing rigor applied to AI. Threat modeling, defense-in-depth, continuous monitoring built in."

---

## SLIDE 6 — template_index: 3 (Multi Point)
- placeholder: "Multi Point Slide" → "Prerequisites and Target Audience"
- bullets:
  - "Basic understanding of machine learning concepts (models, training data, predictions)"
  - "Python familiarity helpful for tool demos, but not required for comprehension"
  - "General cybersecurity or risk management background beneficial"
  - "All tools are open-source and freely available"
  - "Companion Jupyter notebooks available from course GitHub repository"

---

## SLIDE 7 — template_index: 12 (Next Video)
- placeholder: "Name of the Next Video" → "Machine Learning Fundamentals"
- placeholder: "Next Video" → "Video 1.2"

---

## SLIDE 8 — template_index: 1 (Video Title)
- placeholder: "Video Name" → "Machine Learning Fundamentals"
- placeholder: "Section Name" → "Introduction to Machine Learning and AI Models"
- placeholder: "Video Number" → "Video 1.2"

---

## SLIDE 9 — template_index: 4 (Callout / Key Point)
- placeholder: "A key point (or issue)!" → "ML inverts traditional programming: instead of writing rules, you provide data and outputs, and the algorithm learns the rules."

---

## SLIDE 10 — template_index: 11 (Excellence Grid — 3 items)
- placeholder: "EXCELLENCE IN THE" → "Three Learning Paradigms"
- item_01_title: "Supervised Learning"
- item_01_body: "Learns from labeled examples. Classification and regression. Most common in high-stakes decisions (hiring, credit, recidivism)."
- item_02_title: "Unsupervised Learning"
- item_02_body: "Finds structure in unlabeled data. Clustering and anomaly detection. Used in fraud detection and customer segmentation."
- item_03_title: "Reinforcement Learning"
- item_03_body: "Optimizes decisions through trial and error. Powers recommendations, autonomous vehicles, dynamic pricing."

---

## SLIDE 11 — template_index: 9 (Features — 6 items)
- placeholder: "Features" → "ML Lifecycle: Where Bias Enters"
- placeholder: "Enter your subhead line here" → "Seven Stages Where Bias Can Infiltrate AI Systems"
- item_1_title: "Problem Definition"
- item_1_body: "Choice of prediction target encodes assumptions. Biased success metrics embed discrimination before data collection."
- item_2_title: "Data Collection"
- item_2_body: "Training data reflects the world that produced it. Historical patterns encode past discrimination as legitimate signals."
- item_3_title: "Feature Engineering"
- item_3_body: "Proxy variables like zip code correlate with race. Removing protected attributes does not prevent indirect discrimination."
- item_4_title: "Model Training"
- item_4_body: "Optimizing for accuracy alone exploits any signal, including discriminatory ones, without fairness constraints."
- item_5_title: "Evaluation"
- item_5_body: "85% overall accuracy can mask 95% for one group and 60% for another. Aggregate metrics hide group-level harm."
- item_6_title: "Deployment & Monitoring"
- item_6_body: "Real-world drift degrades fairness silently. Without continuous oversight, fair models become unfair over time."

---

## SLIDE 12 — template_index: 7 (Key Highlights — 4 columns)
- placeholder: "Key Highlights" → "Four Types of Data Bias"
- placeholder: "Enter your subhead line here" → "40% of documented bias incidents trace to training data (Mehrabi et al., 2022)"
- card_1_title: "Historical Bias"
- card_1_body: "Training data reflects past discrimination. COMPAS trained on decades of racially disparate policing data."
- card_2_title: "Representation Bias"
- card_2_body: "Underrepresented groups yield higher error rates. Medical imaging models fail on underrepresented skin tones."
- card_3_title: "Measurement Bias"
- card_3_body: "Outcome proxies conflate signals. Arrest records conflate policing intensity with actual crime rates."
- card_4_title: "Aggregation Bias"
- card_4_body: "Heterogeneous populations treated as one. Diabetes models fail for ethnic subgroups with different biomarkers."

---

## SLIDE 13 — template_index: 11 (Excellence Grid — 3 items)
- placeholder: "EXCELLENCE IN THE" → "Model Auditability Spectrum"
- item_01_title: "Transparent Models"
- item_01_body: "Logistic regression, small decision trees. Fully interpretable coefficients. Code review sufficient for auditing."
- item_02_title: "Semi-Transparent Models"
- item_02_body: "Random Forests, XGBoost. Individual trees readable but ensemble behavior is opaque. Systematic tools required."
- item_03_title: "Black-Box Models"
- item_03_body: "Deep neural networks, LLMs. Direct interpretation impossible. Requires SHAP, LIME, Integrated Gradients (Section 6)."

---

## SLIDE 14 — template_index: 3 (Multi Point)
- placeholder: "Multi Point Slide" → "Key Governance Frameworks"
- bullets:
  - "NIST AI RMF: Govern, Map, Measure, Manage — structured governance for AI risk"
  - "EU AI Act: Risk-based classification with mandatory requirements for high-risk AI systems"
  - "ISO/IEC 42001: Certifiable AI management system following Annex SL structure (compatible with ISO 27001)"
  - "These frameworks are covered in depth in Section 4"

---

## SLIDE 15 — template_index: 12 (Next Video)
- placeholder: "Name of the Next Video" → "Understanding Model Behavior in Decision-Making"
- placeholder: "Next Video" → "Video 1.3"

---

## SLIDE 16 — template_index: 1 (Video Title)
- placeholder: "Video Name" → "Understanding Model Behavior in Decision-Making"
- placeholder: "Section Name" → "Introduction to Machine Learning and AI Models"
- placeholder: "Video Number" → "Video 1.3"

---

## SLIDE 17 — template_index: 3 (Multi Point)
- placeholder: "Multi Point Slide" → "From Features to Predictions"
- bullets:
  - "Input features (income, employment, debt ratio, zip code, age) enter the model"
  - "Model outputs a probability score (e.g., 0.72 for loan repayment likelihood)"
  - "Decision threshold converts probability to binary outcome (approve/deny at 0.60)"
  - "Zip code correlates with race due to residential segregation — indirect discrimination"
  - "Auditors must understand how models use inputs, not just what inputs are listed"

---

## SLIDE 18 — template_index: 11 (Excellence Grid — 3 items)
- placeholder: "EXCELLENCE IN THE" → "The Opacity Spectrum"
- item_01_title: "Tier 1: Transparent"
- item_01_body: "Logistic regression, rule-based systems. 10 coefficients you can print and read. Code review is sufficient."
- item_02_title: "Tier 2: Semi-Transparent"
- item_02_body: "Random Forests with 500 trees of depth 20. Tens of thousands of rules interacting. Need systematic tools."
- item_03_title: "Tier 3: Black-Box"
- item_03_body: "Deep neural networks, proprietary scoring. Direct interpretation impossible. SHAP, LIME, Integrated Gradients essential."

---

## SLIDE 19 — template_index: 5 (Stats)
- placeholder: "+80%" → "45% vs 23%"
- placeholder: "That’s how much more effective slides like this can be" → "COMPAS false positive rates: 45% for Black defendants vs 23% for white defendants."

---

## SLIDE 20 — template_index: 9 (Features — 6 items)
- placeholder: "Features" → "The Auditor's Technical Checklist"
- placeholder: "Enter your subhead line here" → "Six Questions Every Auditor Must Answer (Maps to NIST AI RMF MAP + MEASURE)"
- item_1_title: "Training Data"
- item_1_body: "What data was the model trained on? Who collected it? What populations are represented or underrepresented?"
- item_2_title: "Objective Function"
- item_2_body: "Does it optimize for accuracy only, or does it include fairness constraints?"
- item_3_title: "Feature Analysis"
- item_3_body: "What features does the model use? Are any proxies for protected attributes?"
- item_4_title: "Group Performance"
- item_4_body: "How does the model perform across demographic groups? Check group-specific error rates, not just overall."
- item_5_title: "Threshold Design"
- item_5_body: "Is the decision threshold uniform or optimized for fairness? Threshold optimization can improve fairness by 30%+."
- item_6_title: "Monitoring System"
- item_6_body: "Is there continuous monitoring for performance degradation and fairness drift after deployment?"

---

## SLIDE 21 — template_index: 3 (Multi Point)
- placeholder: "Multi Point Slide" → "Section 1 Summary"
- bullets:
  - "ML systems learn rules from data, creating opacity that requires systematic auditing"
  - "Bias enters at every lifecycle stage: problem definition through monitoring"
  - "Four data bias types: historical (40% of incidents), representation, measurement, aggregation"
  - "Model opacity spectrum determines auditing approach: transparent to black-box"
  - "Decision thresholds directly impact fairness: uniform thresholds on biased distributions produce unequal outcomes"
  - "NIST AI RMF MAP + MEASURE functions structure the auditor's technical assessment"

---

## SLIDE 22 — template_index: 12 (Next Video)
- placeholder: "Name of the Next Video" → "Introduction to Algorithmic Auditing"
- placeholder: "Next Video" → "Section 2"
