# E3 Learning loop on real randomized data (Hillstrom, 42,613 customers: men's email vs none)

50 repeats (random splits: 10% before the CRM, two rounds of 30%, 30% held out). The CRM emails the top 30% by its score, 15% of its choices random, and never contacts its 5% control group; it retrains twice. Everything is judged on held-out customers the real experiment left alone (visit rate 10.6%). Intervals: 95%, corrected resampled t-test (Nadeau & Bengio 2003).

## The precise metric: feedback bias

**Feedback bias** = mean predicted minus actual visit rate of held-out customers the randomized experiment left alone (percentage points). A score that learned the CRM's own emails as customer quality over-predicts what customers do when nobody contacts them. No selection is involved, so the no-loop reference sits at zero.

| Method | Feedback bias (points) | In % of the true rate | Over-predicts its own targeted 30% by | Honest AUC | Honest log-loss |
|---|---|---|---|---|---|
| Naive retrain (how CRMs retrain) | +2.35 [+1.80, +2.89] | +22 [+16, +28]% | +37.7 [+28.0, +47.4]% | 0.637 | 0.3294 |
| Control group only (clinical-ML holdout approach) | +0.08 [-0.92, +1.08] | +1 [-9, +10]% | +19.2 [+3.0, +35.4]% | 0.614 | 0.3322 |
| Left-alone customers, weighted (IPW) | +0.04 [-0.83, +0.92] | +0 [-8, +9]% | +16.3 [+0.8, +31.7]% | 0.622 | 0.3311 |
| **Ours** (told what the CRM did) | +0.33 [-0.31, +0.96] | +3 [-3, +9]% | +9.3 [+1.3, +17.3]% | 0.638 | 0.3257 |
| Reference: no loop at all (oracle) | +0.05 [-0.54, +0.64] | +1 [-5, +6]% | +6.7 [-1.5, +14.9]% | 0.637 | 0.3256 |

- **Best of all deployable methods on one proper scoring rule:** ours has the lowest honest log-loss of naive, holdout, IPW and ours in **49 of 50** repeats (and is level with the no-loop oracle: lower in 20 of 50).
- **Ours removes 88 [72, 104]% of the feedback bias** of naive retraining; ours minus the no-loop reference: +0.28 [-0.09, +0.65] points. Ours is less biased than naive in **50 of 50** repeats.
- Against the clinical-ML holdout approach (unbiased by construction, but it learns from the control group only): honest AUC +0.024 [+0.010, +0.037] higher, log-loss +0.0065 [+0.0023, +0.0106] lower with ours (ours better in 50 and 50 of 50).
- Against IPW (left-alone customers, weighted): the same idea, but the weights (up to 13x) make it noisy: its feedback bias varies with sd 0.65 points between repeats, ours 0.47.
- Against naive: honest AUC +0.001 [-0.007, +0.009], log-loss +0.0037 [+0.0017, +0.0057] lower with ours (ours more accurate on the truth in 49 of 50).
- The last column includes the winner's curse: picking the top 30% of any noisy score over-predicts them (the no-loop reference: +6.7%); scores learned from fewer people are noisier, so the holdout and IPW models show more of it.

## The accuracy illusion

| Method | AUC on the data its own policy logged | Honest AUC | Illusion |
|---|---|---|---|
| Naive retrain (how CRMs retrain) | 0.683 | 0.637 | +0.046 [+0.036, +0.056] |
| Control group only (clinical-ML holdout approach) | 0.660 | 0.614 | +0.046 [+0.035, +0.057] |
| Left-alone customers, weighted (IPW) | 0.667 | 0.622 | +0.045 [+0.035, +0.055] |
| **Ours** (told what the CRM did) | 0.681 | 0.638 | +0.043 [+0.033, +0.053] |
| Reference: no loop at all (oracle) | 0.681 | 0.637 | +0.044 [+0.033, +0.055] |

Every model looks better on the data its own emails shaped: an AUC measured on a CRM's own logged data is not its accuracy.

## Choosing the model: naive vs ours

| Check | Result |
|---|---|
| Truth: honest log-loss on all held-out left-alone customers | ours better in 49 of 50 |
| Usual check: log-loss on the CRM's own logged data | picks naive in **50 of 50** |
| Our check with naive in place: the control group, swap if better in >= 90% of 300 resamples | swaps to ours in 11 of 50; otherwise keeps naive |
| Our check with ours in place | swaps to naive in **2 of 50** |

The held-out period's control group has 323 left-alone people on average: our check rarely makes a wrong swap; with so few people it often keeps the current model (the right swap needs more control-group outcomes).

## Different exploration rates

| Random share of the CRM's choices | Feedback bias, naive (points) | Feedback bias, ours | Bias removed | Honest AUC naive / ours |
|---|---|---|---|---|
| 0% (25 repeats) | +2.24 [+1.62, +2.86] | +0.30 [-0.49, +1.09] | 90 [72, 107]% | 0.636 / 0.639 |
| 5% (25 repeats) | +2.24 [+1.62, +2.86] | +0.32 [-0.42, +1.07] | 89 [72, 106]% | 0.637 / 0.639 |
| 15% (50 repeats) | +2.35 [+1.80, +2.89] | +0.33 [-0.31, +0.96] | 88 [72, 104]% | 0.637 / 0.638 |
| 30% (25 repeats) | +2.48 [+1.91, +3.05] | +0.37 [-0.33, +1.06] | 88 [76, 100]% | 0.638 / 0.637 |

Ours needs customers the CRM did NOT email among those it would target (overlap). The random choices give some, and so does the control group, which the CRM never contacts: that is why the result hardly depends on the exploration rate here, even at 0%.
