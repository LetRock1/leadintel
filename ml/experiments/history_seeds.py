"""
history_seeds.py: re-creates ml/results/history_runs.md from scratch: six 180-day simulated histories with
different random seeds, each in its own temporary copy of the project (your own database is never touched),
then history_check.py over all six.

Run from the project folder with the backend's Python (servers may be running):
    backend/.venv/Scripts/python ml/experiments/history_seeds.py       (Windows)
    backend/.venv/bin/python ml/experiments/history_seeds.py           (macOS, Linux)
About 10 minutes per history. Optional: --seeds 2026 11 12   --keep (keep the copies)   --jobs 2
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _project as PJ  # noqa: E402


def one(work, seed):
    d = PJ.copy_project(os.path.join(work, f"seed{seed}"))
    t0 = time.time()
    print(f"history with seed {seed} ...", flush=True)
    PJ.run_history(d, 2000, 180, seed)
    print(f"  seed {seed} done ({(time.time() - t0) / 60:.1f} min)", flush=True)
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[2026, 11, 12, 13, 14, 15])
    ap.add_argument("--jobs", type=int, default=2, help="histories made at the same time")
    ap.add_argument("--keep", action="store_true", help="keep the temporary project copies")
    args = ap.parse_args()
    PJ.require_starting_models()
    work = tempfile.mkdtemp(prefix="xedu_histories_")
    try:
        with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as ex:
            folders = list(ex.map(lambda s: one(work, s), args.seeds))
        env = dict(os.environ, PYTHONUTF8="1", OMP_NUM_THREADS="1")
        subprocess.run(
            [sys.executable, os.path.join(HERE, "history_check.py"), *folders], cwd=PJ.ROOT, env=env, check=True
        )
    finally:
        if args.keep:
            print(f"Copies kept in {work}")
        else:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
