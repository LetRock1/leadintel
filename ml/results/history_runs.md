# The simulated histories, checked against what is known to be true

6 histories (different random seeds), each 180 days, 2,000 simulated learners, the CRM running by itself: scoring, next-best-action with 15% random learning steps, campaigns with hold-outs, six A/B tests, auto-adopted winners, and the learning loop at days 30, 60, 90, 120, 150 and the end. The untouched control group is 5% of learners (never contacted). Made by `ml/experiments/history_check.py` from the history databases.

## 1. Is the learning loop fooling itself? (judged on the untouched control group)

Each row is one learning run. The control group's decision points are the moments the CRM would have acted on those people (it logged the decision but did nothing). *Expects* = the average predicted chance to buy within 14 days at those points; *bought* = how often they actually did.

| History | Run | Control group: people / decision points | Bought | Model in use expects | Naive retrain expects | v7.0 retrain expects | Ours expects | Log-loss naive | Log-loss v7.0 | Log-loss ours | Usual check picks | Decision |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| seed 2026 | 2026-05-28 | 9 / 17 | 5.9% | 35.2% | 38.5% | 32.4% | 32.4% | 0.9600 | 0.8139 | 0.8139 | naive | not_enough_data |
| seed 2026 | 2026-06-27 | 21 / 51 | 15.7% | 44.5% | 34.0% | 27.7% | 27.7% | 0.6128 | 0.5706 | 0.5706 | naive | swapped |
| seed 2026 | 2026-07-27 | 34 / 79 | 11.4% | 22.7% | 31.8% | 24.2% | 24.2% | 0.4937 | 0.4177 | 0.4177 | naive | kept |
| seed 2026 | 2026-08-26 | 46 / 119 | 13.4% | 23.4% | 31.2% | 24.2% | 18.9% | 0.4485 | 0.3863 | 0.3914 | naive | kept |
| seed 2026 | 2026-09-25 | 59 / 151 | 14.6% | 24.5% | 32.1% | 25.1% | 20.5% | 0.4545 | 0.3909 | 0.3883 | naive | kept |
| seed 2026 | 2026-10-25 | 77 / 199 | 14.6% | 25.9% | 32.8% | 26.1% | 21.3% | 0.4387 | 0.3724 | 0.3536 | naive | swapped |
| seed 11 | 2026-05-28 | 9 / 16 | 37.5% | 50.1% | 68.5% | 64.4% | 64.4% | 0.6230 | 0.5196 | 0.5196 | naive | not_enough_data |
| seed 11 | 2026-06-27 | 19 / 48 | 43.8% | 50.1% | 47.7% | 43.8% | 43.8% | 0.3464 | 0.3430 | 0.3430 | naive | not_enough_data |
| seed 11 | 2026-07-27 | 35 / 86 | 32.6% | 44.4% | 38.9% | 32.7% | 32.7% | 0.3796 | 0.3780 | 0.3780 | naive | kept |
| seed 11 | 2026-08-26 | 42 / 106 | 29.2% | 43.5% | 38.0% | 31.4% | 31.4% | 0.3830 | 0.3637 | 0.3637 | naive | kept |
| seed 11 | 2026-09-25 | 59 / 140 | 24.3% | 37.9% | 33.3% | 26.7% | 25.9% | 0.3521 | 0.3265 | 0.3225 | naive | swapped |
| seed 11 | 2026-10-25 | 79 / 194 | 25.8% | 25.0% | 34.1% | 28.9% | 28.5% | 0.3328 | 0.3111 | 0.3304 | naive | kept |
| seed 12 | 2026-05-28 | 8 / 11 | 45.5% | 20.1% | 31.6% | 26.8% | 26.8% | 0.5064 | 0.5334 | 0.5334 | naive | not_enough_data |
| seed 12 | 2026-06-27 | 18 / 35 | 28.6% | 30.3% | 35.5% | 30.2% | 30.2% | 0.4463 | 0.4399 | 0.4399 | naive | not_enough_data |
| seed 12 | 2026-07-27 | 31 / 66 | 27.3% | 33.9% | 31.8% | 27.6% | 27.6% | 0.3873 | 0.3883 | 0.3883 | naive | kept |
| seed 12 | 2026-08-26 | 40 / 96 | 33.3% | 38.2% | 35.5% | 31.9% | 32.7% | 0.3548 | 0.3525 | 0.3508 | naive | kept |
| seed 12 | 2026-09-25 | 56 / 134 | 33.6% | 39.1% | 36.6% | 32.6% | 32.1% | 0.3615 | 0.3596 | 0.3620 | naive | kept |
| seed 12 | 2026-10-25 | 79 / 199 | 31.2% | 40.7% | 37.5% | 33.8% | 34.3% | 0.3854 | 0.3759 | 0.3782 | naive | swapped |
| seed 13 | 2026-05-28 | 10 / 23 | 34.8% | 39.2% | 41.2% | 40.0% | 40.0% | 0.2693 | 0.2724 | 0.2724 | ours | not_enough_data |
| seed 13 | 2026-06-27 | 20 / 57 | 33.3% | 45.8% | 42.4% | 42.0% | 42.0% | 0.3524 | 0.3498 | 0.3498 | naive | kept |
| seed 13 | 2026-07-27 | 32 / 85 | 35.3% | 46.5% | 41.6% | 40.9% | 40.9% | 0.3766 | 0.3821 | 0.3821 | naive | kept |
| seed 13 | 2026-08-26 | 42 / 102 | 32.4% | 42.3% | 38.6% | 37.5% | 37.5% | 0.3381 | 0.3323 | 0.3323 | naive | kept |
| seed 13 | 2026-09-25 | 64 / 154 | 30.5% | 40.9% | 37.2% | 35.6% | 35.3% | 0.3583 | 0.3499 | 0.3474 | naive | swapped |
| seed 13 | 2026-10-25 | 83 / 211 | 28.4% | 35.0% | 36.6% | 34.7% | 32.5% | 0.3401 | 0.3295 | 0.3202 | naive | kept |
| seed 14 | 2026-05-28 | 10 / 19 | 15.8% | 43.5% | 51.9% | 41.4% | 41.4% | 0.9725 | 0.8220 | 0.8220 | naive | not_enough_data |
| seed 14 | 2026-06-27 | 20 / 57 | 19.3% | 49.0% | 42.9% | 34.1% | 34.1% | 0.7063 | 0.6126 | 0.6126 | naive | kept |
| seed 14 | 2026-07-27 | 33 / 91 | 12.1% | 46.6% | 39.3% | 31.3% | 26.2% | 0.6268 | 0.5065 | 0.4804 | naive | swapped |
| seed 14 | 2026-08-26 | 46 / 138 | 13.8% | 25.6% | 41.5% | 31.8% | 26.7% | 0.5909 | 0.4476 | 0.4052 | naive | kept |
| seed 14 | 2026-09-25 | 60 / 179 | 17.3% | 26.0% | 43.4% | 34.0% | 30.3% | 0.5982 | 0.4680 | 0.4340 | naive | kept |
| seed 14 | 2026-10-25 | 81 / 247 | 20.2% | 23.7% | 40.9% | 34.0% | 27.6% | 0.5671 | 0.4918 | 0.4498 | naive | kept |
| seed 15 | 2026-05-28 | 7 / 10 | 40.0% | 35.2% | 47.8% | 45.4% | 45.4% | 0.5854 | 0.5601 | 0.5601 | naive | not_enough_data |
| seed 15 | 2026-06-27 | 19 / 45 | 35.6% | 44.0% | 44.4% | 37.5% | 37.5% | 0.3521 | 0.3205 | 0.3205 | naive | not_enough_data |
| seed 15 | 2026-07-27 | 32 / 69 | 23.2% | 35.4% | 34.4% | 25.4% | 25.4% | 0.2617 | 0.2107 | 0.2107 | naive | swapped |
| seed 15 | 2026-08-26 | 43 / 93 | 24.7% | 24.8% | 35.2% | 26.1% | 27.1% | 0.3093 | 0.2651 | 0.2734 | naive | kept |
| seed 15 | 2026-09-25 | 57 / 120 | 24.2% | 26.3% | 35.0% | 25.0% | 26.8% | 0.3157 | 0.2689 | 0.2783 | naive | kept |
| seed 15 | 2026-10-25 | 81 / 174 | 24.7% | 27.1% | 36.1% | 28.0% | 30.4% | 0.3294 | 0.2836 | 0.2920 | naive | kept |

