# What-if paths: out-of-time check

6 histories: in each, the paths are learned from the decisions before a cut-off (two thirds into the history) and tested on the later decisions, weighted by 1/probability.

| History | Learned from / tested on | same mix for everyone | mix per stage (ignores the step) | what-if paths (stage and step) |
|---|---|---|---|---|
| seed2026 | 2,762 / 2,051 | 0.5576 | 0.5449 | 0.5465 |
| seed11 | 2,867 / 1,935 | 0.5630 | 0.5415 | 0.5289 |
| seed12 | 2,688 / 2,086 | 0.5638 | 0.5402 | 0.5467 |
| seed13 | 2,708 / 2,073 | 0.5877 | 0.5792 | 0.5719 |
| seed14 | 2,845 / 2,161 | 0.5476 | 0.5264 | 0.5245 |
| seed15 | 2,612 / 2,094 | 0.5470 | 0.5361 | 0.5260 |
| Mean | | 0.5611 | 0.5447 | 0.5407 |

Brier score of the reaction in the next 3 days (lower is better). The what-if paths beat the mix per stage in 4 of 6 histories (mean difference -0.0040).

| Team step | Later decisions | Predicted buying within 14 days | Actual |
|---|---|---|---|
| Counsellor phone call | 2,066 | 28.3% | 34.3% |
| Send email with 10% coupon | 1,524 | 34.6% | 37.7% |
| Send email with 20% coupon | 3,517 | 37.1% | 38.3% |
| Send an information email | 2,588 | 33.8% | 33.3% |
| Do nothing for now | 1,995 | 28.8% | 32.7% |
| WhatsApp message | 710 | 37.9% | 42.3% |
| All steps | 12,400 | 33.1% | 35.6% |
