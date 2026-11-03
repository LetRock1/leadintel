# Where the learning loop's remaining gap comes from (simulated histories)

3 histories per rule (seeds 11, 12, 2026; 2,000 learners, 180 days; campaigns and A/B tests off), the same people and the same random draws under both rules. Each learning run checks the models on the untouched control group: how many of them each model expected to buy within 14 days, and how many did. Overstatement = expected / bought − 1, pooled over the runs of a history (weighted by the control group's decision points).

## 1. Later follow-ups in the outcome window

| Rule | History | Learning runs | CRM decisions | Control group bought (last run) | Naive expects | Ours expects | Naive overstates | Ours overstates |
|---|---|---|---|---|---|---|---|---|
| Usual | seed 11 | 6 | 4,607 | 23.4% (197 points) | 33.2% | 26.1% | +51.9% | +15.9% |
| Usual | seed 12 | 6 | 4,473 | 32.6% (193 points) | 34.8% | 29.0% | +2.7% | -15.0% |
| Usual | seed 2026 | 6 | 4,528 | 15.2% (211 points) | 37.5% | 28.4% | +156.9% | +106.7% |
| One touch per 14 days | seed 11 | 6 | 2,388 | 14.1% (99 points) | 22.6% | 19.5% | +54.9% | +34.0% |
| One touch per 14 days | seed 12 | 6 | 2,378 | 19.0% (105 points) | 23.9% | 18.8% | +35.8% | +6.9% |
| One touch per 14 days | seed 2026 | 6 | 2,337 | 14.8% (108 points) | 22.9% | 17.6% | +42.5% | +12.5% |

| Rule | Learning runs | Naive overstates | Ours overstates |
|---|---|---|---|
| Usual: the CRM decides at every trigger | 18 | +56.2% | +24.5% |
| One touch per 14 days: nothing else in a decision's outcome window | 18 | +43.8% | +16.9% |

Without later follow-ups in the outcome window, our model's gap goes from +24.5% to +16.9% (so later follow-ups explain part of it); the naive retrain's from +56.2% to +43.8%. Ours is below the naive retrain in every history. Single histories vary a lot (ours -15% to +107%): the control group is small.

## 2. Where the gap is: by the lead's age at the decision (last learning run of each history)

Two groups of people the CRM did nothing for at that moment: the **control group** (never worked on) and **worked-on leads it left alone by a random pick** (the 15% random choices). Pooled over the histories.

| Rule | Group | Younger than 7 days: points · bought · ours expects | 7 days or older: points · bought · ours expects |
|---|---|---|---|
| Usual | Control group (never worked on) | 344 · 22.4% · 19.7% (-12%) | 257 · 24.9% · 38.7% (+56%) |
| Usual | Worked-on leads, left alone by a random pick | 265 · 24.5% · 19.6% (-20%) | 160 · 28.1% · 33.0% (+17%) |
| One touch per 14 days | Control group (never worked on) | 228 · 13.2% · 13.0% (-1%) | 84 · 23.8% · 33.8% (+42%) |
| One touch per 14 days | Worked-on leads, left alone by a random pick | 147 · 11.6% · 11.4% (-1%) | 62 · 16.1% · 31.0% (+92%) |

Read with care: these are a few hundred decision points per cell (the control group is 5% of the learners); the pattern across the cells is the result, not the exact percentages.

## 3. The fix, tested here and used by the CRM: the lead's age as a learned input

The same live layer with the lead's age since sign-up (7–14 days, 14–30 days, 30+ days) as inputs that stay in the score, like time away. Out-of-fold, every history and both rules pooled:

| Group | Points | Bought | Ours expects (log-loss) | With lead age (log-loss) |
|---|---|---|---|---|
| Control group, younger than 7 days | 572 | 18.7% | 17.0% (-9%; 0.3241) | 19.6% (+5%; 0.3142) |
| Control group, 7 days or older | 341 | 24.6% | 37.5% (+52%; 0.5000) | 30.8% (+25%; 0.4414) |
| Control group, all | 913 | 20.9% | 24.7% (+18%; 0.3898) | 23.8% (+14%; 0.3617) |
| Worked-on leads, left alone by a random pick, younger than 7 days | 412 | 19.9% | 16.7% (-16%; 0.3629) | 19.4% (-3%; 0.3517) |
| Worked-on leads, left alone by a random pick, 7 days or older | 222 | 24.8% | 32.4% (+31%; 0.4788) | 27.2% (+10%; 0.4645) |
| Worked-on leads, left alone by a random pick, all | 634 | 21.6% | 22.2% (+3%; 0.4035) | 22.1% (+2%; 0.3912) |

Learned effect of the lead's age (log-odds, range over the histories): 7–14 days -1.18 to -0.35; 14–30 days -1.37 to -0.85; 30+ days -1.95 to -1.34.
