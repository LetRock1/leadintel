# E6 Learned lead aging vs hand-set decay rules (simulated histories)

3 new histories (seeds 11, 12, 2026; 2,000 learners, 180 days; campaigns and A/B tests on, as in the product), made by the CRM's own code with lead aging switched on. Judged at the last learning run on people the CRM did nothing for at that moment, out-of-fold. Log-loss is a proper scoring rule (lower = better ranking AND more honest probabilities); calibration error by lead age = weighted mean |expected − actual| over the age groups (<7, 7–14, 14–30, 30+ days). Intervals: 95%, cluster bootstrap over people.

## Untouched control group (never worked on) (592 decision points, 23.8% bought)

| Score | Log-loss | Ours better by (log-loss) | Calibration error by age (points) | Ours better by | Over-predicts leads 7+ days old | Leads < 7 days |
|---|---|---|---|---|---|---|
| Score without lead age | 0.3755 | +0.0220 [+0.0093, +0.0344] | 6.38 | +1.46 [+0.01, +3.96] | +56% | +0% |
| Hand-set decay: −25% after 30 days (HubSpot-style) | 0.3695 | +0.0160 [+0.0059, +0.0267] | 5.42 | +0.53 [-1.02, +3.15] | +47% | +0% |
| Hand-set decay: −50% after 30 days | 0.3698 | +0.0164 [+0.0041, +0.0288] | 5.01 | +0.26 [-1.86, +3.40] | +39% | +0% |
| Inactivity decay: cap at 40 after 45 days away (Pardot-style) | 0.3755 | +0.0220 [+0.0093, +0.0344] | 6.38 | +1.46 [+0.01, +3.96] | +56% | +0% |
| **Lead age learned (ours)** | 0.3535 | — | 5.81 | — | +36% | +14% |
| Naive retrain (not told what the CRM did) | 0.3861 | +0.0326 [+0.0163, +0.0482] | 11.00 | +5.03 [+3.08, +5.61] | +55% | +38% |

## Worked-on leads the CRM left alone by a random pick (486 decision points, 24.7% bought)

| Score | Log-loss | Ours better by (log-loss) | Calibration error by age (points) | Ours better by | Over-predicts leads 7+ days old | Leads < 7 days |
|---|---|---|---|---|---|---|
| Score without lead age | 0.3762 | +0.0111 [+0.0014, +0.0202] | 4.87 | +1.92 [-0.77, +3.47] | +22% | -17% |
| Hand-set decay: −25% after 30 days (HubSpot-style) | 0.3810 | +0.0159 [+0.0063, +0.0252] | 5.24 | +2.20 [-0.22, +3.23] | +9% | -17% |
| Hand-set decay: −50% after 30 days | 0.3946 | +0.0295 [+0.0140, +0.0459] | 6.83 | +3.74 [+1.09, +5.04] | -4% | -17% |
| Inactivity decay: cap at 40 after 45 days away (Pardot-style) | 0.3762 | +0.0111 [+0.0014, +0.0202] | 4.87 | +1.92 [-0.77, +3.47] | +22% | -17% |
| **Lead age learned (ours)** | 0.3651 | — | 2.33 | — | +8% | -5% |
| Naive retrain (not told what the CRM did) | 0.3751 | +0.0101 [-0.0014, +0.0221] | 5.26 | +2.29 [-1.74, +4.88] | +26% | +16% |

## Both together (1,078 decision points, 24.2% bought)

| Score | Log-loss | Ours better by (log-loss) | Calibration error by age (points) | Ours better by | Over-predicts leads 7+ days old | Leads < 7 days |
|---|---|---|---|---|---|---|
| Score without lead age | 0.3758 | +0.0171 [+0.0087, +0.0250] | 5.64 | +2.11 [+0.05, +3.75] | +40% | -7% |
| Hand-set decay: −25% after 30 days (HubSpot-style) | 0.3747 | +0.0159 [+0.0086, +0.0230] | 4.52 | +1.27 [-0.90, +3.23] | +29% | -7% |
| Hand-set decay: −50% after 30 days | 0.3810 | +0.0222 [+0.0121, +0.0319] | 5.77 | +2.23 [-0.44, +4.45] | +19% | -7% |
| Inactivity decay: cap at 40 after 45 days away (Pardot-style) | 0.3758 | +0.0171 [+0.0087, +0.0250] | 5.64 | +2.11 [+0.05, +3.75] | +40% | -7% |
| **Lead age learned (ours)** | 0.3587 | — | 3.39 | — | +23% | +5% |
| Naive retrain (not told what the CRM did) | 0.3812 | +0.0220 [+0.0116, +0.0323] | 8.41 | +4.65 [+2.45, +5.27] | +42% | +28% |

## Inside the product: the learning runs of these histories

| History | Run | Control group bought | Ours expects | Naive expects | Decision | Learned lead age (log-odds: 7–14 / 14–30 / 30+) |
|---|---|---|---|---|---|---|
| seed 11 | 2026-05-28 | 37.5% | 64.4% | 68.5% | not_enough_data | — / — / — |
| seed 11 | 2026-06-27 | 43.8% | 43.8% | 47.7% | not_enough_data | — / — / — |
| seed 11 | 2026-07-27 | 32.6% | 32.7% | 38.9% | kept | — / — / — |
| seed 11 | 2026-08-26 | 29.2% | 31.4% | 38.0% | kept | — / — / — |
| seed 11 | 2026-09-25 | 24.3% | 25.9% | 33.3% | swapped | -0.43 / -0.68 / -1.30 |
| seed 11 | 2026-10-25 | 25.8% | 28.5% | 34.1% | kept | -0.43 / -0.68 / -1.30 |
| seed 12 | 2026-05-28 | 45.5% | 26.8% | 31.6% | not_enough_data | — / — / — |
| seed 12 | 2026-06-27 | 28.6% | 30.2% | 35.5% | not_enough_data | — / — / — |
| seed 12 | 2026-07-27 | 27.3% | 27.6% | 31.8% | kept | — / — / — |
| seed 12 | 2026-08-26 | 33.3% | 32.7% | 35.5% | kept | — / — / — |
| seed 12 | 2026-09-25 | 33.6% | 32.1% | 36.6% | kept | — / — / — |
| seed 12 | 2026-10-25 | 31.2% | 34.3% | 37.5% | swapped | -0.43 / -0.72 / -0.99 |
| seed 2026 | 2026-05-28 | 5.9% | 32.4% | 38.5% | not_enough_data | — / — / — |
| seed 2026 | 2026-06-27 | 15.7% | 27.7% | 34.0% | swapped | -1.29 / -0.75 / -0.66 |
| seed 2026 | 2026-07-27 | 11.4% | 24.2% | 31.8% | kept | -1.29 / -0.75 / -0.66 |
| seed 2026 | 2026-08-26 | 13.4% | 18.9% | 31.2% | kept | -1.29 / -0.75 / -0.66 |
| seed 2026 | 2026-09-25 | 14.6% | 20.5% | 32.1% | kept | -1.29 / -0.75 / -0.66 |
| seed 2026 | 2026-10-25 | 14.6% | 21.3% | 32.8% | swapped | -0.74 / -0.95 / -1.12 |

Over all 18 learning runs (weighted by control-group decision points): ours over-predicts the control group by +26.7%, the naive retrain by +65.1%. Swaps: seed 11 1, seed 12 1, seed 2026 2.
