# E9: the money features against known truth

Simulated learners whose true response to every step is known, the production code and the starting models (lead_model.starter.pkl, nba_model.starter.pkl). Every rule sees the same learners in the same order with the same predictions and is scored with the true probabilities as expected profit (no outcome noise). INR throughout.

## a. A monthly discount budget

10 runs of 2 months (300 automatic decisions a weekday, fewer at weekends; the first 7 days only build the price). If every coupon that pays were sent, a month of coupons would cost about 10,059,890 of expected discount; the budgets below are shares of that. Calls are left out here (E7 prices them). 'Share' is the part of the value of the budget that each rule captures, between no coupons (0%) and the best allocation with hindsight (100%), with a 95% interval across months and runs. 'Budget used' is the true expected discount given, as a share of the budget (the rules count the predicted cost when a coupon goes out, as the CRM does for open coupons).

Rules compared:

- **no coupons**: no coupon is ever given (what the other steps earn on their own)
- **cart recovery**: the usual rule: a 10% coupon to every left cart while money is left; everyone else gets the model's best step without a coupon
- **first come**: the model's best step for each learner, coupons included, until the money is used up
- **fixed price**: a coupon only when it adds more than one price per rupee of discount, the same all month (from the week before the month)
- **re-solved price**: ours (production app.ml.budget): the price is worked out again at every decision from the money left, the days left and the last 7 days of decisions
- **hindsight**: the best single price for the month, chosen knowing the whole month's decisions in advance (the best any rule could do with the same predictions)
- **true hindsight**: the same with the true effects and costs (the ceiling, with perfect prediction too)

| Budget | First come | Cart recovery | Fixed price | Re-solved price (ours) | Ours against first come, a month |
|---|---|---|---|---|---|
| 10% (1,005,989) | 37.3% | -26.3% | 95.3% | 96.8% | +1,573,914 (+/- 38,217) |
| 25% (2,514,973) | 49.9% | -35.5% | 89.2% | 99.8% | +2,482,130 (+/- 57,589) |
| 50% (5,029,945) | 61.6% | -43.4% | 93.5% | 99.2% | +3,057,503 (+/- 80,169) |
| 100% (10,059,890) | 98.5% | -38.4% | 98.8% | 99.8% | +136,908 (+/- 76,839) |

### Budget 10% of the natural month (1,005,989 a month)

| Rule | Profit added a month | Share of hindsight | Coupons a month | Budget used (mean, max) | Discount to people who would have bought anyway |
|---|---|---|---|---|---|
| no coupons | 0 | 0.0% (+/- 0.0) | 0 | 0%, 0% | 0 |
| cart recovery | -695,039 | -26.3% (+/- 1.0) | 275 | 100%, 101% | 915,405 |
| first come | 986,446 | 37.3% (+/- 1.0) | 407 | 98%, 103% | 505,842 |
| fixed price | 2,520,674 | 95.3% (+/- 0.7) | 1,250 | 95%, 98% | 508,951 |
| re-solved price | 2,560,360 | 96.8% (+/- 0.5) | 1,324 | 95%, 97% | 509,326 |
| hindsight | 2,645,960 | 100.0% (+/- 0.0) | 1,454 | 93%, 96% | 500,933 |
| true hindsight | 3,476,864 | 131.5% (+/- 1.2) | 1,418 | 100%, 100% | 499,702 |

### Budget 25% of the natural month (2,514,973 a month)

| Rule | Profit added a month | Share of hindsight | Coupons a month | Budget used (mean, max) | Discount to people who would have bought anyway |
|---|---|---|---|---|---|
| no coupons | 0 | 0.0% (+/- 0.0) | 0 | 0%, 0% | 0 |
| cart recovery | -1,762,913 | -35.5% (+/- 0.8) | 690 | 100%, 100% | 2,287,548 |
| first come | 2,480,468 | 49.9% (+/- 0.8) | 1,005 | 97%, 100% | 1,247,660 |
| fixed price | 4,442,897 | 89.2% (+/- 2.0) | 1,780 | 80%, 91% | 953,065 |
| re-solved price | 4,962,598 | 99.8% (+/- 0.2) | 1,903 | 95%, 96% | 1,094,853 |
| hindsight | 4,974,663 | 100.0% (+/- 0.0) | 1,902 | 95%, 97% | 1,090,536 |
| true hindsight | 6,579,137 | 132.3% (+/- 0.9) | 2,167 | 100%, 100% | 1,105,445 |

