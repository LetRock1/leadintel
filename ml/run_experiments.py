"""
Re-runs every experiment behind the paper's numbers and writes ml/results/*.md and *.json (fixed seeds).

Run from the project folder with the backend's Python, after the first start (it trains the starting models):
    backend/.venv/Scripts/python ml/run_experiments.py          Windows    (about 4 hours; "quick" under an hour)
    backend/.venv/bin/python ml/run_experiments.py              macOS, Linux
    ... ml/run_experiments.py quick                             skips the slow robustness and history studies
    ... ml/run_experiments.py E7                                one experiment (E1, E1b, E2, E2b, E3, E4, E5, E6, E7, E8, E8b, E9)

  E1   model_benchmark.py      the lead-scoring method on REAL data: boosting vs logistic, random forest, neural
                               networks on the 9,240 real X Education leads, no leaked columns
  E1b  published_benchmark.py  against four public solutions re-run exactly (same rows, same inputs) and published
                               papers on the same file; DeLong and McNemar tests, 30 new splits
  E2   hillstrom_uplift.py     next-best-action on a real randomized email experiment (64,000 customers)
  E2b  nba_robustness.py       next-best-action when the assumptions about the world are wrong (simulation)
  E3   learning_loop.py        does naive retraining fool itself, and does ours avoid it? (real data)
  E4   ab_engine_check.py      are the A/B statistics trustworthy? (simulated tests with known truth)
  E5   paths_check.py          do the what-if paths predict what learners do next? (on the CRM's own history)
  E6   lead_age_check.py       learned lead aging against hand-set decay rules (simulated histories)
  E7   capacity_check.py       capacity-aware next-best-action: a priced call slot against first come, first served
  E8   anchored_check.py       each step's effect from the CRM's own experiment (v7.1) inside the product: the ways
                               to retrain the lead score, judged on learners nobody contacted or trained on, across
                               control-group and random-step settings (11 simulated histories, about 3 hours)
  E8b  exploration_check.py    what the random learning steps cost, and what next-best-action loses without them
                               (closed loop, 12 months, 14 worlds of E2b, 5 runs each, about 45 minutes)
  E9   money_check.py          the money features against known truth: a priced monthly discount budget against
                               first come first served and the cart-recovery rule, the coupon guard, the pipeline
                               in rupees (money order against score order), and the planner's estimates

The next-best-action policy comparison (profit per 1,000 leads) is written when the models are trained
(python -m app.cli train uplift). The six-history report (ml/results/history_runs.md) is made by
ml/experiments/history_seeds.py (about an hour).
"""

import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
EXP = os.path.join(HERE, "experiments")
STEPS = [
    ("E1", "lead scoring on real data", "model_benchmark.py", False),
    ("E1b", "against published solutions", "published_benchmark.py", False),
    ("E2", "next-best-action on real data", "hillstrom_uplift.py", False),
    ("E2b", "next-best-action robustness", "nba_robustness.py", True),
    ("E3", "learning loop on real data", "learning_loop.py", False),
    ("E4", "A/B engine", "ab_engine_check.py", False),
    ("E5", "what-if paths", "paths_check.py", False),
    ("E6", "learned lead aging", "lead_age_check.py", True),
    ("E7", "capacity-aware next-best-action", "capacity_check.py", False),
    ("E8", "the anchored update in the product", "anchored_check.py", True),
    ("E8b", "the cost of random learning steps", "exploration_check.py", True),
    ("E9", "the money features", "money_check.py", False),
]


def main() -> int:
    args = [a for a in sys.argv[1:]]
    quick = "quick" in args
    only = {a.upper() for a in args if a.lower() != "quick"}
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    failed = []
    for key, title, script, slow in STEPS:
        if (only and key.upper() not in only) or (quick and slow and not only):
            continue
        print(f"\n==== {key} {title} ({script}) ====", flush=True)
        t0 = time.time()
        code = subprocess.call([sys.executable, os.path.join(EXP, script)], cwd=os.path.dirname(HERE))
        print(f"---- {'done' if code == 0 else f'FAILED (exit {code})'} in {time.time() - t0:.0f} s", flush=True)
        if code:
            failed.append(key)
    print("\nResults: ml/results/*.md" + (f"\nFailed: {', '.join(failed)}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
