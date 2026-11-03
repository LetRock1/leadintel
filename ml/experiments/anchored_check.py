"""
E8: the anchored update inside the product, judged on learners nobody contacted and nobody trained on.

The histories (anchored_histories.py) are the CRM running by itself for 180 days with one setting changed (the share
of learners it never contacts, the share of random next-best-action steps). Each also keeps an evaluation group of
10% of learners that the CRM never contacts and that no retraining method ever sees. At every learning date of every
history, the same logged decision points (without the evaluation group) are given to six retraining methods of the
lead score's live layer:

    naive          not told what the CRM did (how CRMs usually retrain)
    v7.0           told what the CRM did; the effect of each step is learned by the model (action-aware)
    anchored       each step's effect fixed at its design-based lift (the CRM's own cut-off, random
                   leaving-alone, campaign and A/B hold-outs), the paper's estimators applied per step
    anchored, shrunk  the same, each lift weighed against the model's own estimate by the design's precision (the
                   kit's shrunk variant: a lift from a handful of leads hardly moves the model's estimate)
    never-contacted   each step's effect from leads acted on against the never-contacted control group only (v7.1's
                   default, "anchored_control"); steps without that contrast, and everything with no control group,
                   learned as in v7.0
    anchored, one  the paper's own single-action setting: one lift for "the CRM took some step"

and each method's score ("the chance to buy if we do nothing now", time effects kept) is judged on the evaluation
group's decision points: log-loss (a proper scoring rule), AUC, and how much it over-states their buying, for all of
them and for those the CRM would have acted on (its targeted leads: where the CRM's own effect is largest).

Usage: python ml/experiments/anchored_check.py                     makes the reported 11 histories (PLAN; about
                                                                   3 hours with 2 jobs), then analyses them
       python ml/experiments/anchored_check.py --seeds 2026 11       every setting with these seeds instead
       python ml/experiments/anchored_check.py FOLDER [FOLDER ...]  histories already made by anchored_histories.py
Each history's numbers are kept in FOLDER/e8_cells.json (reused only if this script, anchor.py and learning.py are
unchanged); --jobs analyses that many histories at once.
Writes ml/results/anchored_check.{md,json}.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))
os.environ.setdefault("SIMULATION_ENABLED", "false")

import joblib  # noqa: E402

from app.ml import anchor as AN  # noqa: E402
from app.ml import learning as L  # noqa: E402

RESULTS = os.path.join(ROOT, "ml", "results")
METHODS = ["naive", "action_aware", "anchored", "anchored_shrunk", "anchored_control", "anchored_any"]
NAME = {
    "naive": "Naive retrain",
    "action_aware": "v7.0: told what the CRM did",
    "anchored": "Anchored per step (the kit's main estimator)",
    "anchored_shrunk": "Anchored per step, weighed against the model's own (the kit's shrunk variant)",
    "anchored_any": "Anchored, one lift for any step (the kit's single-action setting)",
    "anchored_control": "Anchored per step, left alone = never contacted (the control group only)",
}
SETTING_TEXT = {
    "c5_e15": "5% control group, 15% random steps (v7.0's settings)",
    "c5_e05": "5% control group, 5% random steps",
    "c5_e00": "5% control group, no random steps",
    "c0_e15": "no control group, 15% random steps",
    "c0_e00": "no control group, no random steps",
}
ORDER = list(SETTING_TEXT)
# the histories of the reported study: three seeds where the CRM keeps a control group, one where it does not (there
# the never-contacted method is exactly v7.0's, and one seed already shows how the research kit's estimators behave)
PLAN = [(["c5_e15", "c5_e05", "c5_e00"], [2026, 11, 12]), (["c0_e15", "c0_e00"], [2026])]
BOOT = 2000


def in_eval(uid, share):
    h = hashlib.sha256(f"global-control:{uid}".encode()).hexdigest()
    return int(h[:15], 16) / float(16**15) < share


def logloss_rows(y, p):
    p = np.clip(np.asarray(p, float), 1e-5, 1 - 1e-5)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def one_history(folder):
    with open(os.path.join(folder, "done.json"), encoding="utf-8") as f:
        info = json.load(f)
    con = sqlite3.connect(os.path.join(folder, "backend", "data", "xeducation.db"))
    bundle = joblib.load(os.path.join(folder, "backend", "data", "models", "lead_model.starter.pkl"))
    dates = [
        r[0] for r in con.execute("SELECT as_of FROM learning_runs WHERE simulated=1 AND status='done' ORDER BY as_of")
    ]
    out = []
    for k, as_of in enumerate(dates):
        rows = L.assemble(con, as_of)
        if len(rows) < 300:
            continue
        ev = np.array([in_eval(u, info["eval_share"]) for u in rows["user_id"]])
        tr_rows = rows[~ev].reset_index(drop=True)
        ev_rows = rows[ev].reset_index(drop=True)
        ye = ev_rows["y"].to_numpy(dtype=int)
        if len(ev_rows) < 30 or ye.sum() < 5 or (len(ye) - ye.sum()) < 5:
            continue
        y = tr_rows["y"].to_numpy(dtype=int)
        z, S, Nm = L.arrays(bundle, tr_rows)
        ze, Se, Nme = L.arrays(bundle, ev_rows)
        geo = AN.nba_geometry(tr_rows)
        design = AN.designs(tr_rows, y, geo)
        preds, steps = {}, {}
        for m in METHODS:
            live, eff, _ = L._fit(m, z, S, y, Nm, design=design)
            preds[m] = L._p(live, ze, Se, Nme, eff)  # the evaluation group as it was: left alone, time kept
            steps[m] = {c: eff.get(c) for c in L.ACTION_COLS}
        targeted = ev_rows["model_best"].fillna("none").to_numpy() != "none"
        out.append(
            {
                "setting": info["setting"],
                "seed": info["seed"],
                "as_of": as_of,
                "run": k + 1,
                "final": k == len(dates) - 1,
                "train_rows": int(len(tr_rows)),
                "acted_share": float((tr_rows["action"] != "none").mean()),
                "eval_rows": int(len(ev_rows)),
                "eval_people": int(ev_rows["user_id"].nunique()),
                "users": ev_rows["user_id"].to_numpy().tolist(),
                "y": ye.tolist(),
                "targeted": targeted.tolist(),
                "pred": {m: preds[m].tolist() for m in METHODS},
                "steps": steps,
                "design": AN.jsonable(
                    {s: {k2: design[s][k2] for k2 in ("threshold", "random", "experiments", "design")} for s in design}
                ),
            }
        )
    con.close()
    return out


def summarise(cells, subset=None):
    """Pooled over the cells (histories x dates): per method log-loss, AUC, mean predicted vs actual; paired
    log-loss differences against v7.0 with a 95% interval by resampling people (people of different histories are
    independent; one person's rows stay together, across learning dates too)."""
    ys, people, preds = [], [], defaultdict(list)
    for c in cells:
        mask = np.ones(len(c["y"]), bool) if subset is None else np.asarray(c[subset], bool)
        ys.append(np.asarray(c["y"])[mask])
        # one cluster per person and history: the same person appears at several learning dates
        people += [f"{c['setting']}-{c['seed']}-{u}" for u, keep in zip(c["users"], mask) if keep]
        for m in METHODS:
            preds[m].append(np.asarray(c["pred"][m])[mask])
    y = np.concatenate(ys) if ys else np.array([])
    if len(y) == 0:
        return None
    P = {m: np.concatenate(preds[m]) for m in METHODS}
    out = {"rows": int(len(y)), "bought": float(y.mean()), "methods": {}}
    ids, inv = np.unique(np.array(people), return_inverse=True)
    loss = {m: np.bincount(inv, weights=logloss_rows(y, P[m]), minlength=len(ids)) for m in METHODS}
    cnt = np.bincount(inv, minlength=len(ids))
    rng = np.random.default_rng(8)
    picks = [rng.integers(0, len(ids), len(ids)) for _ in range(BOOT)]
    for m in METHODS:
        auc = L.wauc(y, P[m])
        out["methods"][m] = {
            "logloss": float(loss[m].sum() / cnt.sum()),
            "auc": auc,
            "predicted": float(P[m].mean()),
            "overstates": float(P[m].mean() / y.mean() - 1) if y.mean() > 0 else None,
        }
        for ref in ("action_aware", "naive"):
            if m == ref:
                continue
            d = loss[m] - loss[ref]
            sims = np.array([d[p].sum() / cnt[p].sum() for p in picks])
            out["methods"][m][f"vs_{ref}"] = {
                "diff_x1000": float(d.sum() / cnt.sum() * 1000),
                "ci95_x1000": [float(np.percentile(sims, 2.5) * 1000), float(np.percentile(sims, 97.5) * 1000)],
            }
    return out


def fmt_ci(v):
    if not v:
        return ""
    lo, hi = v["ci95_x1000"]
    return f"{v['diff_x1000']:+.2f} [{lo:+.2f}, {hi:+.2f}]"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folders", nargs="*")
    ap.add_argument("--seeds", type=int, nargs="+", default=None)
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--keep", action="store_true", help="keep the history copies it makes")
    args = ap.parse_args()
    folders, work = list(args.folders), None
    if not folders:  # make the histories first, in a temporary folder
        import shutil
        import subprocess
        import tempfile

        work = tempfile.mkdtemp(prefix="xedu_anchored_")
        cmd = [sys.executable, os.path.join(HERE, "anchored_histories.py"), "--out", work, "--jobs", str(args.jobs)]
        for settings, seeds in [(list(SETTING_TEXT), args.seeds)] if args.seeds else PLAN:
            subprocess.run(cmd + ["--settings", *settings, "--seeds", *map(str, seeds)], check=True)
        folders = sorted(os.path.join(work, d) for d in os.listdir(work))
    try:
        run_analysis(folders, args.jobs)
    finally:
        if work and not args.keep:
            shutil.rmtree(work, ignore_errors=True)


def _fingerprint():
    h = hashlib.sha256()
    for path in (__file__, AN.__file__, L.__file__):
        with open(path, "rb") as f:
            h.update(f.read())
    return h.hexdigest()[:16]


def cached_history(folder):
    """one_history, kept in FOLDER/e8_cells.json and reused while the code is unchanged."""
    path = os.path.join(folder, "e8_cells.json")
    code = _fingerprint()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)
        if saved.get("code") == code:
            print("reusing", os.path.basename(os.path.normpath(folder)), flush=True)
            return saved["cells"]
    print("analysing", os.path.basename(os.path.normpath(folder)), flush=True)
    cells = one_history(folder)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"code": code, "cells": AN.jsonable(cells)}, f)
    return cells


