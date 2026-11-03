"""
anchored_histories.py: the simulated histories behind E8 (the anchored update inside the product).

Each history is the CRM running by itself for 180 days on 2,000 simulated learners (python -m app.cli history create),
in its own temporary copy of the project (your own database is never touched), with one setting changed:

    control   the share of learners the CRM never contacts (crm_settings.json global_control.share): 5% or 0%
    explore   the share of next-best-action decisions taken at random (exploration_rate): 15%, 5% or 0%

On top of that, every history keeps an EVALUATION GROUP of 10% of learners whom the CRM never contacts either. The
analysis (anchored_check.py) never trains on them: their outcomes are the truth every retraining method is judged
on. They are the first 10% of the same hash the CRM uses for its control group (app.core.rules.in_global_control),
so the settings file says global_control.share = control + 10%, and the analysis splits the two by the hash.

Usage (from the project folder, with the backend's Python, after the first start trained the starting models):
    python ml/experiments/anchored_histories.py --out WORK_FOLDER [--seeds 2026 11 12 13] [--jobs 2]
Writes WORK_FOLDER/<setting>_s<seed>/ (a project copy with its database), about 10 minutes per history.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _project as PJ  # noqa: E402

EVAL_SHARE = 0.10
SETTINGS = {  # name: (control share, exploration rate)
    "c5_e15": (0.05, 0.15),  # v7.0's defaults
    "c5_e05": (0.05, 0.05),
    "c5_e00": (0.05, 0.00),
    "c0_e15": (0.00, 0.15),
    "c0_e00": (0.00, 0.00),  # nothing left to chance except the evaluation group
}


def make(work, name, seed):
    control, explore = SETTINGS[name]
    dest = os.path.join(work, f"{name}_s{seed}")
    if os.path.exists(os.path.join(dest, "done.json")):
        return dest
    if not os.path.exists(dest):
        PJ.copy_project(dest)
    path = os.path.join(dest, "crm_settings.json")
    with open(path, encoding="utf-8") as f:
        s = json.load(f)
    s["global_control"]["share"] = round(control + EVAL_SHARE, 4)
    s["exploration_rate"] = explore
    with open(path, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2, ensure_ascii=False)
    env = dict(PJ.env_for(dest), NBA_EXPLORE_RATE=str(explore))
    t0 = time.time()
    print(f"{name} seed {seed}: making the history ...", flush=True)
    subprocess.run(
        [sys.executable, "-m", "app.cli", "history", "create", "--n", "2000", "--days", "180", "--seed", str(seed)],
        cwd=os.path.join(dest, "backend"),
        env=env,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    with open(os.path.join(dest, "done.json"), "w", encoding="utf-8") as f:
        json.dump(
            {
                "setting": name,
                "seed": seed,
                "control": control,
                "explore": explore,
                "eval_share": EVAL_SHARE,
                "minutes": round((time.time() - t0) / 60, 1),
            },
            f,
        )
    print(f"  {name} seed {seed} done ({(time.time() - t0) / 60:.1f} min)", flush=True)
    return dest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="folder for the history copies (kept for the analysis)")
    ap.add_argument("--seeds", type=int, nargs="+", default=[2026, 11, 12, 13])
    ap.add_argument("--settings", nargs="+", default=list(SETTINGS))
    ap.add_argument("--jobs", type=int, default=2)
    args = ap.parse_args()
    PJ.require_starting_models()
    os.makedirs(args.out, exist_ok=True)
    jobs = [(n, s) for s in args.seeds for n in args.settings]
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as ex:
        list(ex.map(lambda j: make(args.out, *j), jobs))


if __name__ == "__main__":
    main()
