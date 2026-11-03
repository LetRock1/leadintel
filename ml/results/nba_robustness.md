# Next-best-action robustness: worlds where our assumptions are wrong

Share of the oracle's net incremental profit captured on 30,000 fresh leads (each world's true response). Models trained on 60,000 randomized decisions. *Best fixed* = the best of the six fixed policies in that world, chosen in hindsight. *Pick* = the family the closed loop's champion/challenger rule selected using only logged decisions (off-policy estimate on a 25% hold-out).

| World | Hidden share | Ours (interpretable) | Flexible (GBM) | Champion/challenger pick | Best fixed policy | Best fixed | Oracle ₹/1000 |
|---|---|---|---|---|---|---|---|
| documented | — | 91.4% | 85.5% | 91.4% (interpretable) | Email everyone (no discount) | 35.7% | 3,898,866 |
| null | — | ₹-18,671 | ₹-5,717 | ₹-18,671 | No contact | ₹0 | 0 |
| reversed | — | 70.3% | 54.7% | 70.3% (interpretable) | Email everyone (no discount) | 12.9% | 1,617,905 |
| hidden | — | 36.7% | 59.5% | 59.5% (flexible) | Email everyone (no discount) | 29.4% | 2,816,102 |
| random_01 | 0.52 | 63.9% | 60.7% | 60.7% (flexible) | No contact | 0.0% | 3,158,043 |
| random_02 | 0.71 | 72.0% | 79.1% | 79.1% (flexible) | 20% coupon to everyone | 13.8% | 4,020,587 |
| random_03 | 0.64 | 97.6% | 97.4% | 97.6% (interpretable) | Email everyone (no discount) | 97.0% | 6,896,027 |
| random_04 | 0.69 | 55.6% | 71.7% | 71.7% (flexible) | Email everyone (no discount) | 36.0% | 2,554,722 |
| random_05 | 0.84 | 73.3% | 90.4% | 90.4% (flexible) | Email everyone (no discount) | 64.5% | 5,121,855 |
| random_06 | 0.21 | 89.2% | 83.6% | 89.2% (interpretable) | Email everyone (no discount) | 54.1% | 4,636,466 |
| random_07 | 0.14 | 94.1% | 88.5% | 94.1% (interpretable) | Lead-score targeting (score-based CRM) | 0.4% | 3,386,415 |
| random_08 | 0.82 | 71.2% | 77.4% | 77.4% (flexible) | Lead-score targeting (score-based CRM) | 26.5% | 4,051,624 |
| random_09 | 0.58 | 88.9% | 92.0% | 88.9% (interpretable) | Lead-score targeting (score-based CRM) | 53.7% | 7,161,810 |
| random_10 | 0.52 | 87.1% | 86.5% | 86.5% (flexible) | Lead-score targeting (score-based CRM) | 24.5% | 5,416,027 |
| random_11 | 0.13 | 98.5% | 96.6% | 98.5% (interpretable) | Email everyone (no discount) | 92.4% | 6,468,170 |
| random_12 | 0.50 | 70.9% | 62.9% | 70.9% (interpretable) | No contact | 0.0% | 2,728,146 |
| random_13 | 0.09 | 87.1% | 79.2% | 87.1% (interpretable) | No contact | 0.0% | 2,646,209 |
| random_14 | 0.44 | 91.2% | 87.6% | 91.2% (interpretable) | Email everyone (no discount) | 79.9% | 5,258,619 |
| random_15 | 0.13 | 94.1% | 89.7% | 89.7% (flexible) | 20% coupon to everyone | 28.3% | 4,223,759 |
| random_16 | 0.48 | 76.4% | 79.5% | 76.4% (interpretable) | Lead-score targeting (score-based CRM) | 25.0% | 3,683,361 |
| random_17 | 0.11 | 90.8% | 87.1% | 87.1% (flexible) | No contact | 0.0% | 2,485,337 |
| random_18 | 0.60 | 72.1% | 61.0% | 72.1% (interpretable) | Email everyone (no discount) | 37.5% | 1,837,596 |
| random_19 | 0.44 | 79.2% | 79.1% | 79.2% (interpretable) | 20% coupon to everyone | 33.2% | 3,362,650 |
| random_20 | 0.67 | 60.0% | 61.2% | 60.0% (interpretable) | No contact | 0.0% | 2,599,503 |

**20 random worlds.** Beat the best fixed policy (chosen in hindsight): ours 20/20, flexible 20/20, champion/challenger 20/20. Median share of oracle profit: ours 83.1% (worst 55.6%), flexible 81.5% (worst 60.7%), champion/challenger 86.8% (worst 60.0%), best fixed 27.4%. The interpretable model beat the flexible one in 9/10 worlds with hidden share < 0.5 and 4/10 with hidden share ≥ 0.5 (correlation of hidden share with the interpretable model's advantage: -0.70). The champion/challenger rule picked the better family in 13/20.

## Named worlds — every policy (net incremental profit per 1,000 leads, ₹)

| Policy | documented | null | reversed | hidden |
|---|---|---|---|---|
| No contact | 0 | 0 | 0 | 0 |
| Email everyone (no discount) | 1,393,515 | -1,845 | 208,413 | 828,961 |
| 20% coupon to everyone | 553,592 | -2,970,517 | -2,117,084 | -1,548,872 |
| Random action | 1,037,883 | -872,290 | -471,120 | -17,305 |
| Tier playbook (rule-based workflow) | 943,138 | -602,083 | -187,524 | 186,776 |
| Lead-score targeting (score-based CRM) | 1,089,122 | -743,815 | -331,426 | 115,380 |
| Oracle (knows true effects) | 3,898,866 | 0 | 1,617,905 | 2,816,102 |
| Next-best-action (ours, interpretable) | 3,563,643 | -18,671 | 1,137,434 | 1,033,734 |
| Next-best-action (flexible GBM) | 3,332,422 | -5,717 | 885,590 | 1,676,363 |
| Next-best-action (champion/challenger pick) | 3,563,643 | -18,671 | 1,137,434 | 1,676,363 |

Null world: ours contacted 532 of every 1,000 leads (2 coupons, 100 calls).

## Learning curve (net profit per 1,000 leads vs number of randomized decisions)

| World | Decisions | Ours (interpretable) | Flexible (GBM) | Best fixed | Oracle |
|---|---|---|---|---|---|
| documented | 1,000 | 2,790,399 | 1,305,302 | 1,393,515 | 3,898,866 |
| documented | 3,000 | 3,190,977 | 1,683,828 | 1,393,515 | 3,898,866 |
| documented | 10,000 | 3,435,311 | 2,816,454 | 1,393,515 | 3,898,866 |
| documented | 30,000 | 3,554,422 | 3,199,734 | 1,393,515 | 3,898,866 |
| documented | 60,000 | 3,563,643 | 3,332,422 | 1,393,515 | 3,898,866 |
| hidden | 1,000 | 601,064 | 121,954 | 828,961 | 2,816,102 |
| hidden | 3,000 | 722,751 | 981,296 | 828,961 | 2,816,102 |
| hidden | 10,000 | 932,781 | 1,230,246 | 828,961 | 2,816,102 |
| hidden | 30,000 | 1,011,303 | 1,580,593 | 828,961 | 2,816,102 |
| hidden | 60,000 | 1,033,734 | 1,676,363 | 828,961 | 2,816,102 |