### Budget 50% of the natural month (5,029,945 a month)

| Rule | Profit added a month | Share of hindsight | Coupons a month | Budget used (mean, max) | Discount to people who would have bought anyway |
|---|---|---|---|---|---|
| no coupons | 0 | 0.0% (+/- 0.0) | 0 | 0%, 0% | 0 |
| cart recovery | -3,522,361 | -43.4% (+/- 1.1) | 1,371 | 100%, 100% | 4,575,450 |
| first come | 4,999,533 | 61.6% (+/- 0.6) | 2,011 | 97%, 99% | 2,485,734 |
| fixed price | 7,595,159 | 93.5% (+/- 2.3) | 2,554 | 86%, 95% | 1,909,561 |
| re-solved price | 8,057,036 | 99.2% (+/- 0.2) | 2,674 | 95%, 97% | 2,141,224 |
| hindsight | 8,118,410 | 100.0% (+/- 0.0) | 2,673 | 96%, 97% | 2,133,696 |
| true hindsight | 9,956,138 | 122.6% (+/- 0.5) | 2,815 | 100%, 100% | 2,142,816 |

### Budget 100% of the natural month (10,059,890 a month)

| Rule | Profit added a month | Share of hindsight | Coupons a month | Budget used (mean, max) | Discount to people who would have bought anyway |
|---|---|---|---|---|---|
| no coupons | 0 | 0.0% (+/- 0.0) | 0 | 0%, 0% | 0 |
| cart recovery | -3,850,361 | -38.4% (+/- 1.2) | 1,502 | 55%, 58% | 5,004,411 |
| first come | 9,873,378 | 98.5% (+/- 0.8) | 3,978 | 96%, 98% | 4,920,412 |
| fixed price | 9,906,693 | 98.8% (+/- 0.5) | 3,856 | 92%, 98% | 4,636,540 |
| re-solved price | 10,010,286 | 99.8% (+/- 0.1) | 3,955 | 95%, 97% | 4,815,982 |
| hindsight | 10,025,520 | 100.0% (+/- 0.0) | 3,983 | 96%, 98% | 4,895,904 |
| true hindsight | 12,227,123 | 122.0% (+/- 0.4) | 3,928 | 98%, 100% | 4,813,124 |

## b. The coupon guard

Coupons a counsellor might give by hand. The guard stops a coupon when its predicted extra profit (chance to buy with it x fee x (1 - discount) - chance without it x fee) is not positive. 'Precision': of the stopped coupons, the share that truly lose money; 'recall': of the coupons that truly lose money, the share stopped. Profit is per 100 coupons the counsellor wanted to give.

| Coupons for | Discount | Stopped | Truly lose money | Precision | Recall | Profit, all given | Profit, guard on | Saved | Discount to buyers anyway avoided |
|---|---|---|---|---|---|---|---|---|---|
| the warmest leads (top 10% by score) | 10% | 100% | 98% | 98% | 100% | -383,894 | 0 | 383,894 | 438,065 |
| the warmest leads (top 10% by score) | 20% | 100% | 100% | 100% | 100% | -801,491 | 0 | 801,491 | 876,130 |
| every left cart | 10% | 59% | 61% | 96% | 93% | -48,034 | 158,673 | 206,707 | 242,870 |
| every left cart | 20% | 67% | 67% | 95% | 95% | -258,336 | 178,177 | 436,513 | 538,142 |
| anyone (10% at random) | 10% | 36% | 35% | 74% | 76% | 98,852 | 156,172 | 57,320 | 91,878 |
| anyone (10% at random) | 20% | 45% | 42% | 80% | 86% | 67,230 | 211,164 | 143,934 | 227,424 |

## c. The pipeline in rupees

200 snapshots of 1,200 open leads. 'Comes in anyway' is the sum of each lead's chance to buy with no contact x fee; 'the team can add' is the sum of the best step's extra profit.

