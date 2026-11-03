"""
E7: capacity-aware next-best-action. Does pricing a call slot beat first come, first served?

The counsellors can make only C calls a day, but next-best-action decides one learner at a time, as triggers arrive.
This compares five ways of spending the C slots, on simulated days whose true effects are known
(app.simulation.effects), with the production pricing code (app.ml.capacity.SlotPricer):

    no calls            calls are never used (the floor: what the other steps earn on their own)
    first come          the model's best step for each learner; a call while slots are left (the usual cap)
    fixed price         a call only when it adds more than one price, the same all day (from the last 7 days)
    re-solved price     ours: the price is worked out again at every decision from the slots left and the share of
                        the day's call-worthy decisions still to come (both from the last 7 days)
    hindsight           the C learners with the largest predicted call advantage of the whole day (needs the day's
                        future, so it is the best any online rule could do with the same predictions)
    true hindsight      the same with the true advantages (the ceiling, including perfect prediction)

Every policy sees the same learners, in the same order, with the same predictions (the starting uplift model) and is
scored with the simulator's true probabilities, as expected profit (no outcome noise). A call's advantage is what it
adds over the best step that needs no call. Days differ in demand (weekends are quieter, plus noise), and in one
scenario demand doubles half-way, to test how fast the 7-day look-back adapts.

Output: ml/results/capacity_check.{json,md} and figures/capacity_share.png.
Run: python ml/experiments/capacity_check.py [quick | report]   (report: rebuild the report from the saved results)
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("SCHEDULER_ENABLED", "false")

import joblib  # noqa: E402
import numpy as np  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.ml import capacity  # noqa: E402
from app.ml import features as F  # noqa: E402
from app.ml import lead_model as LM  # noqa: E402
from app.ml import nba_core as N  # noqa: E402
from app.simulation import effects as S  # noqa: E402
from app.simulation import population as G  # noqa: E402

RESULTS = ROOT / "ml" / "results"
QUICK = len(sys.argv) > 1 and sys.argv[1] == "quick"
CAPACITY = 20
DAYS = 60
WARMUP = 7  # the price needs a week of decisions first
SEEDS = 4 if QUICK else 10
POOL = 60_000 if QUICK else 150_000
# demand: decisions per day whose call would add value (call-worthy), as a multiple of the capacity
DEMAND = [0.5, 1, 2, 4, 8]
# when decisions arrive during the day (share per hour, 0-23): evenings are busiest on a learning website
HOURLY = np.array(
    [
        0.2,
        0.1,
        0.05,
        0.05,
        0.05,
        0.1,
        0.3,
        0.6,
        1.0,
        1.2,
        1.3,
        1.3,
        1.2,
        1.2,
        1.3,
        1.4,
        1.5,
        1.7,
        2.0,
        2.4,
        2.6,
        2.4,
        1.6,
        0.8,
    ]
)
POLICIES = ["no calls", "first come", "fixed price", "re-solved price", "hindsight", "true hindsight"]


def logit(p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def values(probs: dict, price: np.ndarray) -> np.ndarray:
    """Incremental profit of every step for every row: an array (rows x steps), in N.ACTION_LIST order."""
    base = probs["none"] * price
    cols = []
    for a in N.ACTION_LIST:
        spec = N.ACTIONS[a]
        cols.append(probs[a] * price * (1 - spec["discount"]) - spec["cost_inr"] - base)
    return np.column_stack(cols)


def build_pool(seed: int):
    """Learners at a trigger, with predicted and true incremental profit for every step."""
    d = get_settings().model_dir
    lead = joblib.load(d / "lead_model.pkl")
    nba = joblib.load(d / "nba_model.pkl")
    raw = G.generate(POOL, seed=seed, return_truth=True)
    frame = F.to_model_frame(raw)
    base = LM.predict_proba(lead, frame)
    pred = N.predict_actions(nba["model"], frame, base)
    shift = logit(base) - logit(pred["none"])  # anchored on the lead score, as in production
    pred = {a: 1 / (1 + np.exp(-(logit(p) + shift))) for a, p in pred.items()}
    truth = S.true_probabilities(frame, raw["_p_true"].to_numpy(), seed=seed + 1)
    price = S.prices_for(frame)
    blocked = S.blocked_matrix(frame)
    B = np.column_stack([blocked[a] for a in N.ACTION_LIST])
    vp, vt = values(pred, price), values(truth, price)
    vp[B] = -np.inf
    vt[B] = -np.inf
    vp[:, 0] = 0.0  # doing nothing is always possible
    vt[:, 0] = 0.0
    return vp, vt


CALL = N.ACTION_LIST.index("call")
NONCALL = [i for i in range(len(N.ACTION_LIST)) if i != CALL]


def advantages(v: np.ndarray) -> np.ndarray:
    """What a call adds over the best step without one (-inf when a call is not possible)."""
    return v[:, CALL] - v[:, NONCALL].max(axis=1)


def simulate(seed: int, demand: float, drift: bool, pool):
    vp, vt = pool
    rng = np.random.default_rng(seed)
    adv_p, adv_t = advantages(vp), advantages(vt)
    best_noncall_p = np.array(NONCALL)[vp[:, NONCALL].argmax(axis=1)]
    worthy = float(np.mean(adv_p > 0))  # share of decisions where a call would add value
    base_rate = demand * CAPACITY / max(worthy, 1e-6)  # decisions per day for this demand level
    hourly = HOURLY / HOURLY.sum()
    history = []  # (day, time of day, predicted advantage)
    totals = {p: [] for p in POLICIES}
    calls = {p: [] for p in POLICIES}
    for day in range(DAYS):
        weekday = day % 7
        factor = (0.7 if weekday in (5, 6) else 1.0) * float(rng.lognormal(0, 0.15))
        if drift and day >= DAYS // 2:
            factor *= 2.0
        n = int(rng.poisson(base_rate * factor))
        rows = rng.integers(0, len(vp), n)
        hours = rng.choice(24, size=n, p=hourly)
        t = (hours + rng.random(n)) / 24.0
        order = np.argsort(t)  # arrivals in time order
        order_rows, tod = rows[order], t[order]
        a_p, a_t = adv_p[order_rows], adv_t[order_rows]
        best_p = vp[order_rows].argmax(axis=1)  # the model's step without any price
        alt = best_noncall_p[order_rows]
        win = [h for h in history if h[0] >= day - capacity.CONF["lookback_days"]]
        pricer = capacity.SlotPricer(
            [h[2] for h in win], [h[1] for h in win], len({h[0] for h in win}), CAPACITY, "priced"
        )
        if day >= WARMUP:
            chosen = {}
            chosen["no calls"] = alt
            # first come, first served
            pick, used = alt.copy(), 0
            for i in range(n):
                if best_p[i] == CALL and used < CAPACITY:
                    pick[i], used = CALL, used + 1
            chosen["first come"] = pick
            for name, static in (("fixed price", True), ("re-solved price", False)):
                pick, used = alt.copy(), 0
                for i in range(n):
                    if not np.isfinite(a_p[i]) or used >= CAPACITY:
                        continue
                    if a_p[i] > pricer.price(CAPACITY - used, float(tod[i]), static=static) and a_p[i] > 0:
                        pick[i], used = CALL, used + 1
                chosen[name] = pick
            for name, adv in (("hindsight", a_p), ("true hindsight", a_t)):
                pick = alt.copy()
                if n:
                    top = np.argsort(-adv)[:CAPACITY]
                    top = top[np.isfinite(adv[top]) & (adv[top] > 0)]
                    pick[top] = CALL
                chosen[name] = pick
            truth = vt[order_rows]
            for name, pick in chosen.items():
                totals[name].append(float(truth[np.arange(n), pick].sum()))
                calls[name].append(int((pick == CALL).sum()))
        history += [(day, float(t), float(a)) for t, a in zip(tod, a_p) if np.isfinite(a)]
    return {p: (float(np.mean(totals[p])), float(np.mean(calls[p]))) for p in POLICIES}


def run_scenario(demand, drift, pools):
    per_seed = [simulate(1000 + s, demand, drift, pools[s % len(pools)]) for s in range(SEEDS)]
    out = {}
    floor = np.array([r["no calls"][0] for r in per_seed])
    ceil = np.array([r["hindsight"][0] for r in per_seed])
    fcfs = np.array([r["first come"][0] for r in per_seed])
    for p in POLICIES:
        v = np.array([r[p][0] for r in per_seed])
        share = (v - floor) / np.maximum(ceil - floor, 1e-9)
        diff = v - fcfs
        se = lambda x: float(np.std(x, ddof=1) / np.sqrt(len(x))) if len(x) > 1 else 0.0
        out[p] = {
            "profit_per_day": round(float(v.mean())),
            "calls_per_day": round(float(np.mean([r[p][1] for r in per_seed])), 1),
            "share_of_hindsight": round(float(share.mean()), 3),
            "share_ci95": round(1.96 * se(share), 3),
            "vs_first_come_per_day": round(float(diff.mean())),
            "vs_first_come_ci95": round(1.96 * se(diff)),
        }
    return out


def main():
    t0 = time.time()
    print(f"E7 capacity-aware next-best-action: {SEEDS} seeds x {DAYS} days, {CAPACITY} calls a day", flush=True)
    pools = [build_pool(77 + k) for k in range(2 if not QUICK else 1)]
    worthy = float(np.mean(advantages(pools[0][0]) > 0))
    print(f"  {POOL:,} learners per pool; a call would add value for {worthy:.1%} of decisions", flush=True)
    results = {
        "settings": {
            "capacity": CAPACITY,
            "days": DAYS,
            "warmup_days": WARMUP,
            "seeds": SEEDS,
            "lookback_days": capacity.CONF["lookback_days"],
            "pool": POOL,
            "call_worthy_share": round(worthy, 4),
        },
        "scenarios": [],
    }
    for drift in (False, True):
        for demand in DEMAND if not drift else [2, 4]:
            res = run_scenario(demand, drift, pools)
            label = f"demand {demand}x capacity" + (", doubling half-way" if drift else "")
            results["scenarios"].append({"label": label, "demand": demand, "drift": drift, "policies": res})
            line = ", ".join(f"{p}: {res[p]['share_of_hindsight'] * 100:.0f}%" for p in POLICIES[1:4])
            print(f"  {label:38s} {line}", flush=True)
    results["seconds"] = round(time.time() - t0, 1)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "capacity_check.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    write_report(results)


RULES = {
    "no calls": "calls are never used (what the other steps earn on their own)",
    "first come": "the model's best step for each learner, a call while slots are left (the usual daily cap)",
    "fixed price": "a call only when it adds more than one price, the same all day (from the last 7 days)",
    "re-solved price": "ours: the price is worked out again at every decision from the slots left and the share of "
    "the day's call-worthy decisions still to come",
    "hindsight": "the day's largest predicted call advantages (needs the day's future: the best any online rule "
    "could do with the same predictions)",
    "true hindsight": "the same with the true advantages (the ceiling, with perfect prediction too)",
}


def write_report(results: dict) -> None:
    st = results["settings"]
    lines = [
        "# E7: capacity-aware next-best-action",
        "",
        f"{st['seeds']} simulated runs of {st['days']} days (the first {st['warmup_days']} build the price), "
        f"{st['capacity']} calls a day. Value is the true expected extra profit per day (INR) against doing "
        "nothing; 'share' is the part of the value of the call slots that each rule captures, between using no "
        "calls (0%) and the best allocation with hindsight (100%), with a 95% interval across runs.",
        "",
        "Rules compared:",
        "",
    ]
    lines += [f"- **{name}**: {text}" for name, text in RULES.items()]
    lines += [
        "",
        "## Summary",
        "",
        "| Scenario | First come | Fixed price | Re-solved price (ours) | Ours against first come, INR per day |",
        "|---|---|---|---|---|",
    ]
    over = []
    for sc in results["scenarios"]:
        pol = sc["policies"]
        lines.append(
            f"| {sc['label']} | {pol['first come']['share_of_hindsight'] * 100:.1f}% | "
            f"{pol['fixed price']['share_of_hindsight'] * 100:.1f}% | "
            f"{pol['re-solved price']['share_of_hindsight'] * 100:.1f}% | "
            f"{pol['re-solved price']['vs_first_come_per_day']:+,} (+/- {pol['re-solved price']['vs_first_come_ci95']:,}) |"
        )
        if sc["demand"] >= 2 and not sc["drift"]:
            over.append(sc)
    if over:
        fc = [sc["policies"]["first come"]["share_of_hindsight"] * 100 for sc in over]
        rs = [sc["policies"]["re-solved price"]["share_of_hindsight"] * 100 for sc in over]
        gain = [sc["policies"]["re-solved price"]["vs_first_come_per_day"] for sc in over]
        lines += [
            "",
            f"When demand for calls is {over[0]['demand']}x to {over[-1]['demand']}x the capacity, first "
            f"come, first served captures {min(fc):.0f}% to {max(fc):.0f}% of the value of the call slots; the "
            f"re-solved slot price captures {min(rs):.0f}% to {max(rs):.0f}%, that is {min(gain):+,} to "
            f"{max(gain):+,} INR a day with {st['capacity']} calls a day. With spare capacity (0.5x) every rule "
            "uses the same calls, so pricing costs nothing when it is not needed.",
        ]
    for sc in results["scenarios"]:
        lines += [
            "",
            f"## {sc['label']}",
            "",
            "| Rule | Profit per day | Calls per day | Share of hindsight | " "Against first come, per day |",
            "|---|---|---|---|---|",
        ]
        for name, r in sc["policies"].items():
            lines.append(
                f"| {name} | {r['profit_per_day']:,} | {r['calls_per_day']} | "
                f"{r['share_of_hindsight'] * 100:.1f}% (+/- {r['share_ci95'] * 100:.1f}) | "
                f"{r['vs_first_come_per_day']:+,} (+/- {r['vs_first_come_ci95']:,}) |"
            )
    lines.append("")
    (RESULTS / "capacity_check.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved ml/results/capacity_check.md ({results.get('seconds', 0)} s)")
    figure(results)


def figure(results: dict) -> None:
    """Share of the hindsight value captured, by demand (ml/results/figures/capacity_share.png)."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("  (matplotlib is not installed, so no figure: pip install -r ml/requirements.txt)")
        return
    steady = [sc for sc in results["scenarios"] if not sc["drift"]]
    demand = [sc["demand"] for sc in steady]
    fig, ax = plt.subplots(figsize=(6.4, 3.8), dpi=150)
    series = [
        ("first come", "First come, first served", "#eb6834", "o"),
        ("fixed price", "Fixed price", "#1baf7a", "s"),
        ("re-solved price", "Re-solved price (ours)", "#2a78d6", "D"),
    ]
    for key, label, color, marker in series:
        share = [sc["policies"][key]["share_of_hindsight"] * 100 for sc in steady]
        ax.plot(demand, share, color=color, linewidth=2, marker=marker, markersize=6, label=label)
    ax.set_xscale("log", base=2)
    ax.set_xticks(demand)
    ax.set_xticklabels([f"{d:g}x" for d in demand])
    ax.set_ylim(0, 105)
    ax.set_xlabel("Call-worthy decisions a day, as a multiple of the call capacity")
    ax.set_ylabel("Share of hindsight value (%)")
    ax.grid(axis="y", color="#e3e5ea", linewidth=0.8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.legend(frameon=False, loc="lower left")
    fig.tight_layout()
    out = RESULTS / "figures"
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / "capacity_share.png")
    plt.close(fig)
    print("Saved ml/results/figures/capacity_share.png")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "report":  # rebuild the report and figure from the saved results
        write_report(json.loads((RESULTS / "capacity_check.json").read_text(encoding="utf-8")))
    else:
        main()
