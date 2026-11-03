"""
Do the what-if paths predict what learners really do next? An out-of-time check on the CRM's history.

The what-if paths use, for each lifecycle stage and team step, the mix of reactions in the next
3 days (bought / cart-checkout-enquiry / came back / clicked / nothing) and the chance of buying
within 14 days, learned from earlier decisions (weighted by 1/probability of each decision).

Check: learn that model from the decisions made BEFORE a cut-off date (only outcomes known by then),
and predict the decisions made AFTER it.
  reaction mix   multi-class Brier score (lower is better) against two simpler guesses:
                 the same mix for everyone, and the mix per stage ignoring the step
  buying         predicted vs actual buying rate within 14 days, per step
All test decisions are weighted by 1/probability, so the score is about what each step does, not
about which leads the model happened to pick for it.

Run on one or more databases with history (the simulated starting history, the six histories of
ml/experiments/history_seeds.py --keep, or real data):
    python ml/experiments/paths_check.py [--db DB [DB ...]] [--cut 2026-08-15]
Writes ml/results/paths_check.md
"""

import argparse
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))


def brier(pred, obs, w, reactions):
    total = 0.0
    for r in reactions:
        total = total + (pred[r] - (obs == r).astype(float)) ** 2
    return float((w * total).sum() / w.sum())


def one(db_path, cut_text=None):
    """The check on one history: Brier scores of the three guesses, and per step predicted vs actual buying."""
    from app import db

    if db_path:
        db.DB_PATH = db_path
    from app.ml import journeys as J

    every = J.steps()
    if every.empty:
        raise SystemExit(f"No decisions in {db_path}.")
    t = pd.to_datetime(every["t"])
    cut = pd.Timestamp(cut_text) if cut_text else t.min() + (t.max() - t.min()) * 2 / 3
    model = J.model_from(J.steps(until=cut.strftime("%Y-%m-%d %H:%M:%S")))
    test = every[(t > cut) & every["matured"]].copy()
    if test.empty:
        raise SystemExit(f"No matured decisions after the cut-off in {db_path}.")
    R = J.REACTIONS
    test = test[test["stage"].isin(model["stages"])]
    w = test["w"].to_numpy(dtype=float)
    obs = test["reaction"].to_numpy()
    # the model: per stage and step
    cell = {
        r: np.array([model["stages"][s]["actions"][a]["reactions"][r] for s, a in zip(test["stage"], test["action"])])
        for r in R
    }
    buy_pred = np.array([model["stages"][s]["actions"][a]["buy14"] for s, a in zip(test["stage"], test["action"])])
    # simpler guesses, learned from the same earlier decisions
    train = J.steps(until=cut.strftime("%Y-%m-%d %H:%M:%S"))
    train = train[train["matured"]]
    tw = train["w"].to_numpy(dtype=float)
    glob = {r: np.full(len(test), float((tw * (train["reaction"] == r)).sum() / tw.sum())) for r in R}
    stage_mix = {}
    for s in model["stages"]:
        m = train[train["stage"] == s]
        mw = m["w"].to_numpy(dtype=float)
        stage_mix[s] = {r: float((mw * (m["reaction"] == r)).sum() / mw.sum()) if len(m) else 0.0 for r in R}
    by_stage = {r: np.array([stage_mix[s][r] for s in test["stage"]]) for r in R}
    return {
        "cut": cut,
        "train": len(train),
        "test": len(test),
        "scores": {
            "same mix for everyone": brier(glob, obs, w, R),
            "mix per stage (ignores the step)": brier(by_stage, obs, w, R),
            "what-if paths (stage and step)": brier(cell, obs, w, R),
        },
        "action": test["action"].to_numpy(),
        "w": w,
        "buy_pred": buy_pred,
        "bought": test["bought"].to_numpy(dtype=float),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", nargs="+", default=[None], help="CRM databases (default: the project's own)")
    ap.add_argument("--cut", default=None, help="cut-off date (default: two thirds into each history)")
    a = ap.parse_args()
    runs = [one(d, a.cut) for d in a.db]
    names = list(runs[0]["scores"])
    lines = [
        "# What-if paths: out-of-time check",
        "",
        f"{len(runs)} {'history' if len(runs) == 1 else 'histories'}: in each, the paths are learned from the "
        "decisions before a cut-off (two thirds into the history) and tested on the later decisions, weighted by "
        "1/probability.",
        "",
        "| History | Learned from / tested on | " + " | ".join(names) + " |",
        "|---|---|" + "---|" * len(names),
    ]
    for i, (d, r) in enumerate(zip(a.db, runs)):
        label = os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(d)))) if d else "this CRM"
        lines.append(
            f"| {label or i + 1} | {r['train']:,} / {r['test']:,} | "
            + " | ".join(f"{r['scores'][k]:.4f}" for k in names)
            + " |"
        )
    paths, stage = names[2], names[1]
    wins = sum(r["scores"][paths] < r["scores"][stage] for r in runs)
    diffs = np.array([r["scores"][paths] - r["scores"][stage] for r in runs])
    lines += [
        "| Mean | | " + " | ".join(f"{np.mean([r['scores'][k] for r in runs]):.4f}" for k in names) + " |",
        "",
        f"Brier score of the reaction in the next 3 days (lower is better). The what-if paths beat the mix per stage "
        f"in {wins} of {len(runs)} histories (mean difference {diffs.mean():+.4f}).",
        "",
        "| Team step | Later decisions | Predicted buying within 14 days | Actual |",
        "|---|---|---|---|",
    ]
    from app.ml import nba_core as N

    act = np.concatenate([r["action"] for r in runs])
    w = np.concatenate([r["w"] for r in runs])
    bp = np.concatenate([r["buy_pred"] for r in runs])
    y = np.concatenate([r["bought"] for r in runs])
    for s in sorted(set(act)):
        m = act == s
        label = N.ACTIONS.get(s, {}).get("label", s)
        lines.append(
            f"| {label} | {int(m.sum()):,} | {np.average(bp[m], weights=w[m]):.1%} | "
            f"{np.average(y[m], weights=w[m]):.1%} |"
        )
    lines.append(f"| All steps | {len(act):,} | {np.average(bp, weights=w):.1%} | {np.average(y, weights=w):.1%} |")
    os.makedirs(os.path.join(ROOT, "ml", "results"), exist_ok=True)
    with open(os.path.join(ROOT, "ml", "results", "paths_check.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
