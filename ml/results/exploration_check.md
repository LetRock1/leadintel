# E8b What the random learning steps cost, and what next-best-action loses without them

Closed loop for 12 months, 1,000 new leads a month, in the worlds of E2b. The CRM starts from the model it ships with (trained on the documented assumptions) and retrains monthly exactly as the learning loop does (documented prior plus logged decisions, swap only on a clear off-policy gain). Same leads, true effects and random numbers for every share of random steps. Extra profit per lead over doing nothing, with the world's true effects (higher is better), as the mean of 5 independent runs per world (new leads and random numbers in each); swaps are the mean number of model replacements per run. Made by `ml/experiments/exploration_check.py`.

| World | Oracle | 0% random: what it did | 5% random: what it did | 15% random: what it did | 0%: learned policy, last month | 5%: learned policy, last month | 15%: learned policy, last month | Swaps (0% / 5% / 15%) |
|---|---|---|---|---|---|---|---|---|
| documented | ₹4,212.0 | ₹3,935.1 | ₹3,689.6 | ₹3,490.8 | ₹3,917.8 | ₹3,763.3 | ₹3,857.7 | 3.6 / 0.6 / 0.0 |
| null | ₹0.0 | ₹-419.7 | ₹-538.7 | ₹-573.3 | ₹-402.4 | ₹-513.3 | ₹-523.2 | 3.0 / 0.2 / 0.6 |
| reversed | ₹1,888.1 | ₹-1,507.4 | ₹-1,549.1 | ₹-1,385.3 | ₹-1,322.6 | ₹-1,393.9 | ₹-1,124.0 | 0.6 / 0.2 / 0.4 |
| hidden | ₹2,843.2 | ₹837.0 | ₹758.2 | ₹666.9 | ₹849.0 | ₹808.4 | ₹808.4 | 2.6 / 0.0 / 0.0 |
| random 01 (hidden 0.52) | ₹3,379.8 | ₹783.3 | ₹466.2 | ₹237.8 | ₹1,262.4 | ₹604.7 | ₹482.3 | 3.4 / 0.4 / 0.4 |
| random 02 (hidden 0.71) | ₹4,306.7 | ₹2,376.7 | ₹2,070.4 | ₹1,886.0 | ₹2,696.9 | ₹2,257.2 | ₹2,142.0 | 2.6 / 0.2 / 0.2 |
| random 03 (hidden 0.64) | ₹6,928.8 | ₹3,448.6 | ₹408.7 | ₹1,937.7 | ₹6,222.1 | ₹1,300.8 | ₹5,696.0 | 6.2 / 0.8 / 1.2 |
| random 04 (hidden 0.69) | ₹2,558.2 | ₹-282.2 | ₹-971.0 | ₹-912.8 | ₹-38.9 | ₹-834.5 | ₹315.7 | 2.0 / 0.8 / 1.0 |
| random 05 (hidden 0.84) | ₹5,705.9 | ₹1,939.6 | ₹1,238.2 | ₹1,170.9 | ₹2,323.4 | ₹1,385.3 | ₹1,575.7 | 3.8 / 0.2 / 0.4 |
| random 06 (hidden 0.21) | ₹5,796.1 | ₹3,511.0 | ₹3,327.7 | ₹3,225.9 | ₹3,904.8 | ₹3,547.3 | ₹3,772.3 | 2.8 / 0.8 / 0.2 |
| random 07 (hidden 0.14) | ₹3,392.5 | ₹234.0 | ₹-108.8 | ₹-349.2 | ₹835.3 | ₹745.3 | ₹616.5 | 3.0 / 1.0 / 0.8 |
| random 08 (hidden 0.82) | ₹4,256.4 | ₹1,677.7 | ₹889.9 | ₹705.4 | ₹2,166.3 | ₹1,050.2 | ₹793.0 | 4.8 / 0.2 / 0.0 |
| random 09 (hidden 0.58) | ₹7,242.1 | ₹5,076.5 | ₹2,450.4 | ₹3,122.6 | ₹5,498.2 | ₹3,049.3 | ₹4,886.3 | 3.4 / 0.4 / 0.8 |
| random 10 (hidden 0.52) | ₹5,401.6 | ₹787.4 | ₹1,004.5 | ₹1,233.6 | ₹1,873.1 | ₹2,424.3 | ₹3,344.3 | 0.8 / 0.8 / 1.2 |

**5% against 15% random steps.** What it did: more profit in **9 of 14** worlds (two-sided sign test p 0.424) and in 45 of 70 single runs; mean difference ₹-94.3 per lead (95% interval ₹-366.9 to ₹+106.8; ₹-94,337 per 1,000 leads), median ₹+79.3, worst world ₹-1,529.0, best ₹+240.4. What it had learned by the last month (its greedy policy): better in 5, worse in 8 and the same in 1 of 14 worlds, mean ₹-603.5 per lead (95% interval ₹-1,312.8 to ₹-90.7).

**0% against 15% random steps.** What it did: more profit in **12 of 14** worlds (two-sided sign test p 0.013) and in 61 of 70 single runs; mean difference ₹+567.2 per lead (95% interval ₹+269.5 to ₹+890.4; ₹+567,179 per 1,000 leads), median ₹+518.1, worst world ₹-446.2, best ₹+1,953.8. What it had learned by the last month (its greedy policy): better in 11, worse in 3 and the same in 0 of 14 worlds, mean ₹+224.5 per lead (95% interval ₹-133.4 to ₹+535.7).

**0% against 5% random steps.** What it did: more profit in **13 of 14** worlds (two-sided sign test p 0.002) and in 59 of 70 single runs; mean difference ₹+661.5 per lead (95% interval ₹+239.7 to ₹+1,201.6; ₹+661,517 per 1,000 leads), median ₹+311.7, worst world ₹-217.1, best ₹+3,039.9. What it had learned by the last month (its greedy policy): better in 13, worse in 1 and the same in 0 of 14 worlds, mean ₹+827.9 per lead (95% interval ₹+255.2 to ₹+1,607.6).