def run_analysis(folders, jobs=1):
    cells = []
    if jobs > 1:
        from concurrent.futures import ProcessPoolExecutor

        with ProcessPoolExecutor(max_workers=jobs) as ex:
            for part in ex.map(cached_history, folders):
                cells += part
    else:
        for f in folders:
            cells += cached_history(f)
    by = defaultdict(list)
    for c in cells:
        by[c["setting"]].append(c)
    res = {"settings": {}}
    for s in [x for x in ORDER if x in by]:
        cs = by[s]
        fin = [c for c in cs if c["final"]]
        wins = defaultdict(int)
        for c in cs:
            y = np.asarray(c["y"])
            ll = {m: logloss_rows(y, np.asarray(c["pred"][m])).mean() for m in METHODS}
            wins["anchored_beats_v70"] += int(ll["anchored"] < ll["action_aware"])
            wins["anchored_beats_naive"] += ll["anchored"] < ll["naive"]
            wins["anchored_any_beats_v70"] += ll["anchored_any"] < ll["action_aware"]
            wins["anchored_beats_anchored_any"] += ll["anchored"] < ll["anchored_any"]
            wins["shrunk_beats_v70"] += ll["anchored_shrunk"] < ll["action_aware"]
            wins["shrunk_beats_naive"] += ll["anchored_shrunk"] < ll["naive"]
            wins["shrunk_beats_anchored"] += ll["anchored_shrunk"] < ll["anchored"]
            wins["control_beats_v70"] += ll["anchored_control"] < ll["action_aware"]
            for m in METHODS:  # how often each method is the worst of the informed ones by a wide margin
                wins[f"worst_{m}"] += ll[m] == max(ll[x] for x in METHODS if x != "naive") and m != "naive"
        steps = defaultdict(lambda: defaultdict(list))
        for c in fin:
            for m in ("action_aware", "anchored", "anchored_shrunk", "anchored_control"):
                for st, b in c["steps"][m].items():
                    if b is not None:
                        steps[m][st].append(b)
            steps["anchored_any"]["any"].append((c["design"].get("any") or {}).get("design", [None])[0])
        res["settings"][s] = {
            "text": SETTING_TEXT[s],
            "histories": len({c["seed"] for c in cs}),
            "cells": len(cs),
            "all_dates": {"all": summarise(cs), "targeted": summarise(cs, "targeted")},
            "final_date": {"all": summarise(fin), "targeted": summarise(fin, "targeted")},
            "wins": dict(wins),
            "step_effects_final": {
                m: {st: float(np.nanmean([v for v in vals if v is not None])) for st, vals in d.items()}
                for m, d in steps.items()
            },
            "train_rows_final": float(np.mean([c["train_rows"] for c in fin])) if fin else None,
            "eval_people_final": float(np.mean([c["eval_people"] for c in fin])) if fin else None,
        }
    os.makedirs(RESULTS, exist_ok=True)
    with open(os.path.join(RESULTS, "anchored_check.json"), "w", encoding="utf-8") as f:
        json.dump(AN.jsonable(res), f, indent=2)
    write_md(res)


