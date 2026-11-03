# E1b Our lead scoring vs published solutions (X Education, 9,240 real leads)

Same data (byte-identical Leads.csv), same rows, same inputs. The precise metric is ROC AUC on the identical test rows with DeLong's 95% interval and paired test, repeated on 30 new splits with the corrected resampled t-interval; accuracy is compared at a cut-off chosen on the training rows by each solution's own rule (McNemar's exact test).

**Post-contact columns** (Tags, Lead Quality, Lead Profile, Last Activity, Last Notable Activity, Asymmetrique scores) are filled in by the sales team after contacting a lead, so a new lead never has them: a model that uses them cannot score new leads.

## The records, in one table

| Comparison | Best earlier result (published, or their model re-run) | Ours | How it is measured |
|---|---|---|---|
| Same rows and same inputs as each of 4 public solutions | AUC 0.864–0.972 | higher by +0.004 to +0.030 on their split; better in 30 of 30 new splits for each (every 95% interval above zero) | DeLong on the identical test rows; 30 new 70/30 splits |
| Only inputs a new lead has | AUC 0.8605 (Mandal 2025, stratified 80/20); 0.864 (Lohani & Bansal, on its split) | AUC 0.874 on 50 stratified 80/20 splits (above 0.8605 in 98%); 0.875 on Lohani & Bansal's split — with 9 columns | their protocol |
| With post-contact columns (not valid for new leads) | AUC 0.972, accuracy 93.0% | AUC 0.984 [0.982, 0.987], accuracy 94.7% | 5-fold cross-validation |

## A. Four public solutions, re-run exactly, on their own splits

| Public solution | Post-contact columns in its model | Test rows | Their AUC | Ours, same inputs | Ours − theirs (DeLong p) | Ours, new-lead inputs only | Their model without post-contact columns |
|---|---|---|---|---|---|---|---|
| [shinde-chandrakant / Lead-Scoring-Case-Study](https://github.com/shinde-chandrakant/Lead-Scoring-Case-Study) | 9 of 12 | 2,723 | 0.939 [0.929, 0.948] | 0.969 [0.962, 0.975] | +0.030 [+0.023, +0.037] (p < 0.0001) | 0.871 [0.857, 0.885] | 0.599 |
| [Sivagiri12 / Lead-Scoring-Case-Study---Sivagiri](https://github.com/Sivagiri12/Lead-Scoring-Case-Study---Sivagiri) | 5 of 14 | 1,649 | 0.882 [0.865, 0.899] | 0.900 [0.885, 0.916] | +0.018 [+0.010, +0.027] (p < 0.0001) | 0.886 [0.869, 0.902] | 0.862 |
| [ShahadShaikh / Lead_Score_Case_Study](https://github.com/ShahadShaikh/Lead_Score_Case_Study) | 9 of 13 | 2,686 | 0.972 [0.966, 0.978] | 0.976 [0.970, 0.982] | +0.004 [+0.001, +0.007] (p 0.0149) | 0.877 [0.864, 0.891] | 0.785 |
| [garima2811 / Lead_Scoring_Case_Study (Lohani & Bansal)](https://github.com/garima2811/Lead_Scoring_Case_Study) | none (0 of 11) | 2,731 | 0.864 [0.850, 0.878] | 0.869 [0.856, 0.883] | +0.005 [-0.001, +0.011] (p 0.0746) | 0.875 [0.861, 0.888] | 0.864 |

Every confusion matrix the notebooks printed was reproduced exactly: shinde-chandrakant yes, Sivagiri12 yes, ShahadShaikh yes, garima2811 yes. Sivagiri12's cleaning turns every lead from the API into a missing value, so its rows are the 5,496 leads that did not come from the API.

### Accuracy, sensitivity and specificity at each solution's own cut-off rule

| Public solution | Model | Cut-off | Accuracy | Sensitivity | Specificity | Precision | Log-loss |
|---|---|---|---|---|---|---|---|
| shinde-chandrakant | theirs (published) | 0.25 | 90.8% | 84.1% | 94.6% | 89.8% | 0.2651 |
| shinde-chandrakant | ours, same inputs | 0.37 | 91.9% | 90.0% | 93.0% | 88.0% | 0.2106 |
| shinde-chandrakant | ours, new-lead inputs | 0.42 | 81.4% | 74.5% | 85.4% | 74.4% | 0.4263 |
| shinde-chandrakant | theirs without post-contact columns | 0.12 | 42.0% | 97.4% | 10.5% | 38.3% | 0.6033 |
| Sivagiri12 | theirs (published) | 0.35 | 80.5% | 82.9% | 78.9% | 71.9% | 0.4229 |
| Sivagiri12 | ours, same inputs | 0.42 | 82.7% | 83.3% | 82.3% | 75.4% | 0.3863 |
| Sivagiri12 | ours, new-lead inputs | 0.42 | 81.3% | 82.5% | 80.6% | 73.5% | 0.4140 |
| Sivagiri12 | theirs without post-contact columns | 0.38 | 80.9% | 81.4% | 80.6% | 73.2% | 0.4473 |
| ShahadShaikh | theirs (published) | 0.30 | 92.8% | 92.0% | 93.3% | 89.2% | 0.1961 |
| ShahadShaikh | ours, same inputs | 0.29 | 92.4% | 91.7% | 92.8% | 88.4% | 0.1817 |
| ShahadShaikh | ours, new-lead inputs | 0.36 | 80.9% | 76.6% | 83.5% | 73.6% | 0.4215 |
| ShahadShaikh | theirs without post-contact columns | 0.28 | 74.7% | 74.9% | 74.6% | 64.0% | 0.5167 |
| garima2811 | theirs (published) | 0.30 | 77.5% | 83.0% | 74.1% | 66.4% | 0.4461 |
| garima2811 | ours, same inputs | 0.38 | 79.0% | 82.8% | 76.6% | 68.6% | 0.4345 |
| garima2811 | ours, new-lead inputs | 0.36 | 81.0% | 76.9% | 83.5% | 74.2% | 0.4262 |
| garima2811 | theirs without post-contact columns | 0.31 | 79.2% | 74.1% | 82.4% | 72.2% | 0.4461 |

| Public solution | Ours (same inputs) vs theirs: accuracy | McNemar p | Log-loss lower by [95% CI] |
|---|---|---|---|
| shinde-chandrakant | +1.1 points (110 leads only ours got right, 79 only theirs) | 0.0288 | +0.0545 [+0.0378, +0.0722] |
| Sivagiri12 | +2.2 points (75 leads only ours got right, 39 only theirs) | 0.0010 | +0.0365 [+0.0212, +0.0523] |
| ShahadShaikh | -0.4 points (24 leads only ours got right, 35 only theirs) | 0.1925 | +0.0144 [+0.0057, +0.0233] |
| garima2811 | +1.5 points (89 leads only ours got right, 49 only theirs) | 0.0008 | +0.0116 [+0.0018, +0.0209] |

### 30 more random 70/30 splits of each solution's rows

Mean AUC with the corrected resampled t-interval (Nadeau & Bengio 2003); their model keeps its published feature list (chosen on the original split, which can only favour it).

| Public solution | Their AUC | Ours, same inputs | Ours − theirs | Ours better in | Ours, new-lead inputs | New-lead − theirs |
|---|---|---|---|---|---|---|
| shinde-chandrakant | 0.949 [0.942, 0.955] | 0.973 [0.970, 0.977] | +0.025 [+0.020, +0.029] | 30 of 30 | 0.873 [0.865, 0.881] | -0.075 [-0.084, -0.067] |
| Sivagiri12 | 0.881 [0.872, 0.890] | 0.891 [0.883, 0.900] | +0.011 [+0.006, +0.016] | 30 of 30 | 0.876 [0.866, 0.887] | -0.004 [-0.012, +0.003] |
| ShahadShaikh | 0.970 [0.967, 0.974] | 0.975 [0.972, 0.978] | +0.004 [+0.003, +0.006] | 30 of 30 | 0.873 [0.863, 0.882] | -0.098 [-0.107, -0.089] |
| garima2811 | 0.859 [0.850, 0.867] | 0.867 [0.859, 0.876] | +0.009 [+0.005, +0.012] | 30 of 30 | 0.871 [0.863, 0.880] | +0.013 [+0.009, +0.016] |

## B. Published results whose code is not public

| Publication | Post-contact columns | Their protocol | Their result | Ours |
|---|---|---|---|---|
| [Mandal, MSc thesis, National College of Ireland (2025)](https://norma.ncirl.ie/9780/) | removed (9 columns) | stratified 80/20 split | random forest: accuracy 79.8%, AUC 0.8605 (threshold 0.53 chosen to maximise accuracy on the test set) | same protocol, 9 new-lead columns, 50 stratified 80/20 splits: AUC 0.874 (95% of splits 0.862–0.886; above 0.8605 in 98%), accuracy 80.8% with the cut-off chosen on the training rows |
| [Jadli et al., Indian J. Computer Science and Engineering 13(2), 2022](https://doi.org/10.21817/indjcse/2022/v13i2/221302098) | not stated | 9,074 rows x 89 columns after preprocessing | random forest: accuracy 93.0%, AUC 0.92 | with post-contact columns (5-fold CV): AUC 0.984, accuracy 94.7%. Without them the best accuracy in this study is 81.4%: above 90% needs post-contact columns |
| [Yim et al., Int. J. Management, Finance and Accounting 5(1), 2024](https://doi.org/10.33093/ijomfa.2024.5.1.2) | not stated in the abstract | 10-fold cross-validation | stacking: accuracy 92.3% | with post-contact columns (5-fold CV): AUC 0.984, accuracy 94.7%. Without them the best accuracy in this study is 81.4%: above 90% needs post-contact columns |

## What this shows (computed from the numbers above)

- **Same rows, same inputs:** on each solution's own split our AUC is higher for all 4 (3 significantly, DeLong p < 0.05; 1 not significantly; 0 lower), and on 30 new splits ours is better in 30, 30, 30, 30 of 30 with every interval above zero. Nothing was tuned on their data: the gradient boosting is the CRM's own configuration.
- **Their high numbers come from post-contact columns.** Refitted without those columns, each solution's own model falls: shinde-chandrakant AUC 0.939 → 0.599; Sivagiri12 AUC 0.882 → 0.862; ShahadShaikh AUC 0.972 → 0.785.
- **On what a new lead has**, our 9-column model scores AUC 0.871–0.886 on the four splits; against the only leak-free public solution (Lohani & Bansal) on its own rows: +0.011 [+0.004, +0.017] (DeLong p 0.0009), and +0.013 [+0.009, +0.016] over 30 new splits (better in 30). Under the leak-free thesis's protocol it reaches AUC 0.874 on average (98% of 50 splits above the thesis's 0.8605).
- **The honest ceiling.** Without post-contact columns no model in this study goes beyond AUC 0.886 or accuracy 81.4%. The accuracies above 90% reported for this file (two of the public solutions, which use post-contact columns; Jadli et al.; Yim et al., whose inputs are not listed) are out of reach for a model that scores new leads.
- Leads in the file: 9,240; converted 38.5%.
