# E7: capacity-aware next-best-action

10 simulated runs of 60 days (the first 7 build the price), 20 calls a day. Value is the true expected extra profit per day (INR) against doing nothing; 'share' is the part of the value of the call slots that each rule captures, between using no calls (0%) and the best allocation with hindsight (100%), with a 95% interval across runs.

Rules compared:

- **no calls**: calls are never used (what the other steps earn on their own)
- **first come**: the model's best step for each learner, a call while slots are left (the usual daily cap)
- **fixed price**: a call only when it adds more than one price, the same all day (from the last 7 days)
- **re-solved price**: ours: the price is worked out again at every decision from the slots left and the share of the day's call-worthy decisions still to come
- **hindsight**: the day's largest predicted call advantages (needs the day's future: the best any online rule could do with the same predictions)
- **true hindsight**: the same with the true advantages (the ceiling, with perfect prediction too)

## Summary

| Scenario | First come | Fixed price | Re-solved price (ours) | Ours against first come, INR per day |
|---|---|---|---|---|
| demand 0.5x capacity | 100.0% | 100.0% | 100.0% | +0 (+/- 0) |
| demand 1x capacity | 93.7% | 93.8% | 97.0% | +1,915 (+/- 415) |
| demand 2x capacity | 70.3% | 89.8% | 95.5% | +23,258 (+/- 1,231) |
| demand 4x capacity | 52.3% | 89.3% | 96.2% | +55,286 (+/- 2,694) |
| demand 8x capacity | 40.7% | 88.7% | 96.8% | +88,039 (+/- 2,605) |
| demand 2x capacity, doubling half-way | 58.1% | 88.4% | 94.8% | +40,164 (+/- 1,674) |
| demand 4x capacity, doubling half-way | 45.5% | 88.5% | 96.5% | +72,984 (+/- 4,481) |

When demand for calls is 2x to 8x the capacity, first come, first served captures 41% to 70% of the value of the call slots; the re-solved slot price captures 96% to 97%, that is +23,258 to +88,039 INR a day with 20 calls a day. With spare capacity (0.5x) every rule uses the same calls, so pricing costs nothing when it is not needed.

## demand 0.5x capacity

| Rule | Profit per day | Calls per day | Share of hindsight | Against first come, per day |
|---|---|---|---|---|
| no calls | 61,871 | 0.0 | 0.0% (+/- 0.0) | -29,787 (+/- 857) |
| first come | 91,659 | 9.2 | 100.0% (+/- 0.1) | +0 (+/- 0) |
| fixed price | 91,659 | 9.2 | 100.0% (+/- 0.1) | +0 (+/- 0) |
| re-solved price | 91,659 | 9.2 | 100.0% (+/- 0.1) | +0 (+/- 0) |
| hindsight | 91,667 | 9.2 | 100.0% (+/- 0.0) | +9 (+/- 17) |
| true hindsight | 96,024 | 8.8 | 114.7% (+/- 2.2) | +4,366 (+/- 642) |

## demand 1x capacity

| Rule | Profit per day | Calls per day | Share of hindsight | Against first come, per day |
|---|---|---|---|---|
| no calls | 126,486 | 0.0 | 0.0% (+/- 0.0) | -54,887 (+/- 2,154) |
| first come | 181,374 | 17.0 | 93.7% (+/- 0.9) | +0 (+/- 0) |
| fixed price | 181,436 | 16.9 | 93.8% (+/- 0.9) | +62 (+/- 60) |
| re-solved price | 183,289 | 16.9 | 97.0% (+/- 1.1) | +1,915 (+/- 415) |
| hindsight | 185,068 | 17.0 | 100.0% (+/- 0.0) | +3,694 (+/- 574) |
| true hindsight | 195,167 | 16.5 | 117.3% (+/- 1.2) | +13,794 (+/- 456) |

## demand 2x capacity