def write_md(res):
    L_ = []
    w = L_.append
    w("# E8 The anchored update inside the product (simulated histories)\n")
    w(
        "Each history is the CRM running by itself for 180 days on 2,000 simulated learners, with one setting changed. "
        "An extra 10% of learners (the evaluation group) is never contacted and never used for training: every "
        "retraining method's score is judged on their outcomes. At each monthly learning date the methods refit the "
        "lead score's live layer on the same logged decision points (the evaluation group left out). Made by "
        "`ml/experiments/anchored_histories.py` and `ml/experiments/anchored_check.py`.\n"
    )
    w(
        'What is judged: each score as "the chance to buy within 14 days if the CRM never contacts the lead", the '
        "same target as the learning loop's own control-group check. The comparison is offline: every method is fitted "
        "on the same logs, made by one run of the CRM (which retrained with the research kit's estimator during the "
        "history); how each method would change the CRM's later decisions is not measured here.\n"
    )
    w(
        "*Log-loss* is a proper scoring rule (lower is better; differences x1000, paired on the same rows, 95% "
        "interval from resampling people, each person's rows at every learning date kept together). *Over-states* = "
        "mean predicted chance to buy within 14 days over the share that bought, minus 1. *Targeted* = decision points "
        "where the CRM would have taken a step (where its own effect is largest).\n"
    )
    for r in res["settings"].values():
        w(f"## {r['text']}\n")
        w(
            f"{r['histories']} histories, {r['cells']} learning dates; at the last date on average "
            f"{r['train_rows_final']:,.0f} logged decision points to learn from and {r['eval_people_final']:.0f} "
            "evaluation-group learners.\n"
        )
        for when in ("final_date", "all_dates"):
            label = "last learning date of each history" if when == "final_date" else "every learning date"
            w(f"**{label.capitalize()}**\n")
            w(
                "| Method | Log-loss | AUC | Over-states | Log-loss vs v7.0 (x1000) | Targeted: log-loss | "
                "Targeted: over-states | Targeted: vs v7.0 (x1000) |"
            )
            w("|---|---|---|---|---|---|---|---|")
            a, t = r[when]["all"], r[when]["targeted"]
            for m in METHODS:
                ma, mt = a["methods"][m], (t["methods"][m] if t else None)
                w(
                    f"| {NAME[m]} | {ma['logloss']:.4f} | {ma['auc']:.3f} | {ma['overstates'] * 100:+.0f}% | "
                    f"{fmt_ci(ma.get('vs_action_aware')) or 'reference'} | "
                    f"{mt['logloss']:.4f} | {mt['overstates'] * 100:+.0f}% | "
                    f"{fmt_ci(mt.get('vs_action_aware')) or 'reference'} |"
                    if mt
                    else ""
                )
            w(
                f"\n{a['rows']:,} decision points of the evaluation group ({a['bought'] * 100:.1f}% bought); targeted "
                f"{t['rows'] if t else 0:,}.\n"
            )
        wn, n = r["wins"], r["cells"]
        w(
            f"Lower log-loss than v7.0, of {n} learning dates: anchored {wn.get('anchored_beats_v70', 0)}, shrunk "
            f"{wn.get('shrunk_beats_v70', 0)}, never-contacted {wn.get('control_beats_v70', 0)}, one lift "
            f"{wn.get('anchored_any_beats_v70', 0)}. Than the naive "
            f"retrain: anchored {wn.get('anchored_beats_naive', 0)}, shrunk {wn.get('shrunk_beats_naive', 0)}. "
            f"Shrunk better than anchored in {wn.get('shrunk_beats_anchored', 0)}; per step better than one lift in "
            f"{wn.get('anchored_beats_anchored_any', 0)}. Worst of the informed methods: "
            + ", ".join(f"{NAME[m].split(' (')[0]} {wn.get(f'worst_{m}', 0)}" for m in METHODS if m != "naive")
            + ".\n"
        )
        se = r["step_effects_final"]
        if se.get("anchored"):
            w("Each step's effect on the log-odds of buying at the last date (mean over the histories):\n")
            w("| Step | v7.0, learned by the model | Anchored, from the design | Shrunk | Never-contacted |")
            w("|---|---|---|---|---|")
            for st in L.ACTION_COLS:
                vals = [
                    se.get(m, {}).get(st) for m in ("action_aware", "anchored", "anchored_shrunk", "anchored_control")
                ]
                w(
                    f"| {L.LABELS.get(st, st)} | "
                    + " | ".join("n/a" if v is None or not np.isfinite(v) else f"{v:+.2f}" for v in vals)
                    + " |"
                )
            anyv = se.get("anchored_any", {}).get("any")
            if anyv is not None and np.isfinite(anyv):
                w(f"\nOne lift for any step (the paper's setting): {anyv:+.2f}.\n")
            w("")
    with open(os.path.join(RESULTS, "anchored_check.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(x for x in L_ if x is not None) + "\n")
    print("wrote ml/results/anchored_check.md")


if __name__ == "__main__":
    main()
