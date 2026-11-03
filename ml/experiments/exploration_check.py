"""
E8b: what the random learning steps cost, and what next-best-action loses without them.

v7.0 takes 15% of next-best-action's decisions at random. They serve two purposes. (1) They kept the lead score
honest; with the anchored update and the 5% control group that no longer needs them (E8, anchored_check.py). (2) They
let next-best-action learn the effect of steps it would not choose by itself, and let the learning loop check a new
uplift model against the one in use. This study measures (2) in money.

The closed loop, month by month for 12 months, in the worlds of the robustness study (E2b, nba_robustness.py): the
documented world (the starting model's assumptions are right), the null world (no step changes anything), the
reversed world, the hidden world, and 10 random worlds. In every world the CRM starts from the model it ships with
(trained on the documented assumptions), decides for 1,000 new leads a month (greedy on extra profit, a share of the
decisions at random, every probability logged), observes who buys, and retrains exactly as the learning loop does
(app.ml.learning.retrain_nba: the documented prior plus the logged decisions weighted by 5 x clip(1 / probability, 1,
20); the new model replaces the one in use only if the lower end of the 95% interval of its profit gain on held-out
logged decisions is above zero). The same leads, the same true effects and the same random numbers are used for every
share of random steps, so the shares are compared on equal terms.

Measured with the world's true effects: the extra profit per lead over doing nothing of what the CRM actually did
(random steps included), and of its greedy policy (what it has learned), per month and in total.

Every world is run --repeats times (default 5) with new leads and new random numbers, because one run's outcome
depends a lot on whether and when a better model happens to be adopted. The shares are compared per world on the mean
over its runs, with a sign test across worlds and a 95% interval for the mean difference from resampling worlds.

Usage: python ml/experiments/exploration_check.py [--months 12] [--leads 1000] [--random-worlds 10] [--repeats 5]
Writes ml/results/exploration_check.{md,json}.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "backend"))
os.environ.setdefault("SIMULATION_ENABLED", "false")

import nba_robustness as R  # noqa: E402

from app.ml import nba_core as N  # noqa: E402
from app.ml.training import uplift as U  # noqa: E402
from app.simulation import effects as S  # noqa: E402
from app.simulation import population as G  # noqa: E402

RESULTS = os.path.join(ROOT, "ml", "results")
SHARES = [0.0, 0.05, 0.15]
REAL_WEIGHT = 5.0  # as app.ml.learning.REAL_WEIGHT_NBA
RESAMPLES = 300


def _value(choice, truth, price):
    """True extra profit per lead over doing nothing of the chosen steps."""
    acts = np.asarray(choice)
    p = np.array([truth[a][i] for i, a in enumerate(acts)])
    disc = np.array([N.ACTIONS[a]["discount"] for a in acts])
    cost = np.array([N.ACTIONS[a]["cost_inr"] for a in acts])
    return p * price * (1 - disc) - cost - truth["none"] * price


def _snips_terms(model, frame, base, blocked, price, actions, props, y):
    greedy = U.greedy_policy(U.predict_all(model, frame, base), price, blocked, capacity=1.0)
    w = (greedy == actions) / np.clip(props, 1e-3, None)
    disc = np.array([N.ACTIONS[a]["discount"] for a in actions])
    cost = np.array([N.ACTIONS[a]["cost_inr"] for a in actions])
    return w, w * (y * price * (1 - disc) - cost)


def _swap(champion, challenger, held, rng):
    """The learning loop's rule: swap when the lower end of the 95% interval of the profit gain is above zero."""
    cw, cv = _snips_terms(champion, *held)
    hw, hv = _snips_terms(challenger, *held)
    n = len(cw)
    diffs = []
    for _ in range(RESAMPLES):
        i = rng.integers(0, n, n)
        a, b = hw[i].sum(), cw[i].sum()
        if a > 0 and b > 0:
            diffs.append(hv[i].sum() / a - cv[i].sum() / b)
    if len(diffs) < RESAMPLES // 2:
        return False, None
    lo = float(np.percentile(diffs, 2.5))
    return lo > 0, lo