| Rule | Profit per day | Calls per day | Share of hindsight | Against first come, per day |
|---|---|---|---|---|
| no calls | 247,781 | 0.0 | 0.0% (+/- 0.0) | -64,740 (+/- 1,339) |
| first come | 312,520 | 19.9 | 70.3% (+/- 1.2) | +0 (+/- 0) |
| fixed price | 330,544 | 17.6 | 89.8% (+/- 1.2) | +18,024 (+/- 1,775) |
| re-solved price | 335,779 | 19.2 | 95.5% (+/- 0.9) | +23,258 (+/- 1,231) |
| hindsight | 339,960 | 19.9 | 100.0% (+/- 0.0) | +27,440 (+/- 1,406) |
| true hindsight | 363,007 | 19.9 | 125.1% (+/- 1.6) | +50,487 (+/- 1,545) |

## demand 4x capacity

| Rule | Profit per day | Calls per day | Share of hindsight | Against first come, per day |
|---|---|---|---|---|
| no calls | 496,048 | 0.0 | 0.0% (+/- 0.0) | -65,734 (+/- 939) |
| first come | 561,782 | 20.0 | 52.3% (+/- 1.0) | +0 (+/- 0) |
| fixed price | 608,354 | 17.7 | 89.3% (+/- 0.6) | +46,572 (+/- 2,618) |
| re-solved price | 617,068 | 19.7 | 96.2% (+/- 0.8) | +55,286 (+/- 2,694) |
| hindsight | 621,857 | 20.0 | 100.0% (+/- 0.0) | +60,075 (+/- 2,520) |
| true hindsight | 663,054 | 20.0 | 132.8% (+/- 1.6) | +101,272 (+/- 2,860) |

## demand 8x capacity

| Rule | Profit per day | Calls per day | Share of hindsight | Against first come, per day |
|---|---|---|---|---|
| no calls | 991,546 | 0.0 | 0.0% (+/- 0.0) | -63,818 (+/- 889) |
| first come | 1,055,364 | 20.0 | 40.7% (+/- 0.8) | +0 (+/- 0) |
| fixed price | 1,130,727 | 17.5 | 88.7% (+/- 0.9) | +75,363 (+/- 2,423) |
| re-solved price | 1,143,403 | 19.9 | 96.8% (+/- 0.7) | +88,039 (+/- 2,605) |
| hindsight | 1,148,433 | 20.0 | 100.0% (+/- 0.0) | +93,069 (+/- 2,130) |
| true hindsight | 1,209,718 | 20.0 | 139.1% (+/- 1.3) | +154,354 (+/- 2,471) |

## demand 2x capacity, doubling half-way

| Rule | Profit per day | Calls per day | Share of hindsight | Against first come, per day |
|---|---|---|---|---|
| no calls | 385,328 | 0.0 | 0.0% (+/- 0.0) | -63,676 (+/- 2,023) |
| first come | 449,004 | 20.0 | 58.1% (+/- 1.1) | +0 (+/- 0) |
| fixed price | 482,165 | 17.7 | 88.4% (+/- 1.0) | +33,161 (+/- 1,190) |
| re-solved price | 489,168 | 19.5 | 94.8% (+/- 1.0) | +40,164 (+/- 1,674) |
| hindsight | 494,876 | 20.0 | 100.0% (+/- 0.0) | +45,872 (+/- 1,273) |
| true hindsight | 527,698 | 19.9 | 130.0% (+/- 1.6) | +78,694 (+/- 1,747) |

## demand 4x capacity, doubling half-way

| Rule | Profit per day | Calls per day | Share of hindsight | Against first come, per day |
|---|---|---|---|---|
| no calls | 775,987 | 0.0 | 0.0% (+/- 0.0) | -64,944 (+/- 828) |
| first come | 840,931 | 20.0 | 45.5% (+/- 1.4) | +0 (+/- 0) |
| fixed price | 902,504 | 17.9 | 88.5% (+/- 1.1) | +61,573 (+/- 4,496) |
| re-solved price | 913,915 | 19.8 | 96.5% (+/- 0.9) | +72,984 (+/- 4,481) |
| hindsight | 918,901 | 20.0 | 100.0% (+/- 0.0) | +77,969 (+/- 4,244) |
| true hindsight | 972,981 | 20.0 | 138.0% (+/- 2.3) | +132,050 (+/- 3,997) |