| | Predicted | True | Predicted / true |
|---|---|---|---|
| Comes in anyway | 18,985,429 | 18,958,782 | 1.001 |
| The team can add (best step for every lead) | 4,743,635 | 4,666,279 | 1.017 |

By fifths of the lead score:

| Lead score | Anyway, predicted / true | Can add per lead, predicted | Can add per lead, true |
|---|---|---|---|
| 0.004 to 0.069 | 0.925 | 1,787 | 1,635 |
| 0.069 to 0.154 | 1.018 | 3,444 | 3,296 |
| 0.154 to 0.320 | 0.998 | 4,948 | 4,923 |
| 0.320 to 0.650 | 0.998 | 6,319 | 6,244 |
| 0.650 to 1.000 | 1.007 | 3,239 | 3,329 |

When the team has time for only some of the open leads, each worked with the model's best step: the true profit added when they are worked in the usual order (highest score first), in money order (most to add first, the pipeline's default), at random, and with perfect knowledge (the ceiling).

| Leads worked | Highest score first | Most to add first (ours) | Random | Perfect knowledge | Ours against highest score |
|---|---|---|---|---|---|
| 60 (5%) | 40,316 (4%) | 874,900 (89%) | 229,510 (24%) | 978,420 | +834,583 (+/- 7,418) |
| 120 (10%) | 193,262 (12%) | 1,415,563 (89%) | 462,883 (29%) | 1,588,622 | +1,222,300 (+/- 9,896) |
| 240 (20%) | 797,639 (32%) | 2,271,329 (91%) | 930,284 (37%) | 2,501,642 | +1,473,691 (+/- 12,903) |
| 480 (40%) | 2,299,796 (62%) | 3,451,426 (93%) | 1,863,147 (50%) | 3,710,557 | +1,151,630 (+/- 12,094) |

'No discount needed' (more likely than not to buy anyway, and no coupon would add profit by the model: 20.4% of the leads who can get email): for 91% of them even the better coupon truly loses money (on average 2,859 a lead). Being likely to buy anyway is not enough on its own: for all such leads (28.2%) the share is 73%; for every other lead it is 15%.

## d. The owner's planner

What one more counsellor (8 more call slots a day on top of 8) would add in a month: the planner's estimate (from the last 7 days of predicted call advantages, production app.services.planner.slots_value) against the true extra profit of the same days run with the extra slots (re-solved slot price, E7). The planner replays last week's decisions with the CRM's own rule; 'ranked' is the simpler estimate it does not use (each day's calls ranked 9 to 16 by predicted advantage), which misses that with more slots the rule holds back fewer calls for later in the day. Demand is the number of call-worthy decisions a day as a multiple of today's slots.

| Demand | Today's slots: estimate | true | estimate / true | One more counsellor: estimate | true | estimate / true | ranked / true |
|---|---|---|---|---|---|---|---|
| 1x | 547,794 | 542,470 | 1.01 (+/- 0.04) | 57,401 | 61,509 | 0.89 (+/- 0.13) | 0.31 |
| 2x | 919,464 | 899,190 | 1.02 (+/- 0.03) | 193,546 | 204,809 | 0.95 (+/- 0.05) | 0.81 |
| 4x | 1,401,105 | 1,389,185 | 1.01 (+/- 0.03) | 570,275 | 558,237 | 1.02 (+/- 0.04) | 1.02 |
| 8x | 1,883,119 | 1,818,069 | 1.04 (+/- 0.02) | 999,139 | 968,427 | 1.03 (+/- 0.02) | 1.05 |

What 20% more discount budget would add in a month: the planner's estimate (from the week before the month, production BudgetPricer.month_value) against the true difference between the month run with the larger budget and with the budget as it is.

| Budget | Extra money | Estimate | True |
|---|---|---|---|
| 10% (1,005,989) | 201,198 | 401,034 (+/- 5,223) | 453,306 (+/- 12,751) |
| 25% (2,514,973) | 502,995 | 773,994 (+/- 11,867) | 686,451 (+/- 13,931) |
| 50% (5,029,945) | 1,005,989 | 992,461 (+/- 35,388) | 864,239 (+/- 30,225) |
| 100% (10,059,890) | 2,011,978 | 46,439 (+/- 49,274) | 17,217 (+/- 13,163) |