def run_world(name, effects_fn, prior, months, leads, seed, noise_sd=S.EFFECT_NOISE_SD):
    pf, pb, pa, py = prior
    out = {}
    months_data = []
    for m in range(months):  # the same leads, truth and random numbers for every share
        raw = G.generate(leads, seed=50_000 + 101 * seed + m, return_truth=True)
        info = R.world_info(raw)
        info["base"] = U.base_probability(info["frame"])
        truth = R.truth_for(info, effects_fn(info), 70_000 + 101 * seed + m, noise_sd)
        rng = np.random.default_rng(90_000 + 101 * seed + m)
        months_data.append((info, truth, rng.random(leads), rng.random(leads), rng.random(leads)))
    start = U.fit_uplift(pf, pb, pa, py)
    for eps in SHARES:
        model, swaps = start, 0
        log = {"frame": [], "base": [], "blocked": [], "price": [], "a": [], "p": [], "y": []}
        per_month = []
        for m, (info, truth, u_exp, u_pick, u_buy) in enumerate(months_data):
            frame, base, blocked, price = info["frame"], info["base"], info["blocked"], info["price"]
            greedy = U.greedy_policy(U.predict_all(model, frame, base), price, blocked, capacity=1.0)
            allowed = np.column_stack([~blocked[a] for a in N.ACTION_LIST])
            k = allowed.sum(1)
            pick_idx = np.array([np.flatnonzero(allowed[i])[int(u_pick[i] * k[i])] for i in range(leads)])
            randoms = np.array(N.ACTION_LIST)[pick_idx]
            explore = u_exp < eps
            choice = np.where(explore, randoms, greedy)
            prop = (1 - eps) * (choice == greedy) + eps / k
            p_buy = np.array([truth[a][i] for i, a in enumerate(choice)])
            y = (u_buy < p_buy).astype(int)
            done = _value(choice, truth, price)
            learned = _value(greedy, truth, price)
            oracle = _value(U.greedy_policy(truth, price, blocked, capacity=1.0), truth, price)
            per_month.append(
                {
                    "month": m + 1,
                    "done_per_lead": float(done.mean()),
                    "greedy_per_lead": float(learned.mean()),
                    "oracle_per_lead": float(oracle.mean()),
                    "random_steps": int(explore.sum()),
                    "swaps_so_far": swaps,
                }
            )
            for key, v in (
                ("frame", frame),
                ("base", base),
                ("blocked", blocked),
                ("price", price),
                ("a", choice),
                ("p", prop),
                ("y", y),
            ):
                log[key].append(v)
            # retrain as the learning loop does, at the end of every month
            import pandas as pd

            lf = pd.concat(log["frame"], ignore_index=True)
            lb, la, lp, ly = (np.concatenate(log[x]) for x in ("base", "a", "p", "y"))
            lprice = np.concatenate(log["price"])
            lblock = {a: np.concatenate([b[a] for b in log["blocked"]]) for a in N.ACTION_LIST}
            n = len(ly)
            rs = np.random.default_rng(3 + m)
            test = np.zeros(n, bool)
            test[rs.choice(n, size=max(1, n // 3), replace=False)] = True
            Xf = pd.concat([pf, lf[~test]], ignore_index=True)
            Xb = np.concatenate([pb, lb[~test]])
            Xa = np.concatenate([pa, la[~test]])
            Xy = np.concatenate([py, ly[~test]])
            w = np.concatenate([np.ones(len(py)), REAL_WEIGHT * np.clip(1 / lp[~test], 1, 20)])
            challenger = U.fit_uplift(Xf, Xb, Xa, Xy, weights=w)
            held = (
                lf[test].reset_index(drop=True),
                lb[test],
                {a: lblock[a][test] for a in N.ACTION_LIST},
                lprice[test],
                la[test],
                lp[test],
                ly[test],
            )
            ok, _ = _swap(model, challenger, held, np.random.default_rng(17 + m))
            if ok:
                model, swaps = challenger, swaps + 1
        out[f"{eps:.2f}"] = {
            "months": per_month,
            "total_done_per_lead": float(np.mean([r["done_per_lead"] for r in per_month])),
            "total_greedy_per_lead": float(np.mean([r["greedy_per_lead"] for r in per_month])),
            "oracle_per_lead": float(np.mean([r["oracle_per_lead"] for r in per_month])),
            "last_greedy_per_lead": per_month[-1]["greedy_per_lead"],
            "swaps": swaps,
        }
    d = {k: v["total_done_per_lead"] for k, v in out.items()}
    print(
        f"  {name:12s} extra profit per lead over {months} months (random steps 0% / 5% / 15%): "
        + " / ".join(f"₹{d[f'{e:.2f}']:,.1f}" for e in SHARES)
        + f"  (oracle ₹{out['0.15']['oracle_per_lead']:,.1f}; swaps "
        + " / ".join(str(out[f"{e:.2f}"]["swaps"]) for e in SHARES)
        + ")",
        flush=True,
    )
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=12)
    ap.add_argument("--leads", type=int, default=1000)
    ap.add_argument("--random-worlds", type=int, default=10)
    ap.add_argument("--repeats", type=int, default=5, help="independent runs per world")
    args = ap.parse_args()
    t0 = time.time()
    raw = G.generate(60000, seed=2024, return_truth=True)  # the documented prior the CRM ships with
    pf, pa, _, py, _ = S.simulate_randomized_campaign(raw, seed=11)
    prior = (pf, U.base_probability(pf), pa, py)
    worlds = {  # (effects, hidden share, per-person noise): nothing at all works in the null world, as in E2b
        "documented": (R.eff_documented, None, S.EFFECT_NOISE_SD),
        "null": (R.eff_null, None, 0.0),
        "reversed": (R.eff_reversed, None, S.EFFECT_NOISE_SD),
        "hidden": (R.eff_hidden, None, S.EFFECT_NOISE_SD),
    }
    for s in range(args.random_worlds):
        fn, lam = R.random_world(s)
        worlds[f"random_{s + 1:02d}"] = (fn, lam, S.EFFECT_NOISE_SD)
    res = {
        "months": args.months,
        "leads_per_month": args.leads,
        "repeats": args.repeats,
        "shares": SHARES,
        "worlds": {},
    }
    for i, (name, (fn, lam, noise)) in enumerate(worlds.items()):
        runs = [run_world(name, fn, prior, args.months, args.leads, i + 1000 * k, noise) for k in range(args.repeats)]
        r = summarise(runs)
        if lam is not None:
            r["hidden_share"] = lam
        res["worlds"][name] = r
    res["minutes"] = round((time.time() - t0) / 60, 1)
    os.makedirs(RESULTS, exist_ok=True)
    write_md(res)
    with open(os.path.join(RESULTS, "exploration_check.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2)


KEYS = ("total_done_per_lead", "total_greedy_per_lead", "oracle_per_lead", "last_greedy_per_lead", "swaps")


def summarise(runs):
    """One world: the mean over its independent runs (as one run's keys), each run's totals kept in "runs"."""
    out = {}
    for s in runs[0]:
        out[s] = {k: float(np.mean([r[s][k] for r in runs])) for k in KEYS}
        out[s]["runs"] = [{k: r[s][k] for k in KEYS} for r in runs]
    return out


def compare(res, a, b, key="total_done_per_lead", boot=10_000, seed=5):
    """Share a against share b over the worlds (each world's mean over its runs): wins, mean and median difference,
    a 95% interval for the mean from resampling worlds, a two-sided sign test, and wins over single runs."""
    from math import comb

    names = list(res["worlds"])
    d = np.array([res["worlds"][n][f"{a:.2f}"][key] - res["worlds"][n][f"{b:.2f}"][key] for n in names])
    rng = np.random.default_rng(seed)
    means = d[rng.integers(0, len(d), (boot, len(d)))].mean(1)
    wins, n = int((d > 0).sum()), int((d != 0).sum())
    k = min(wins, n - wins)
    p = min(1.0, 2 * sum(comb(n, j) for j in range(k + 1)) / 2**n) if n else 1.0
    runs = [
        ra[key] - rb[key]
        for nm in names
        for ra, rb in zip(res["worlds"][nm][f"{a:.2f}"]["runs"], res["worlds"][nm][f"{b:.2f}"]["runs"], strict=True)
    ]
    return {
        "worlds": len(d),
        "wins": wins,
        "losses": n - wins,
        "ties": len(d) - n,
        "mean": float(d.mean()),
        "median": float(np.median(d)),
        "ci95": [float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))],
        "worst": float(d.min()),
        "best": float(d.max()),
        "sign_p": float(p),
        "run_wins": int(sum(x > 0 for x in runs)),
        "runs": len(runs),
    }


def write_md(res):
    shares = res["shares"]
    lines = [
        "# E8b What the random learning steps cost, and what next-best-action loses without them\n",
        f"Closed loop for {res['months']} months, {res['leads_per_month']:,} new leads a month, in the worlds of "
        "E2b. The CRM starts from the model it ships with (trained on the documented assumptions) and retrains "
        "monthly exactly as the learning loop does (documented prior plus logged decisions, swap only on a clear "
        "off-policy gain). Same leads, true effects and random numbers for every share of random steps. Extra "
        "profit per lead over doing nothing, with the world's true effects (higher is better), as the mean of "
        f"{res.get('repeats', 1)} independent runs per world (new leads and random numbers in each); swaps are the "
        "mean number of model replacements per run. Made by `ml/experiments/exploration_check.py`.\n",
        "| World | Oracle | "
        + " | ".join(f"{int(s * 100)}% random: what it did" for s in shares)
        + " | "
        + " | ".join(f"{int(s * 100)}%: learned policy, last month" for s in shares)
        + " | Swaps ("
        + " / ".join(f"{int(s * 100)}%" for s in shares)
        + ") |",
        "|---|---|" + "---|" * (2 * len(shares)) + "---|",
    ]
    for name, w in res["worlds"].items():
        k = [f"{s:.2f}" for s in shares]
        label = name.replace("_", " ") + (f" (hidden {w['hidden_share']:.2f})" if "hidden_share" in w else "")
        lines.append(
            f"| {label} | ₹{w['0.15']['oracle_per_lead']:,.1f} | "
            + " | ".join(f"₹{w[x]['total_done_per_lead']:,.1f}" for x in k)
            + " | "
            + " | ".join(f"₹{w[x]['last_greedy_per_lead']:,.1f}" for x in k)
            + " | "
            + " / ".join(f"{w[x]['swaps']:.1f}" for x in k)
            + " |"
        )
    res["comparisons"] = {}
    for a, b in ((0.05, 0.15), (0.0, 0.15), (0.0, 0.05)):
        c = compare(res, a, b)
        g = compare(res, a, b, key="last_greedy_per_lead")
        res["comparisons"][f"{a:.2f}_vs_{b:.2f}"] = {"done": c, "learned_last_month": g}
        lines.append(
            f"\n**{int(a * 100)}% against {int(b * 100)}% random steps.** What it did: more profit in "
            f"**{c['wins']} of {c['worlds']}** worlds (two-sided sign test p {c['sign_p']:.3f}) and in {c['run_wins']} "
            f"of {c['runs']} single runs; mean difference ₹{c['mean']:+,.1f} per lead (95% interval "
            f"₹{c['ci95'][0]:+,.1f} to ₹{c['ci95'][1]:+,.1f}; ₹{c['mean'] * 1000:+,.0f} per 1,000 leads), median "
            f"₹{c['median']:+,.1f}, worst world ₹{c['worst']:+,.1f}, best ₹{c['best']:+,.1f}. What it had learned by "
            f"the last month (its greedy policy): better in {g['wins']}, worse in {g['losses']} and the same in "
            f"{g['ties']} of {g['worlds']} worlds, mean "
            f"₹{g['mean']:+,.1f} per lead (95% interval ₹{g['ci95'][0]:+,.1f} to ₹{g['ci95'][1]:+,.1f})."
        )
    with open(os.path.join(RESULTS, "exploration_check.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("wrote ml/results/exploration_check.md")


if __name__ == "__main__":
    main()
