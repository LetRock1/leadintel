# E8 The anchored update inside the product (simulated histories)

Each history is the CRM running by itself for 180 days on 2,000 simulated learners, with one setting changed. An extra 10% of learners (the evaluation group) is never contacted and never used for training: every retraining method's score is judged on their outcomes. At each monthly learning date the methods refit the lead score's live layer on the same logged decision points (the evaluation group left out). Made by `ml/experiments/anchored_histories.py` and `ml/experiments/anchored_check.py`.

What is judged: each score as "the chance to buy within 14 days if the CRM never contacts the lead", the same target as the learning loop's own control-group check. The comparison is offline: every method is fitted on the same logs, made by one run of the CRM (which retrained with the research kit's estimator during the history); how each method would change the CRM's later decisions is not measured here.

*Log-loss* is a proper scoring rule (lower is better; differences x1000, paired on the same rows, 95% interval from resampling people, each person's rows at every learning date kept together). *Over-states* = mean predicted chance to buy within 14 days over the share that bought, minus 1. *Targeted* = decision points where the CRM would have taken a step (where its own effect is largest).

## 5% control group, 15% random steps (v7.0's settings)

3 histories, 15 learning dates; at the last date on average 8,064 logged decision points to learn from and 166 evaluation-group learners.

**Last learning date of each history**

| Method | Log-loss | AUC | Over-states | Log-loss vs v7.0 (x1000) | Targeted: log-loss | Targeted: over-states | Targeted: vs v7.0 (x1000) |
|---|---|---|---|---|---|---|---|
| Naive retrain | 0.4279 | 0.866 | +31% | +23.19 [+12.25, +34.43] | 0.4268 | +32% | +24.30 [+12.58, +36.78] |
| v7.0: told what the CRM did | 0.4047 | 0.866 | +13% | reference | 0.4026 | +14% | reference |
| Anchored per step (the kit's main estimator) | 0.4065 | 0.867 | +15% | +1.74 [-0.99, +4.75] | 0.4044 | +16% | +1.84 [-0.87, +4.83] |
| Anchored per step, weighed against the model's own (the kit's shrunk variant) | 0.4052 | 0.867 | +13% | +0.49 [+0.00, +1.00] | 0.4031 | +14% | +0.53 [+0.03, +1.04] |
| Anchored per step, left alone = never contacted (the control group only) | 0.4014 | 0.866 | +6% | -3.37 [-9.60, +3.26] | 0.3988 | +7% | -3.75 [-10.55, +3.17] |
| Anchored, one lift for any step (the kit's single-action setting) | 0.4064 | 0.865 | +13% | +1.69 [-3.38, +6.68] | 0.4041 | +14% | +1.57 [-3.61, +6.65] |

1,241 decision points of the evaluation group (28.0% bought); targeted 1,121.

**Every learning date**

| Method | Log-loss | AUC | Over-states | Log-loss vs v7.0 (x1000) | Targeted: log-loss | Targeted: over-states | Targeted: vs v7.0 (x1000) |
|---|---|---|---|---|---|---|---|
| Naive retrain | 0.4252 | 0.864 | +24% | +19.90 [+6.06, +33.25] | 0.4196 | +26% | +21.08 [+6.51, +35.26] |
| v7.0: told what the CRM did | 0.4053 | 0.866 | +9% | reference | 0.3986 | +11% | reference |
| Anchored per step (the kit's main estimator) | 0.4080 | 0.868 | +13% | +2.75 [-3.33, +9.18] | 0.4011 | +15% | +2.58 [-3.92, +9.37] |
| Anchored per step, weighed against the model's own (the kit's shrunk variant) | 0.4048 | 0.868 | +11% | -0.49 [-4.23, +3.12] | 0.3981 | +12% | -0.50 [-4.28, +3.41] |
| Anchored per step, left alone = never contacted (the control group only) | 0.4002 | 0.869 | +2% | -5.08 [-10.78, +1.23] | 0.3928 | +4% | -5.80 [-11.81, +0.56] |
| Anchored, one lift for any step (the kit's single-action setting) | 0.4059 | 0.866 | +8% | +0.60 [-4.85, +6.10] | 0.3987 | +9% | +0.18 [-5.28, +5.62] |

3,598 decision points of the evaluation group (29.3% bought); targeted 3,289.

Lower log-loss than v7.0, of 15 learning dates: anchored 5, shrunk 6, never-contacted 11, one lift 9. Than the naive retrain: anchored 12, shrunk 14. Shrunk better than anchored in 11; per step better than one lift in 7. Worst of the informed methods: v7.0: told what the CRM did 3, Anchored per step 7, Anchored per step, weighed against the model's own 0, Anchored per step, left alone = never contacted 0, Anchored, one lift for any step 5.

Each step's effect on the log-odds of buying at the last date (mean over the histories):

| Step | v7.0, learned by the model | Anchored, from the design | Shrunk | Never-contacted |
|---|---|---|---|---|
| Send an information email | +0.29 | +0.14 | +0.25 | +0.44 |
| Send email with 10% coupon | +0.49 | +0.44 | +0.49 | +0.69 |
| Send email with 20% coupon | +0.73 | +0.80 | +0.73 | +1.48 |
| Counsellor phone call | +0.35 | +0.23 | +0.35 | +0.22 |
| WhatsApp message | +0.21 | +0.22 | +0.21 | +0.36 |
| Campaign or A/B email | +0.86 | +0.74 | +0.75 | +1.08 |

One lift for any step (the paper's setting): +0.45.


## 5% control group, 5% random steps

3 histories, 15 learning dates; at the last date on average 8,233 logged decision points to learn from and 167 evaluation-group learners.

**Last learning date of each history**

| Method | Log-loss | AUC | Over-states | Log-loss vs v7.0 (x1000) | Targeted: log-loss | Targeted: over-states | Targeted: vs v7.0 (x1000) |
|---|---|---|---|---|---|---|---|
| Naive retrain | 0.3674 | 0.902 | +28% | +20.20 [+3.98, +35.47] | 0.3741 | +30% | +22.89 [+6.33, +38.83] |
| v7.0: told what the CRM did | 0.3472 | 0.900 | +1% | reference | 0.3513 | +3% | reference |
| Anchored per step (the kit's main estimator) | 0.3979 | 0.856 | -10% | +50.73 [+19.51, +90.99] | 0.4013 | -7% | +49.99 [+17.29, +93.60] |
| Anchored per step, weighed against the model's own (the kit's shrunk variant) | 0.3991 | 0.856 | -11% | +51.96 [+19.99, +92.13] | 0.4021 | -9% | +50.89 [+18.20, +95.06] |
| Anchored per step, left alone = never contacted (the control group only) | 0.3441 | 0.900 | +1% | -3.11 [-6.10, +0.06] | 0.3482 | +3% | -3.10 [-6.03, +0.05] |
| Anchored, one lift for any step (the kit's single-action setting) | 0.3510 | 0.902 | +12% | +3.78 [-3.63, +10.71] | 0.3562 | +14% | +4.95 [-2.67, +12.06] |

1,258 decision points of the evaluation group (27.2% bought); targeted 1,158.

**Every learning date**

| Method | Log-loss | AUC | Over-states | Log-loss vs v7.0 (x1000) | Targeted: log-loss | Targeted: over-states | Targeted: vs v7.0 (x1000) |
|---|---|---|---|---|---|---|---|
| Naive retrain | 0.3654 | 0.902 | +22% | +13.60 [-5.75, +31.55] | 0.3681 | +24% | +16.64 [-2.92, +34.70] |
| v7.0: told what the CRM did | 0.3518 | 0.901 | -3% | reference | 0.3515 | -1% | reference |
| Anchored per step (the kit's main estimator) | 0.3748 | 0.884 | +1% | +23.06 [+7.50, +44.25] | 0.3758 | +3% | +24.31 [+8.64, +45.38] |
| Anchored per step, weighed against the model's own (the kit's shrunk variant) | 0.3744 | 0.884 | -6% | +22.65 [+9.88, +38.50] | 0.3743 | -4% | +22.82 [+9.67, +39.88] |
| Anchored per step, left alone = never contacted (the control group only) | 0.3508 | 0.901 | +1% | -0.93 [-6.18, +3.93] | 0.3511 | +3% | -0.33 [-5.56, +4.60] |
| Anchored, one lift for any step (the kit's single-action setting) | 0.3541 | 0.902 | +8% | +2.38 [-7.34, +11.79] | 0.3554 | +10% | +3.96 [-6.08, +13.14] |

3,751 decision points of the evaluation group (28.0% bought); targeted 3,465.

Lower log-loss than v7.0, of 15 learning dates: anchored 7, shrunk 5, never-contacted 7, one lift 5. Than the naive retrain: anchored 12, shrunk 11. Shrunk better than anchored in 6; per step better than one lift in 9. Worst of the informed methods: v7.0: told what the CRM did 3, Anchored per step 4, Anchored per step, weighed against the model's own 3, Anchored per step, left alone = never contacted 3, Anchored, one lift for any step 6.

Each step's effect on the log-odds of buying at the last date (mean over the histories):

| Step | v7.0, learned by the model | Anchored, from the design | Shrunk | Never-contacted |
|---|---|---|---|---|
| Send an information email | +0.53 | -0.08 | +0.19 | +0.32 |
| Send email with 10% coupon | +0.65 | +0.56 | +0.65 | +0.73 |
| Send email with 20% coupon | +0.74 | +0.59 | +0.74 | +1.00 |
| Counsellor phone call | +0.65 | +2.51 | +2.35 | +0.54 |
| WhatsApp message | +0.43 | +0.67 | +0.73 | +0.43 |
| Campaign or A/B email | +0.87 | +0.41 | +0.58 | +0.93 |

One lift for any step (the paper's setting): +0.36.


## 5% control group, no random steps

3 histories, 15 learning dates; at the last date on average 8,071 logged decision points to learn from and 168 evaluation-group learners.

**Last learning date of each history**

| Method | Log-loss | AUC | Over-states | Log-loss vs v7.0 (x1000) | Targeted: log-loss | Targeted: over-states | Targeted: vs v7.0 (x1000) |
|---|---|---|---|---|---|---|---|
| Naive retrain | 0.3887 | 0.894 | +32% | +26.70 [+15.55, +37.19] | 0.3925 | +31% | +25.32 [+13.95, +37.52] |
| v7.0: told what the CRM did | 0.3620 | 0.894 | +12% | reference | 0.3672 | +10% | reference |
| Anchored per step (the kit's main estimator) | 0.3674 | 0.892 | +16% | +5.40 [-5.49, +17.55] | 0.3708 | +14% | +3.62 [-7.29, +15.46] |
| Anchored per step, weighed against the model's own (the kit's shrunk variant) | 0.3624 | 0.894 | +14% | +0.39 [-2.40, +3.24] | 0.3669 | +12% | -0.27 [-3.21, +2.62] |
| Anchored per step, left alone = never contacted (the control group only) | 0.3660 | 0.888 | +9% | +4.04 [-3.17, +11.11] | 0.3717 | +7% | +4.51 [-2.98, +12.35] |
| Anchored, one lift for any step (the kit's single-action setting) | 0.3686 | 0.894 | +19% | +6.57 [+2.82, +10.34] | 0.3732 | +17% | +6.05 [+1.94, +10.18] |

1,272 decision points of the evaluation group (27.4% bought); targeted 1,143.

**Every learning date**

| Method | Log-loss | AUC | Over-states | Log-loss vs v7.0 (x1000) | Targeted: log-loss | Targeted: over-states | Targeted: vs v7.0 (x1000) |
|---|---|---|---|---|---|---|---|
| Naive retrain | 0.3894 | 0.887 | +31% | +23.53 [+11.78, +34.56] | 0.3946 | +29% | +22.45 [+9.62, +34.63] |
| v7.0: told what the CRM did | 0.3659 | 0.887 | +13% | reference | 0.3721 | +11% | reference |
| Anchored per step (the kit's main estimator) | 0.3910 | 0.882 | +21% | +25.16 [+9.01, +43.97] | 0.3932 | +19% | +21.12 [+3.89, +38.48] |
| Anchored per step, weighed against the model's own (the kit's shrunk variant) | 0.3776 | 0.885 | +18% | +11.79 [+3.23, +21.90] | 0.3819 | +16% | +9.76 [+1.73, +18.56] |
| Anchored per step, left alone = never contacted (the control group only) | 0.3691 | 0.883 | +10% | +3.28 [-3.32, +10.14] | 0.3757 | +9% | +3.61 [-2.92, +10.49] |
| Anchored, one lift for any step (the kit's single-action setting) | 0.3759 | 0.881 | +15% | +9.99 [+4.01, +15.78] | 0.3820 | +14% | +9.92 [+4.22, +15.91] |

3,615 decision points of the evaluation group (27.2% bought); targeted 3,267.

Lower log-loss than v7.0, of 15 learning dates: anchored 6, shrunk 4, never-contacted 5, one lift 2. Than the naive retrain: anchored 8, shrunk 12. Shrunk better than anchored in 10; per step better than one lift in 9. Worst of the informed methods: v7.0: told what the CRM did 0, Anchored per step 6, Anchored per step, weighed against the model's own 0, Anchored per step, left alone = never contacted 1, Anchored, one lift for any step 8.

Each step's effect on the log-odds of buying at the last date (mean over the histories):

| Step | v7.0, learned by the model | Anchored, from the design | Shrunk | Never-contacted |
|---|---|---|---|---|
| Send an information email | +0.28 | -1.03 | -0.38 | +0.02 |
| Send email with 10% coupon | +0.59 | +0.36 | +0.51 | +0.18 |
| Send email with 20% coupon | +0.76 | +0.95 | +0.88 | +1.09 |
| Counsellor phone call | +0.39 | +0.66 | +0.48 | +0.49 |
| WhatsApp message | +0.38 | +0.57 | +0.47 | +0.80 |
| Campaign or A/B email | +0.68 | +0.49 | +0.61 | +0.73 |

One lift for any step (the paper's setting): +0.32.


## no control group, 15% random steps

1 histories, 5 learning dates; at the last date on average 8,248 logged decision points to learn from and 158 evaluation-group learners.

**Last learning date of each history**

| Method | Log-loss | AUC | Over-states | Log-loss vs v7.0 (x1000) | Targeted: log-loss | Targeted: over-states | Targeted: vs v7.0 (x1000) |
|---|---|---|---|---|---|---|---|
| Naive retrain | 0.4225 | 0.859 | +49% | +17.61 [+7.44, +26.40] | 0.4325 | +51% | +18.54 [+8.50, +27.50] |
| v7.0: told what the CRM did | 0.4049 | 0.858 | +37% | reference | 0.4139 | +39% | reference |
| Anchored per step (the kit's main estimator) | 0.4030 | 0.858 | +35% | -1.91 [-4.58, +0.93] | 0.4120 | +37% | -1.99 [-4.69, +0.94] |
| Anchored per step, weighed against the model's own (the kit's shrunk variant) | 0.4049 | 0.858 | +37% | +0.00 [-0.00, +0.00] | 0.4139 | +39% | +0.00 [-0.00, +0.00] |
| Anchored per step, left alone = never contacted (the control group only) | 0.4049 | 0.858 | +37% | +0.00 [+0.00, +0.00] | 0.4139 | +39% | +0.00 [+0.00, +0.00] |
| Anchored, one lift for any step (the kit's single-action setting) | 0.3913 | 0.859 | +28% | -13.58 [-25.40, -2.13] | 0.3997 | +30% | -14.28 [-25.94, -2.27] |

386 decision points of the evaluation group (24.1% bought); targeted 355.

**Every learning date**

| Method | Log-loss | AUC | Over-states | Log-loss vs v7.0 (x1000) | Targeted: log-loss | Targeted: over-states | Targeted: vs v7.0 (x1000) |
|---|---|---|---|---|---|---|---|
| Naive retrain | 0.4158 | 0.858 | +43% | +11.37 [+2.82, +19.00] | 0.4256 | +44% | +12.17 [+3.36, +20.12] |
| v7.0: told what the CRM did | 0.4044 | 0.857 | +35% | reference | 0.4135 | +35% | reference |
| Anchored per step (the kit's main estimator) | 0.5894 | 0.838 | +62% | +184.91 [+83.96, +304.63] | 0.6033 | +63% | +189.82 [+87.02, +312.57] |
| Anchored per step, weighed against the model's own (the kit's shrunk variant) | 0.5430 | 0.840 | +56% | +138.52 [+63.73, +227.21] | 0.5557 | +56% | +142.25 [+65.07, +233.19] |
| Anchored per step, left alone = never contacted (the control group only) | 0.4044 | 0.857 | +35% | +0.00 [+0.00, +0.00] | 0.4135 | +35% | +0.00 [+0.00, +0.00] |
| Anchored, one lift for any step (the kit's single-action setting) | 0.3894 | 0.857 | +25% | -15.05 [-29.41, -0.94] | 0.3984 | +26% | -15.04 [-29.63, -1.08] |

1,148 decision points of the evaluation group (24.6% bought); targeted 1,054.

Lower log-loss than v7.0, of 5 learning dates: anchored 1, shrunk 0, never-contacted 0, one lift 5. Than the naive retrain: anchored 1, shrunk 2. Shrunk better than anchored in 4; per step better than one lift in 0. Worst of the informed methods: v7.0: told what the CRM did 0, Anchored per step 4, Anchored per step, weighed against the model's own 1, Anchored per step, left alone = never contacted 0, Anchored, one lift for any step 0.

Each step's effect on the log-odds of buying at the last date (mean over the histories):

| Step | v7.0, learned by the model | Anchored, from the design | Shrunk | Never-contacted |
|---|---|---|---|---|
| Send an information email | +0.18 | -0.05 | +0.18 | +0.18 |
| Send email with 10% coupon | +0.13 | +0.07 | +0.13 | +0.13 |
| Send email with 20% coupon | +0.52 | +0.77 | +0.52 | +0.52 |
| Counsellor phone call | +0.06 | +0.16 | +0.06 | +0.06 |
| WhatsApp message | -0.05 | -0.01 | -0.05 | -0.05 |
| Campaign or A/B email | +0.79 | +0.59 | +0.79 | +0.79 |

One lift for any step (the paper's setting): +0.38.


## no control group, no random steps

1 histories, 5 learning dates; at the last date on average 8,309 logged decision points to learn from and 158 evaluation-group learners.

**Last learning date of each history**

| Method | Log-loss | AUC | Over-states | Log-loss vs v7.0 (x1000) | Targeted: log-loss | Targeted: over-states | Targeted: vs v7.0 (x1000) |
|---|---|---|---|---|---|---|---|
| Naive retrain | 0.4472 | 0.861 | +49% | +44.66 [+16.26, +70.87] | 0.4519 | +51% | +46.17 [+20.17, +72.23] |
| v7.0: told what the CRM did | 0.4025 | 0.862 | +19% | reference | 0.4058 | +21% | reference |
| Anchored per step (the kit's main estimator) | 0.4767 | 0.862 | +61% | +74.16 [+32.94, +113.50] | 0.4824 | +63% | +76.65 [+37.49, +115.89] |
| Anchored per step, weighed against the model's own (the kit's shrunk variant) | 0.4470 | 0.861 | +48% | +44.48 [+15.60, +73.12] | 0.4520 | +50% | +46.18 [+18.96, +74.18] |
| Anchored per step, left alone = never contacted (the control group only) | 0.4025 | 0.862 | +19% | +0.00 [+0.00, +0.00] | 0.4058 | +21% | +0.00 [+0.00, +0.00] |
| Anchored, one lift for any step (the kit's single-action setting) | 0.4399 | 0.861 | +45% | +37.34 [+12.42, +60.53] | 0.4444 | +47% | +38.64 [+15.58, +61.75] |

415 decision points of the evaluation group (25.3% bought); targeted 395.

**Every learning date**

| Method | Log-loss | AUC | Over-states | Log-loss vs v7.0 (x1000) | Targeted: log-loss | Targeted: over-states | Targeted: vs v7.0 (x1000) |
|---|---|---|---|---|---|---|---|
| Naive retrain | 0.4486 | 0.866 | +52% | +46.73 [+19.24, +72.12] | 0.4515 | +53% | +48.10 [+21.33, +73.79] |
| v7.0: told what the CRM did | 0.4019 | 0.867 | +25% | reference | 0.4034 | +26% | reference |
| Anchored per step (the kit's main estimator) | 0.5479 | 0.859 | +73% | +146.00 [+73.50, +217.96] | 0.5519 | +74% | +148.52 [+78.08, +222.31] |
| Anchored per step, weighed against the model's own (the kit's shrunk variant) | 0.4975 | 0.859 | +57% | +95.64 [+40.41, +151.83] | 0.5004 | +57% | +96.97 [+43.60, +153.08] |
| Anchored per step, left alone = never contacted (the control group only) | 0.4019 | 0.867 | +25% | +0.00 [+0.00, +0.00] | 0.4034 | +26% | +0.00 [+0.00, +0.00] |
| Anchored, one lift for any step (the kit's single-action setting) | 0.4557 | 0.864 | +54% | +53.83 [+24.31, +81.91] | 0.4587 | +55% | +55.35 [+25.80, +83.73] |

1,246 decision points of the evaluation group (25.1% bought); targeted 1,187.

Lower log-loss than v7.0, of 5 learning dates: anchored 0, shrunk 0, never-contacted 0, one lift 0. Than the naive retrain: anchored 0, shrunk 4. Shrunk better than anchored in 5; per step better than one lift in 0. Worst of the informed methods: v7.0: told what the CRM did 0, Anchored per step 5, Anchored per step, weighed against the model's own 0, Anchored per step, left alone = never contacted 0, Anchored, one lift for any step 0.

Each step's effect on the log-odds of buying at the last date (mean over the histories):

| Step | v7.0, learned by the model | Anchored, from the design | Shrunk | Never-contacted |
|---|---|---|---|---|
| Send an information email | +0.27 | -1.21 | -0.99 | +0.27 |
| Send email with 10% coupon | +0.70 | +0.66 | +0.70 | +0.70 |
| Send email with 20% coupon | +0.75 | -0.41 | +0.05 | +0.75 |
| Counsellor phone call | +0.49 | -0.26 | -0.05 | +0.49 |
| WhatsApp message | +0.59 | -0.23 | +0.02 | +0.59 |
| Campaign or A/B email | +0.75 | +0.49 | +0.74 | +0.75 |

One lift for any step (the paper's setting): +0.07.