- **Ours is each step's effect from the CRM's own experiment against its never-contacted control group (v7.1; the control group also gives those effects, and each person is predicted by a model fitted without them; ml/results/anchored_check.md judges on a group nothing learns from).** Against v7.0's retrain (told what the CRM did, effects learned by the model), on the control group: better in **10**, worse in **7** and the same in 19 of 36 runs (the same: no step had enough control-group decision points yet, so the update works as v7.0's); mean log-loss ours 0.4108, v7.0 0.4144, naive 0.4588. Over-statement of the control group's buying, mean over these runs: ours +44%, v7.0 +50%, naive +80%.

- Runs with a control-group check: **36**. Ours predicted the control group better (lower log-loss) than the naive retrain in **31 of 36**, and better than the model in use at that time in 23 of 36.
- The usual check (fit on all live outcomes, which the CRM's own follow-ups shaped) would have picked the naive retrain in **35 of 36** runs.
- How much each overstated the control group's buying, mean over all runs: naive **+80%**, ours **+44%**, the model in use before the run +62%. (Ours' remaining gap sits in leads older than a week: ml/results/followups_check.md; the loop also learns the lead's age: ml/results/lead_age_check.md.)
- Final runs only (most data): naive +59%, ours +23%.
- Lead model swapped 7 times over 36 runs (only when better on the control group in ≥90% of bootstrap resamples); next-best-action swapped 2 times.

## 2. What the loop learned about this business, vs the truth

The simulated business differs from the base model's training data in three documented ways (log-odds of buying, `WORLD_DRIFT` in backend/app/simulation/behaviour.py). Below: what the final learning run of each history learned (ours), and whether the CRM is using a learned model.

| History | Opted in to WhatsApp (true +0.6) | Browses on mobile (true -0.5) | Joined a webinar (true +0.7) | Largest other corrections | Model in use at the end |
|---|---|---|---|---|---|
| seed 2026 | +0.62 | -0.41 | +0.62 | Clicked our emails -0.71, Downloaded a brochure +0.50, Added to cart +0.32 | learned model from 2026-10-25 |
| seed 11 | +0.54 | -0.26 | +0.48 | Clicked our emails -0.62, Watched a course video +0.27, Read testimonials +0.20 | learned model from 2026-09-25 |
| seed 12 | +0.77 | -0.45 | +0.39 | Clicked our emails -1.56, Started checkout +0.43, Added to cart +0.19 | learned model from 2026-10-25 |
| seed 13 | +0.60 | -0.57 | +0.38 | Clicked our emails -1.02, Opened chat +0.27, Added to cart +0.19 | learned model from 2026-09-25 |
| seed 14 | +0.52 | -0.37 | +0.52 | Clicked our emails -0.73, Downloaded a brochure +0.16, Watched a course video +0.16 | learned model from 2026-07-27 |
| seed 15 | +0.51 | -0.45 | +0.34 | Clicked our emails -1.14, Started checkout +0.47, Sent an enquiry +0.35 | learned model from 2026-07-27 |

Learned vs true, range over the histories: Opted in to WhatsApp +0.51 to +0.77 (true +0.6, right sign in 6 of 6); Browses on mobile -0.57 to -0.26 (true -0.5, right sign in 6 of 6); Joined a webinar +0.34 to +0.62 (true +0.7, right sign in 6 of 6).

Weights are log-odds added for a lead with the signal. They are ridge-shrunk toward 0 and fitted together with a recalibration of the base score, so only the sign and rough size should match.
The large negative correction for *Clicked our emails* is not one of the designed differences, and it is right: in the base model's training data email opens depend only on the learner's interest, but in a running CRM they also depend on how many emails the CRM has already sent (learners it kept emailing without a purchase pile up clicks), so a click says less about interest than the base model assumed.
A learned model is used only once the untouched control group confirms it with 90% confidence. With about 80 untouched people after six months that bar is high: where no model was confirmed, the CRM kept the starting model even though the new one was often better (section 1). A larger control group or a lower bar (crm_settings.json) makes it switch sooner, at the cost of fewer people worked on or more risk of switching on noise.

The naive retrain learns similar signal weights to ours (median difference 0.04, largest 0.50 log-odds). Its main mistake is the overall level: most decision points were followed by an action of the CRM, and the naive retrain folds the average effect of those actions into every lead's baseline — which is what section 1 shows.

## 3. The CRM's total impact (worked-on leads vs the untouched control group)

Share of learners who bought within 30 days of signing up (learners who signed up at least 30 days before the end).

| History | Worked on | Control group | Difference (95% interval) | p |
|---|---|---|---|---|
| seed 2026 | 449/1524 = 29.5% | 8/78 = 10.3% | +19.2 pts (+10.2 to +24.7) | 0.000 |
| seed 11 | 497/1562 = 31.8% | 13/80 = 16.2% | +15.6 pts (+5.7 to +22.5) | 0.003 |
| seed 12 | 495/1533 = 32.3% | 20/80 = 25.0% | +7.3 pts (-3.4 to +15.8) | 0.173 |
| seed 13 | 467/1561 = 29.9% | 19/80 = 23.8% | +6.2 pts (-4.5 to +14.5) | 0.239 |
| seed 14 | 501/1531 = 32.7% | 15/78 = 19.2% | +13.5 pts (+3.1 to +21.1) | 0.013 |
| seed 15 | 458/1532 = 29.9% | 13/78 = 16.7% | +13.2 pts (+3.2 to +20.3) | 0.012 |

Mean difference +12.5 pts, positive in 6 of 6 histories; the 95% interval is above zero in 4 of 6 (the control group is only ~5% of learners, so each single history has a wide interval).
All 6 independent histories together: worked on 2,867/9,243 = 31.0%, control group 88/474 = 18.6%: **+12.5 pts** (95% interval +8.6 to +15.8, p = 0.0000).

## 4. A/B test verdicts vs the true effects

| History | Test | Metric | People per arm | Verdict | Lift of the best variant (95% interval) | True effect | Judged |
|---|---|---|---|---|---|---|---|
| seed 2026 | 10% vs 20% coupon | purchase | control 47, A 89, B 101 | no_difference | A vs control: +8.3 pts (-6.9 to +20.3) | both coupons raise buying (20% more); the audience is far below the planned size | missed (too few people) |
| seed 2026 | Webinar invite vs brochure | purchase | control 74, A 124, B 146 | no_difference | B vs control: +4.8 pts (-2.1 to +10.5) | true null: neither email changes buying | correct (true null) |
| seed 2026 | Subject line: benefit vs urgency | click | A 295, B 316 | winner B | B vs A: +16.9 pts (+10.5 to +23.1) | urgency subject: +0.8 log-odds on clicks, same buying | correct |
| seed 2026 | Short mobile email vs long email | purchase | control 164, A 314, B 299 | no_difference | B vs control: +4.5 pts (-1.8 to +9.9) | short email +1.4 on phones only; long email +0.4 on desktop only | missed (too few people) |
| seed 2026 | Personalised course pick vs generic newsletter | purchase | control 197, A 380, B 385 | winner B | B vs control: +6.6 pts (+1.2 to +11.2) | personalised +1.2 log-odds on buying; newsletter nothing | correct |
| seed 2026 | EMI message vs refund guarantee | purchase | control 223, A 402, B 421 | running | A vs control: -0.0 pts (-4.6 to +3.7) | sent 5 days before the end: cannot be final yet | running (correct: not final) |
| seed 11 | 10% vs 20% coupon | purchase | control 52, A 99, B 114 | no_difference | A vs control: +6.4 pts (-7.4 to +17.3) | both coupons raise buying (20% more); the audience is far below the planned size | missed (too few people) |
| seed 11 | Webinar invite vs brochure | purchase | control 78, A 132, B 139 | no_difference | B vs control: +5.2 pts (-2.5 to +11.6) | true null: neither email changes buying | correct (true null) |
| seed 11 | Subject line: benefit vs urgency | click | A 283, B 337 | winner B | B vs A: +11.1 pts (+4.8 to +17.2) | urgency subject: +0.8 log-odds on clicks, same buying | correct |
| seed 11 | Short mobile email vs long email | purchase | control 147, A 322, B 304 | winner B (on phones: B) | B vs control: +8.4 pts (+2.2 to +13.7) | short email +1.4 on phones only; long email +0.4 on desktop only | correct |
| seed 11 | Personalised course pick vs generic newsletter | purchase | control 179, A 379, B 386 | no_difference | B vs control: +3.6 pts (-1.7 to +7.8) | personalised +1.2 log-odds on buying; newsletter nothing | missed (too few people) |
| seed 11 | EMI message vs refund guarantee | purchase | control 201, A 391, B 423 | running | B vs control: +3.5 pts (-0.4 to +6.6) | sent 5 days before the end: cannot be final yet | running (correct: not final) |
| seed 12 | 10% vs 20% coupon | purchase | control 46, A 83, B 93 | no_difference | B vs control: +7.4 pts (-9.9 to +21.2) | both coupons raise buying (20% more); the audience is far below the planned size | missed (too few people) |
| seed 12 | Webinar invite vs brochure | purchase | control 69, A 126, B 129 | no_difference | B vs control: -4.1 pts (-14.6 to +3.0) | true null: neither email changes buying | correct (true null) |
| seed 12 | Subject line: benefit vs urgency | click | A 292, B 279 | winner B | B vs A: +16.8 pts (+9.9 to +23.5) | urgency subject: +0.8 log-odds on clicks, same buying | correct |
| seed 12 | Short mobile email vs long email | purchase | control 150, A 279, B 270 | no_difference (on phones: B) | B vs control: +3.1 pts (-3.2 to +8.3) | short email +1.4 on phones only; long email +0.4 on desktop only | missed (too few people) |
| seed 12 | Personalised course pick vs generic newsletter | purchase | control 189, A 357, B 393 | no_difference | B vs control: +4.9 pts (-0.9 to +9.6) | personalised +1.2 log-odds on buying; newsletter nothing | missed (too few people) |
| seed 12 | EMI message vs refund guarantee | purchase | control 215, A 383, B 418 | running | A vs control: +2.1 pts (-1.8 to +5.2) | sent 5 days before the end: cannot be final yet | running (correct: not final) |
| seed 13 | 10% vs 20% coupon | purchase | control 49, A 102, B 108 | no_difference | B vs control: +3.7 pts (-11.2 to +14.7) | both coupons raise buying (20% more); the audience is far below the planned size | missed (too few people) |
| seed 13 | Webinar invite vs brochure | purchase | control 55, A 133, B 146 | no_difference | A vs control: +1.9 pts (-8.0 to +7.8) | true null: neither email changes buying | correct (true null) |
| seed 13 | Subject line: benefit vs urgency | click | A 300, B 312 | winner B | B vs A: +16.5 pts (+10.2 to +22.7) | urgency subject: +0.8 log-odds on clicks, same buying | correct |
| seed 13 | Short mobile email vs long email | purchase | control 168, A 342, B 298 | no_difference | B vs control: +2.2 pts (-4.2 to +7.6) | short email +1.4 on phones only; long email +0.4 on desktop only | missed (too few people) |
| seed 13 | Personalised course pick vs generic newsletter | purchase | control 197, A 391, B 408 | no_difference | B vs control: +5.0 pts (-0.8 to +9.7) | personalised +1.2 log-odds on buying; newsletter nothing | missed (too few people) |
| seed 13 | EMI message vs refund guarantee | purchase | control 228, A 411, B 424 | running | B vs control: +1.6 pts (-2.4 to +4.8) | sent 5 days before the end: cannot be final yet | running (correct: not final) |
| seed 14 | 10% vs 20% coupon | purchase | control 46, A 91, B 110 | no_difference | B vs control: +3.3 pts (-12.8 to +15.3) | both coupons raise buying (20% more); the audience is far below the planned size | missed (too few people) |
| seed 14 | Webinar invite vs brochure | purchase | control 60, A 119, B 136 | no_difference | B vs control: +1.3 pts (-7.8 to +6.7) | true null: neither email changes buying | correct (true null) |
| seed 14 | Subject line: benefit vs urgency | click | A 298, B 296 | winner B | B vs A: +8.9 pts (+2.0 to +15.7) | urgency subject: +0.8 log-odds on clicks, same buying | correct |
| seed 14 | Short mobile email vs long email | purchase | control 142, A 291, B 305 | no_difference | B vs control: +5.9 pts (-0.8 to +11.3) | short email +1.4 on phones only; long email +0.4 on desktop only | missed (too few people) |
| seed 14 | Personalised course pick vs generic newsletter | purchase | control 191, A 362, B 385 | winner B | B vs control: +6.7 pts (+0.9 to +11.7) | personalised +1.2 log-odds on buying; newsletter nothing | correct |
| seed 14 | EMI message vs refund guarantee | purchase | control 217, A 389, B 393 | running | A vs control: +1.5 pts (-3.1 to +5.2) | sent 5 days before the end: cannot be final yet | running (correct: not final) |
| seed 15 | 10% vs 20% coupon | purchase | control 45, A 105, B 100 | no_difference | A vs control: +3.8 pts (-12.7 to +16.2) | both coupons raise buying (20% more); the audience is far below the planned size | missed (too few people) |
| seed 15 | Webinar invite vs brochure | purchase | control 68, A 122, B 121 | no_difference | A vs control: +5.1 pts (-3.6 to +12.1) | true null: neither email changes buying | correct (true null) |
| seed 15 | Subject line: benefit vs urgency | click | A 285, B 276 | winner B | B vs A: +14.2 pts (+7.6 to +20.7) | urgency subject: +0.8 log-odds on clicks, same buying | correct |
| seed 15 | Short mobile email vs long email | purchase | control 160, A 317, B 286 | no_difference (on phones: B) | B vs control: +5.8 pts (-0.4 to +11.1) | short email +1.4 on phones only; long email +0.4 on desktop only | missed (too few people) |
| seed 15 | Personalised course pick vs generic newsletter | purchase | control 198, A 383, B 385 | no_difference | B vs control: +5.3 pts (-0.1 to +9.9) | personalised +1.2 log-odds on buying; newsletter nothing | missed (too few people) |
| seed 15 | EMI message vs refund guarantee | purchase | control 212, A 407, B 433 | running | B vs control: -3.1 pts (-8.3 to +0.7) | sent 5 days before the end: cannot be final yet | running (correct: not final) |

Tally: correct: 15, missed: 15, running: 6. Wrong verdicts (a winner or loser that is not true): **0**. *Missed* = a real effect the test was too small to confirm; the plan shown before sending warns when the audience is smaller than needed.

### Adopted winners

| History | From test | Adopted email | Audience | Status | Last check |
|---|---|---|---|---|---|
| seed 2026 | Subject line: benefit vs urgency | Urgency subject | All leads | superseded | Still winning: +21.6 points vs the old email (95% interval +6.1 to +31.7). (Adopted winner: 294 people, 37.4%, Old standard email (check group): 38 people, 15.8%) |
| seed 2026 | Personalised course pick vs generic newsletter | Personalised course pick | All leads | active | Collecting evidence: 65 people got the adopted email, 4 the old one (need 30+ each). (Adopted winner: 65 people, 6.2%, Old standard email (check group): 4 people, 25.0%) |
| seed 11 | Subject line: benefit vs urgency | Urgency subject | All leads | superseded | Collecting evidence: 156 people got the adopted email, 21 the old one (need 30+ each). (Adopted winner: 156 people, 41.0%, Old standard email (check group): 21 people, 38.1%) |
| seed 11 | Short mobile email vs long email | Short mobile-first email | All leads | active | Collecting evidence: 229 people got the adopted email, 18 the old one (need 30+ each). (Adopted winner: 229 people, 28.4%, Old standard email (check group): 18 people, 16.7%) |
| seed 12 | Subject line: benefit vs urgency | Urgency subject | All leads | confirmed | Still winning: +17.9 points vs the old email (95% interval +3.5 to +29.2). (Adopted winner: 387 people, 43.9%, Old standard email (check group): 50 people, 26.0%) |
| seed 13 | Subject line: benefit vs urgency | Urgency subject | All leads | active | Collecting evidence: 117 people got the adopted email, 20 the old one (need 30+ each). (Adopted winner: 117 people, 42.7%, Old standard email (check group): 20 people, 5.0%) |
| seed 14 | Subject line: benefit vs urgency | Urgency subject | All leads | superseded | Still winning: +25.9 points vs the old email (95% interval +9.2 to +37.4). (Adopted winner: 258 people, 45.3%, Old standard email (check group): 36 people, 19.4%) |
| seed 14 | Personalised course pick vs generic newsletter | Personalised course pick | All leads | active | Collecting evidence: 78 people got the adopted email, 7 the old one (need 30+ each). (Adopted winner: 78 people, 6.4%, Old standard email (check group): 7 people, 0.0%) |
| seed 15 | Subject line: benefit vs urgency | Urgency subject | All leads | active | No clear difference yet (+14.1 points; the 95% interval still includes zero). (Adopted winner: 268 people, 43.3%, Old standard email (check group): 48 people, 29.2%) |

## 5. The pipeline in rupees, inside the product

Each learner's first automatic decision with a full 14-day outcome window before the end of the history, in 6 histories. The control group is chosen at random and never contacted, so the difference between worked-on leads and the control group is what the CRM's work added. *Expected* is what the CRM's numbers said at that moment (the score in use then); *actual* is the revenue (fee paid, after any discount) within the window, per learner, with a 95% interval from resampling learners. The worked-on leads' actual revenue includes every later step of the CRM within the window, while the estimate counts only the first step.

**All first decisions** (10,056 learners, 477 of them in the control group)

| | Expected per learner | Actual per learner (95% interval) |
|---|---|---|
| Control group: comes in anyway (chance to buy with no step x fee) | ₹7,903 | ₹6,459 (₹4,889 to ₹8,099) |
| Worked-on leads: with the step the CRM took | ₹9,783 | ₹9,639 (₹9,222 to ₹10,061) |
| What the CRM's work adds: the step it took (its own estimate) against worked-on minus control | ₹2,310 | ₹3,180 (₹1,511 to ₹4,800) |
| The best step's extra profit (what the pipeline calls 'the team can add') | ₹2,627 | |

Share who bought within the window: control group 13.8% against an expected 16.6%; worked-on leads 21.2% against 22.8%.

**First decisions after the score was first updated from this CRM's own outcomes** (3,309 learners, 161 of them in the control group)

| | Expected per learner | Actual per learner (95% interval) |
|---|---|---|
| Control group: comes in anyway (chance to buy with no step x fee) | ₹6,957 | ₹8,137 (₹5,093 to ₹11,709) |
| Worked-on leads: with the step the CRM took | ₹7,620 | ₹9,488 (₹8,744 to ₹10,231) |
| What the CRM's work adds: the step it took (its own estimate) against worked-on minus control | ₹1,840 | ₹1,351 (₹-2,209 to ₹4,619) |
| The best step's extra profit (what the pipeline calls 'the team can add') | ₹2,105 | |

Share who bought within the window: control group 14.9% against an expected 14.0%; worked-on leads 20.7% against 17.8%.
