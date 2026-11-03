"""
E9: the CRM's money features against known truth.

The pipeline in rupees, the coupon guard, the discount budget and the owner's planner all rest on the numbers that
next-best-action already uses: each lead's chance to buy with no contact (the honest lead score) and with each step.
This experiment checks them on simulated learners whose true response to every step is known
(app.simulation.effects), with the production code (app.ml.budget.BudgetPricer, app.ml.capacity.SlotPricer,
app.services.planner.slots_value) and the starting models that every fresh install trains:

    a  discount budget     a monthly discount budget spent with the re-solved price of a rupee of discount (ours),
                           against first come, first served, the usual cart-recovery rule (a 10% coupon to every left
                           cart while money lasts), a fixed price, and the best allocation with hindsight; and whether
                           each rule stays within the budget in truth
    b  coupon guard        coupons a counsellor would give by hand (to the warmest leads, to every left cart, to
                           anyone): how many the guard stops, and whether the stopped coupons really lose money
    c  pipeline in rupees  are 'comes in anyway' and 'the team can add' close to the truth, and when the team can
                           work only some of the open leads, does the money order (most to add first) add more than
                           the usual order (highest score first)?
    d  owner's planner     the planner's estimates of what 8 more call slots a day (one more counsellor) and a 20%
                           larger discount budget would add, against what they truly add in the same simulated days

Every rule sees the same learners in the same order with the same predictions, and is scored with the simulator's
true probabilities as expected profit (no outcome noise), so differences are not luck of the draw. Values are in INR.

Output: ml/results/money_check.{json,md} and figures/money_budget_share.png.
Run: python ml/experiments/money_check.py [quick | report]   (report: rebuild the report from the saved results)
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
from app.ml import budget as BG  # noqa: E402
from app.ml import capacity  # noqa: E402
from app.ml import features as F  # noqa: E402
from app.ml import lead_model as LM  # noqa: E402
from app.ml import nba_core as N  # noqa: E402
from app.services.planner import slots_value  # noqa: E402
from app.simulation import effects as S  # noqa: E402
from app.simulation import population as G  # noqa: E402

RESULTS = ROOT / "ml" / "results"
QUICK = len(sys.argv) > 1 and sys.argv[1] == "quick"
SEEDS = 3 if QUICK else 10
POOL = 60_000 if QUICK else 150_000
POOLS = 1 if QUICK else 2
WARMUP = 7  # the prices need a week of decisions first
MONTH = 30
MONTHS = 2
PER_DAY = 300  # automatic decisions a day (a weekday; weekends are quieter)
BUDGETS = [0.1, 0.25, 0.5, 1.0]  # monthly budget as a share of what every coupon that pays would cost
MORE_BUDGET = 0.2  # the planner's question: what would 20% more budget add?
CALLS_NOW, MORE_CALLS = 8, 8  # one counsellor's calls a day, and one more counsellor
CALL_DEMAND = [1, 2, 4, 8]  # call-worthy decisions a day, as a multiple of today's call slots
OPEN_LEADS = 1200  # a pipeline snapshot
SNAPSHOTS = 40 if QUICK else 200
WORK_SHARES = [0.05, 0.10, 0.20, 0.40]  # share of the open leads the team has time to work
GUARD_LEADS = 20_000 if QUICK else 60_000

A = N.ACTION_LIST
IDX = {a: i for i, a in enumerate(A)}
CALL = IDX["call"]
C10, C20 = IDX["email_coupon_10"], IDX["email_coupon_20"]
COUPON_IDX = (C10, C20)
DISC = np.array([N.ACTIONS[a]["discount"] for a in A])
# steps that need neither a coupon nor a call (doing nothing included)
PLAIN = [i for i in range(len(A)) if i not in (CALL, C10, C20)]
NONCALL = [i for i in range(len(A)) if i != CALL]
# when decisions arrive during the day (share per hour, 0-23), as in E7: evenings are busiest
HOURLY = np.array(
    [0.2, 0.1, 0.05, 0.05, 0.05, 0.1, 0.3, 0.6, 1.0, 1.2, 1.3, 1.3, 1.2, 1.2, 1.3, 1.4, 1.5, 1.7, 2.0, 2.4, 2.6]
    + [2.4, 1.6, 0.8]
)
HOURLY = HOURLY / HOURLY.sum()


def logit(p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def build_pool(seed: int) -> dict:
    """Learners at a decision, with the predicted and the true chance to buy under every step."""
    d = get_settings().model_dir
    lead = joblib.load(d / "lead_model.starter.pkl")
    nba = joblib.load(d / "nba_model.starter.pkl")
    raw = G.generate(POOL, seed=seed, return_truth=True)
    frame = F.to_model_frame(raw)
    base = LM.predict_proba(lead, frame)
    pred = N.predict_actions(nba["model"], frame, base)
    shift = logit(base) - logit(pred["none"])  # anchored on the lead score, as in production
    pp = np.column_stack([1 / (1 + np.exp(-(logit(pred[a]) + shift))) for a in A])
    truth = S.true_probabilities(frame, raw["_p_true"].to_numpy(), seed=seed + 1)
    pt = np.column_stack([truth[a] for a in A])
    price = S.prices_for(frame)
    blocked = S.blocked_matrix(frame)
    B = np.column_stack([blocked[a] for a in A])
    B[:, 0] = False  # doing nothing is always possible
    cost = np.array([N.ACTIONS[a]["cost_inr"] for a in A])

    def values(p):  # incremental profit of every step against doing nothing (the discount is counted)
        v = p * price[:, None] * (1 - DISC[None, :]) - cost[None, :] - (p[:, 0] * price)[:, None]
        v[B] = -np.inf
        v[:, 0] = 0.0
        return v

    return {
        "pp": pp,
        "pt": pt,
        "price": price,
        "blocked": B,
        "vp": values(pp),
        "vt": values(pt),
        "cart": (frame["AddedToCart"].to_numpy() == 1),
    }


def se(x) -> float:
    x = np.asarray(x, dtype=float)
    return float(np.std(x, ddof=1) / np.sqrt(len(x))) if len(x) > 1 else 0.0


def arrivals(rng, rate: float, n_pool: int):
    """One day's decisions: pool rows and times of day (0-1), in time order."""
    n = int(rng.poisson(rate))
    rows = rng.integers(0, n_pool, n)
    t = (rng.choice(24, size=n, p=HOURLY) + rng.random(n)) / 24.0
    order = np.argsort(t)
    return rows[order], t[order]


def day_factor(rng, day: int) -> float:
    return (0.7 if day % 7 in (5, 6) else 1.0) * float(rng.lognormal(0, 0.15))


# a: the discount budget
BUDGET_RULES = [
    "no coupons",
    "cart recovery",
    "first come",
    "fixed price",
    "re-solved price",
    "hindsight",
    "true hindsight",
]


def coupon_terms(pool: dict) -> dict:
    """Per learner: the best step with neither coupon nor call, and both coupons' profit and expected discount (calls
    are left out here: E7 prices them; with a few calls a day nearly every decision is made without one)."""
    vp, pp, pt, price = pool["vp"], pool["pp"], pool["pt"], pool["price"]
    alt = np.array(PLAIN)[vp[:, PLAIN].argmax(axis=1)]
    r = np.arange(len(vp))
    alt_v = vp[r, alt]
    ok = np.isfinite(vp[:, C10]) & np.isfinite(vp[:, C20])
    best = np.where(vp[:, C20] > vp[:, C10], C20, C10)
    cost = {c: pp[:, c] * price * DISC[c] for c in COUPON_IDX}  # predicted expected discount
    tcost = {c: pt[:, c] * price * DISC[c] for c in COUPON_IDX}  # true expected discount
    log_v = np.where(ok, vp[r, best] - alt_v, np.nan)  # what the production log stores (coupon_value)
    log_c = np.where(ok, np.where(best == C20, cost[C20], cost[C10]), np.nan)  # (coupon_cost)
    return {
        "alt": alt,
        "alt_v": alt_v,
        "ok": ok,
        "best": best,
        "cost": cost,
        "tcost": tcost,
        "log_v": log_v,
        "log_c": log_c,
    }


def pick(i: int, lam: float, T: dict, vp) -> int:
    """The production choice for one learner at a price of a rupee of discount (N.choose with calls left out)."""
    a, best_net = int(T["alt"][i]), float(T["alt_v"][i])
    if not T["ok"][i] or not np.isfinite(lam):
        return a
    for c in COUPON_IDX:
        net = float(vp[i, c]) - lam * float(T["cost"][c][i])
        if net > best_net:
            a, best_net = c, net
    return a


def hindsight(alt: np.ndarray, gain: dict, cost: dict, budget: float) -> np.ndarray:
    """The month's choices at the best single price with perfect foresight: the smallest price per rupee of discount
    at which the month's coupons fit the budget (found by bisection; the Lagrangian solution of the month's
    multiple-choice knapsack, so the best any rule could do with these effects and costs, up to one coupon)."""
    ok = np.isfinite(gain[C10]) & np.isfinite(gain[C20])

    def choose(lam: float):
        n10 = np.where(ok, gain[C10] - lam * cost[C10], -np.inf)
        n20 = np.where(ok, gain[C20] - lam * cost[C20], -np.inf)
        pick = np.where(np.maximum(n10, n20) > 0, np.where(n20 > n10, C20, C10), alt)
        spent = np.where(pick == C10, cost[C10], 0.0).sum() + np.where(pick == C20, cost[C20], 0.0).sum()
        return pick, spent

    pick, spent = choose(0.0)
    if spent <= budget:
        return pick
    lo, hi = 0.0, 1.0
    while choose(hi)[1] > budget:
        lo, hi = hi, hi * 2
    for _ in range(50):
        mid = (lo + hi) / 2
        if choose(mid)[1] > budget:
            lo = mid
        else:
            hi = mid
    return choose(hi)[0]


def simulate_budget(seed: int, pool: dict, T: dict, budgets: dict) -> dict:
    """Two months of decisions; every rule spends the same monthly budget. budgets: label -> rupees a month."""
    vp, vt, pt, price = pool["vp"], pool["vt"], pool["pt"], pool["price"]
    rng = np.random.default_rng(seed)
    hist: list[tuple[int, float, float]] = []  # (day, coupon_value, coupon_cost), as nba_decisions logs them
    out = {lab: {r: [] for r in BUDGET_RULES} for lab in budgets}
    planner = {lab: [] for lab in budgets}  # (estimate, truth) of what 20% more budget adds in a month
    for month in range(-1, MONTHS):  # month -1: the warm-up week only
        days = range(MONTH - WARMUP, MONTH) if month < 0 else range(MONTH)
        month_rows, month_tods = [], []
        sequential = {lab: {} for lab in budgets}
        left = {  # money left this month for every sequential rule ('more budget': the planner's 20% more)
            lab: {
                **{r: b for r in ("cart recovery", "first come", "fixed price", "re-solved price")},
                "more budget": b * (1 + MORE_BUDGET),
            }
            for lab, b in budgets.items()
        }
        fixed, est_more = {}, {}
        for day in days:
            g = (month + 1) * MONTH + day
            rows, tod = arrivals(rng, PER_DAY * day_factor(rng, g), len(vp))
            win = [h for h in hist if h[0] >= g - BG.CONF["lookback_days"]]
            pricer = BG.BudgetPricer([h[1] for h in win], [h[2] for h in win], len({h[0] for h in win}))
            if month >= 0:
                for lab, b in budgets.items():
                    if day == 0:
                        fixed[lab] = pricer.price(b, MONTH)
                        _, now_v = pricer.month_value(b, MONTH)
                        _, more_v = pricer.month_value(b * (1 + MORE_BUDGET), MONTH)
                        est_more[lab] = more_v - now_v
                    L = left[lab]
                    ch = sequential[lab]
                    for name in ("cart recovery", "first come", "fixed price", "re-solved price", "more budget"):
                        ch.setdefault(name, [])
                    for i, t in zip(rows, tod):
                        days_left = MONTH - day - t
                        # the usual cart-recovery rule: 10% to every left cart while money is left
                        a = int(T["alt"][i])
                        if pool["cart"][i] and T["ok"][i] and L["cart recovery"] > 0:
                            a = C10
                            L["cart recovery"] -= T["cost"][C10][i]
                        ch["cart recovery"].append(a)
                        # first come, first served: the model's best step while money is left
                        a = pick(i, 0.0 if L["first come"] > 0 else np.inf, T, vp)
                        if a in COUPON_IDX:
                            L["first come"] -= T["cost"][a][i]
                        ch["first come"].append(a)
                        # one price for the whole month, from the week before it started
                        a = pick(i, fixed[lab] if L["fixed price"] > 0 else np.inf, T, vp)
                        if a in COUPON_IDX:
                            L["fixed price"] -= T["cost"][a][i]
                        ch["fixed price"].append(a)
                        # ours: the price worked out again at every decision (production BudgetPricer)
                        for name in ("re-solved price", "more budget"):
                            lam = pricer.price(L[name], days_left)
                            a = pick(i, lam, T, vp)
                            if a in COUPON_IDX:
                                L[name] -= T["cost"][a][i]
                            ch[name].append(a)
                month_rows.append(rows)
                month_tods.append(tod)
            hist += [(g, float(v), float(c)) for v, c in zip(T["log_v"][rows], T["log_c"][rows]) if np.isfinite(v)]
        if month < 0:
            continue
        rows = np.concatenate(month_rows)
        alt = T["alt"][rows]
        for lab, b in budgets.items():
            chosen = {"no coupons": alt.copy()}
            for name in ("cart recovery", "first come", "fixed price", "re-solved price", "more budget"):
                chosen[name] = np.array(sequential[lab][name])
            # hindsight: the best single price for the whole month, known in advance (each learner then gets the
            # step with the most profit net of the price, 10% or 20% coupon or none), with the predicted or the true
            # effects and costs
            r = rows
            pred_gain = {c: vp[r, c] - vp[r, alt] for c in COUPON_IDX}
            pred_cost = {c: T["cost"][c][r] for c in COUPON_IDX}
            true_gain = {c: vt[r, c] - vt[r, alt] for c in COUPON_IDX}
            true_cost = {c: T["tcost"][c][r] for c in COUPON_IDX}
            chosen["hindsight"] = hindsight(alt, pred_gain, pred_cost, b)
            chosen["true hindsight"] = hindsight(alt, true_gain, true_cost, b)
            recs = {}
            for name, ch in chosen.items():
                is_c = np.isin(ch, COUPON_IDX)
                recs[name] = {
                    "profit": float(vt[rows, ch].sum()),
                    "coupons": int(is_c.sum()),
                    # true expected discount given, and the part of it that goes to people who would have bought
                    # anyway (they use the coupon too)
                    "true_discount": float(np.where(is_c, pt[rows, ch] * price[rows] * DISC[ch], 0.0).sum()),
                    "to_buyers_anyway": float(np.where(is_c, pt[rows, 0] * price[rows] * DISC[ch], 0.0).sum()),
                }
            for name in BUDGET_RULES:
                out[lab][name].append(recs[name])
            # the planner: its estimate (from the week before the month) against the true difference in the month
            planner[lab].append((est_more[lab], recs["more budget"]["profit"] - recs["re-solved price"]["profit"]))
    return {"rules": out, "planner": planner, "decisions": len(hist)}


def run_budget(pools) -> dict:
    T = [coupon_terms(p) for p in pools]
    # what every coupon that pays would cost in a month (predicted), at the average number of decisions a day
    t0 = T[0]
    paying = np.nan_to_num(np.where(t0["log_v"] > 0, t0["log_c"], 0.0))
    per_day = PER_DAY * (5 + 2 * 0.7) / 7 * float(np.exp(0.15**2 / 2))
    natural = float(paying.mean() * per_day * MONTH)
    budgets = {f"{int(f * 100)}%": f * natural for f in BUDGETS}
    runs = [simulate_budget(2000 + s, pools[s % len(pools)], T[s % len(pools)], budgets) for s in range(SEEDS)]
    out = {"natural_month": round(natural), "budgets": {k: round(v) for k, v in budgets.items()}, "levels": []}
    for lab, b in budgets.items():
        per = {}
        floor = np.array([m["profit"] for r in runs for m in r["rules"][lab]["no coupons"]])
        ceil = np.array([m["profit"] for r in runs for m in r["rules"][lab]["hindsight"]])
        fcfs = np.array([m["profit"] for r in runs for m in r["rules"][lab]["first come"]])
        for name in BUDGET_RULES:
            ms = [m for r in runs for m in r["rules"][lab][name]]
            v = np.array([m["profit"] for m in ms])
            share = (v - floor) / np.maximum(ceil - floor, 1e-9)
            per[name] = {
                "profit_month": round(float(v.mean())),
                "added_month": round(float((v - floor).mean())),
                "share_of_hindsight": round(float(share.mean()), 3),
                "share_ci95": round(1.96 * se(share), 3),
                "vs_first_come_month": round(float((v - fcfs).mean())),
                "vs_first_come_ci95": round(1.96 * se(v - fcfs)),
                "coupons_month": round(float(np.mean([m["coupons"] for m in ms]))),
                "true_discount_month": round(float(np.mean([m["true_discount"] for m in ms]))),
                "budget_used": round(float(np.mean([m["true_discount"] for m in ms])) / b, 3),
                "budget_used_max": round(float(np.max([m["true_discount"] for m in ms])) / b, 3),
                "to_buyers_anyway_month": round(float(np.mean([m["to_buyers_anyway"] for m in ms]))),
            }
        est = np.array([e for r in runs for e, _ in r["planner"][lab]])
        tru = np.array([t for r in runs for _, t in r["planner"][lab]])
        out["levels"].append(
            {
                "label": lab,
                "budget": round(b),
                "rules": per,
                "planner_more_budget": {
                    "extra": round(b * MORE_BUDGET),
                    "estimate": round(float(est.mean())),
                    "estimate_ci95": round(1.96 * se(est)),
                    "true": round(float(tru.mean())),
                    "true_ci95": round(1.96 * se(tru)),
                },
            }
        )
    return out


# b: the coupon guard
def run_guard(pools) -> dict:
    pool = pools[0]
    rng = np.random.default_rng(5)
    pp, pt, price = pool["pp"], pool["pt"], pool["price"]
    rows = rng.choice(len(pp), size=min(GUARD_LEADS, len(pp)), replace=False)
    rows = rows[~pool["blocked"][rows, C10]]  # people who can get a coupon email
    score = pp[rows, 0]
    who = {
        "the warmest leads (top 10% by score)": rows[score >= np.quantile(score, 0.9)],
        "every left cart": rows[pool["cart"][rows]],
        "anyone (10% at random)": rng.choice(rows, size=len(rows) // 10, replace=False),
    }
    out = []
    for label, r in who.items():
        for c in COUPON_IDX:
            d = DISC[c]
            pred = pp[r, c] * price[r] * (1 - d) - pp[r, 0] * price[r]  # the guard's extra profit (production)
            true = pt[r, c] * price[r] * (1 - d) - pt[r, 0] * price[r]
            stop = pred <= 0
            loses = true <= 0
            n = len(r)
            out.append(
                {
                    "who": label,
                    "discount": int(round(d * 100)),
                    "coupons": n,
                    "stopped": round(float(stop.mean()), 3),
                    "truly_lose_money": round(float(loses.mean()), 3),
                    "precision": round(float((stop & loses).sum() / max(stop.sum(), 1)), 3),
                    "recall": round(float((stop & loses).sum() / max(loses.sum(), 1)), 3),
                    "profit_per_100_all": round(float(true.sum() / n * 100)),
                    "profit_per_100_guarded": round(float(true[~stop].sum() / n * 100)),
                    "saved_per_100": round(float(-true[stop].sum() / n * 100)),
                    "anyway_discount_avoided_per_100": round(float((pt[r, 0] * price[r] * d)[stop].sum() / n * 100)),
                }
            )
    return {"rows": out}


# c: the pipeline in rupees
def run_pipeline(pools) -> dict:
    pool = pools[0]
    rng = np.random.default_rng(6)
    vp, vt, pp, pt, price = pool["vp"], pool["vt"], pool["pp"], pool["pt"], pool["price"]
    best = vp.argmax(axis=1)  # the model's best step for every lead (no prices: the team's own choice of who)
    r_all = np.arange(len(vp))
    add_p = vp[r_all, best]
    add_t = vt[r_all, best]
    anyway_p, anyway_t = pp[:, 0] * price, pt[:, 0] * price
    sums = {"anyway_pred": [], "anyway_true": [], "add_pred": [], "add_true": []}
    work = {s: {"score": [], "money": [], "random": [], "oracle": []} for s in WORK_SHARES}
    for _ in range(SNAPSHOTS):
        r = rng.choice(len(vp), size=OPEN_LEADS, replace=False)
        sums["anyway_pred"].append(anyway_p[r].sum())
        sums["anyway_true"].append(anyway_t[r].sum())
        sums["add_pred"].append(add_p[r].sum())
        sums["add_true"].append(add_t[r].sum())
        orders = {
            "score": np.argsort(-pp[r, 0], kind="stable"),
            "money": np.argsort(-add_p[r], kind="stable"),
            "random": rng.permutation(len(r)),
            "oracle": np.argsort(-add_t[r], kind="stable"),
        }
        for s in WORK_SHARES:
            k = int(round(s * len(r)))
            for name, o in orders.items():
                work[s][name].append(float(add_t[r][o[:k]].sum()))
    # calibration by score band (fifths of the lead score)
    bands = []
    q = np.quantile(pp[:, 0], [0, 0.2, 0.4, 0.6, 0.8, 1.0])
    for lo, hi in zip(q[:-1], q[1:]):
        m = (pp[:, 0] >= lo) & (pp[:, 0] <= hi)
        bands.append(
            {
                "score_from": round(float(lo), 3),
                "score_to": round(float(hi), 3),
                "anyway_pred_over_true": round(float(anyway_p[m].sum() / anyway_t[m].sum()), 3),
                "add_pred": round(float(add_p[m].mean())),
                "add_true": round(float(add_t[m].mean())),
            }
        )

    # the 'no discount needed' badge: more likely than not to buy anyway, and no coupon would add profit (the
    # production rule, app.services.money); judged on leads who can get email (a coupon cannot reach the others)
    def coupon_gain(p):  # the better coupon's extra profit against doing nothing (the email's cost included)
        return np.maximum.reduce(
            [p[:, c] * price * (1 - DISC[c]) - N.ACTIONS[A[c]]["cost_inr"] - p[:, 0] * price for c in COUPON_IDX]
        )

    gain_p, gain_t = coupon_gain(pp), coupon_gain(pt)
    can_email = ~pool["blocked"][:, C10]
    likely = (pp[:, 0] >= 0.5) & can_email
    f = likely & (gain_p <= 0)
    work_out = []
    for s in WORK_SHARES:
        w = {k: np.array(v) for k, v in work[s].items()}
        diff = w["money"] - w["score"]
        work_out.append(
            {
                "share_worked": s,
                "leads_worked": int(round(s * OPEN_LEADS)),
                **{f"{k}_added": round(float(v.mean())) for k, v in w.items()},
                **{f"{k}_share_of_oracle": round(float((v / w["oracle"]).mean()), 3) for k, v in w.items()},
                "money_minus_score": round(float(diff.mean())),
                "money_minus_score_ci95": round(1.96 * se(diff)),
            }
        )
    tot = {k: np.array(v) for k, v in sums.items()}
    return {
        "snapshots": SNAPSHOTS,
        "open_leads": OPEN_LEADS,
        "anyway_pred": round(float(tot["anyway_pred"].mean())),
        "anyway_true": round(float(tot["anyway_true"].mean())),
        "anyway_ratio": round(float((tot["anyway_pred"] / tot["anyway_true"]).mean()), 3),
        "add_pred": round(float(tot["add_pred"].mean())),
        "add_true": round(float(tot["add_true"].mean())),
        "add_ratio": round(float((tot["add_pred"] / tot["add_true"]).mean()), 3),
        "bands": bands,
        "work": work_out,
        "no_discount_badge": {
            "share_flagged": round(float(f.sum() / can_email.sum()), 4),
            "coupon_truly_loses": round(float((gain_t[f] <= 0).mean()), 3),
            "coupon_loss_per_lead": round(float(-gain_t[f].mean())),
            "likely_buyers_share": round(float(likely.sum() / can_email.sum()), 4),
            "likely_buyers_coupon_truly_loses": round(float((gain_t[likely] <= 0).mean()), 3),
            "others_coupon_truly_loses": round(float((gain_t[can_email & ~f] <= 0).mean()), 3),
        },
    }


# d: the owner's planner, one more counsellor
def ranked(pricer, slots_now: int, extra: int) -> float:
    """The simpler estimate the planner does not use: on each day of the window, the calls ranked slots_now+1 to
    slots_now+extra by predicted advantage (as if the extra slots took exactly those calls), per day."""
    by_day: dict = {}
    for a, d in zip(pricer.advantages, pricer.day_of):
        if a > 0:
            by_day.setdefault(d, []).append(a)
    total = sum(sum(sorted(v, reverse=True)[slots_now : slots_now + extra]) for v in by_day.values())
    return total / pricer.days if pricer.days else 0.0


def run_counsellor(pools) -> dict:
    out = []
    for demand in CALL_DEMAND:
        est_more, true_more, est_now, true_now, rank_more = [], [], [], [], []
        for s in range(SEEDS):
            pool = pools[s % len(pools)]
            vp, vt = pool["vp"], pool["vt"]
            adv_p = vp[:, CALL] - vp[:, NONCALL].max(axis=1)
            alt = np.array(NONCALL)[vp[:, NONCALL].argmax(axis=1)]
            worthy = float(np.mean(adv_p > 0))
            rate = demand * CALLS_NOW / max(worthy, 1e-6)
            rng = np.random.default_rng(3000 + s)
            hist = []
            day_est_more, day_true_more, day_est_now, day_true_now, day_rank_more = [], [], [], [], []
            for day in range(WARMUP + MONTH):
                rows, tod = arrivals(rng, rate * day_factor(rng, day), len(vp))
                win = [h for h in hist if h[0] >= day - capacity.CONF["lookback_days"]]
                pricers = {
                    cap: capacity.SlotPricer(
                        [h[2] for h in win],
                        [h[1] for h in win],
                        len({h[0] for h in win}),
                        cap,
                        day_of=[h[0] for h in win],
                    )
                    for cap in (CALLS_NOW, CALLS_NOW + MORE_CALLS)
                }
                if day >= WARMUP:
                    profit = {}
                    for cap in (0, CALLS_NOW, CALLS_NOW + MORE_CALLS):
                        used, total = 0, 0.0
                        for i, t in zip(rows, tod):
                            a = alt[i]
                            worth = cap and np.isfinite(adv_p[i]) and used < cap
                            if worth and adv_p[i] > max(pricers[cap].price(cap - used, float(t)), 0.0):
                                a, used = CALL, used + 1
                            total += vt[i, a]
                        profit[cap] = total
                    p8 = pricers[CALLS_NOW]
                    day_est_now.append(slots_value(p8, 0, CALLS_NOW))
                    day_est_more.append(slots_value(p8, CALLS_NOW, MORE_CALLS))
                    day_rank_more.append(ranked(p8, CALLS_NOW, MORE_CALLS))
                    day_true_now.append(profit[CALLS_NOW] - profit[0])
                    day_true_more.append(profit[CALLS_NOW + MORE_CALLS] - profit[CALLS_NOW])
                hist += [(day, float(t), float(a)) for t, a in zip(tod, adv_p[rows]) if np.isfinite(a)]
            est_more.append(np.mean(day_est_more) * MONTH)
            true_more.append(np.mean(day_true_more) * MONTH)
            est_now.append(np.mean(day_est_now) * MONTH)
            true_now.append(np.mean(day_true_now) * MONTH)
            rank_more.append(np.mean(day_rank_more) * MONTH)
        em, tm, en, tn, rm = map(np.array, (est_more, true_more, est_now, true_now, rank_more))
        out.append(
            {
                "demand": demand,
                "now_estimate": round(float(en.mean())),
                "now_true": round(float(tn.mean())),
                "now_ratio": round(float((en / tn).mean()), 3),
                "now_ratio_ci95": round(1.96 * se(en / tn), 3),
                "more_estimate": round(float(em.mean())),
                "more_true": round(float(tm.mean())),
                "more_ratio": round(float((em / np.maximum(tm, 1e-9)).mean()), 3) if tm.mean() > 0 else None,
                "more_ratio_ci95": round(1.96 * se(em / np.maximum(tm, 1e-9)), 3) if tm.mean() > 0 else None,
                "ranked_estimate": round(float(rm.mean())),
                "ranked_ratio": round(float((rm / np.maximum(tm, 1e-9)).mean()), 3) if tm.mean() > 0 else None,
            }
        )
        print(
            f"  calls {demand}x: 8 slots est {en.mean():,.0f} true {tn.mean():,.0f}; "
            f"+8 est {em.mean():,.0f} true {tm.mean():,.0f} a month",
            flush=True,
        )
    return {"calls_now": CALLS_NOW, "more_calls": MORE_CALLS, "levels": out}


def main():
    t0 = time.time()
    print(f"E9 money features: {SEEDS} seeds, pools of {POOL:,} simulated learners", flush=True)
    pools = [build_pool(91 + k) for k in range(POOLS)]
    results = {
        "settings": {
            "seeds": SEEDS,
            "pool": POOL,
            "pools": POOLS,
            "decisions_per_day": PER_DAY,
            "months": MONTHS,
            "warmup_days": WARMUP,
            "lookback_days": BG.CONF["lookback_days"],
            "open_leads": OPEN_LEADS,
            "snapshots": SNAPSHOTS,
            "models": "starting models (lead_model.starter.pkl, nba_model.starter.pkl)",
        }
    }
    print("  a: discount budget", flush=True)
    results["budget"] = run_budget(pools)
    for lv in results["budget"]["levels"]:
        r = lv["rules"]
        print(
            f"    budget {lv['label']:>4} of the natural month: first come {r['first come']['share_of_hindsight']:.0%}, "
            f"cart recovery {r['cart recovery']['share_of_hindsight']:.0%}, fixed {r['fixed price']['share_of_hindsight']:.0%}, "
            f"re-solved {r['re-solved price']['share_of_hindsight']:.0%}",
            flush=True,
        )
    print("  b: coupon guard", flush=True)
    results["guard"] = run_guard(pools)
    print("  c: pipeline in rupees", flush=True)
    results["pipeline"] = run_pipeline(pools)
    print("  d: one more counsellor", flush=True)
    results["counsellor"] = run_counsellor(pools)
    results["seconds"] = round(time.time() - t0, 1)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "money_check.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    write_report(results)


RULES = {
    "no coupons": "no coupon is ever given (what the other steps earn on their own)",
    "cart recovery": "the usual rule: a 10% coupon to every left cart while money is left; everyone else gets the "
    "model's best step without a coupon",
    "first come": "the model's best step for each learner, coupons included, until the money is used up",
    "fixed price": "a coupon only when it adds more than one price per rupee of discount, the same all month (from "
    "the week before the month)",
    "re-solved price": "ours (production app.ml.budget): the price is worked out again at every decision from the "
    "money left, the days left and the last 7 days of decisions",
    "hindsight": "the best single price for the month, chosen knowing the whole month's decisions in advance (the "
    "best any rule could do with the same predictions)",
    "true hindsight": "the same with the true effects and costs (the ceiling, with perfect prediction too)",
}


def inr(x) -> str:
    return f"{x:,.0f}"


def write_report(res: dict) -> None:
    st = res["settings"]
    b = res["budget"]
    lines = [
        "# E9: the money features against known truth",
        "",
        f"Simulated learners whose true response to every step is known, the production code and the {st['models']}. "
        "Every rule sees the same learners in the same order with the same predictions and is scored with the true "
        "probabilities as expected profit (no outcome noise). INR throughout.",
        "",
        "## a. A monthly discount budget",
        "",
        f"{st['seeds']} runs of {st['months']} months ({st['decisions_per_day']} automatic decisions a weekday, fewer at "
        f"weekends; the first {st['warmup_days']} days only build the price). If every coupon that pays were sent, "
        f"a month of coupons would cost about {inr(b['natural_month'])} of expected discount; the budgets below are "
        "shares of that. Calls are left out here (E7 prices them). 'Share' is the part of the value of the budget "
        "that each rule captures, between no coupons (0%) and the best allocation with hindsight (100%), with a 95% "
        "interval across months and runs. 'Budget used' is the true expected discount given, as a share of the "
        "budget (the rules count the predicted cost when a coupon goes out, as the CRM does for open coupons).",
        "",
        "Rules compared:",
        "",
    ]
    lines += [f"- **{k}**: {v}" for k, v in RULES.items()]
    lines += [
        "",
        "| Budget | First come | Cart recovery | Fixed price | Re-solved price (ours) | Ours against first come, a month |",
        "|---|---|---|---|---|---|",
    ]
    for lv in b["levels"]:
        r = lv["rules"]
        lines.append(
            f"| {lv['label']} ({inr(lv['budget'])}) | {r['first come']['share_of_hindsight'] * 100:.1f}% | "
            f"{r['cart recovery']['share_of_hindsight'] * 100:.1f}% | {r['fixed price']['share_of_hindsight'] * 100:.1f}% | "
            f"{r['re-solved price']['share_of_hindsight'] * 100:.1f}% | "
            f"{r['re-solved price']['vs_first_come_month']:+,} (+/- {r['re-solved price']['vs_first_come_ci95']:,}) |"
        )
    for lv in b["levels"]:
        lines += [
            "",
            f"### Budget {lv['label']} of the natural month ({inr(lv['budget'])} a month)",
            "",
            "| Rule | Profit added a month | Share of hindsight | Coupons a month | Budget used (mean, max) | "
            "Discount to people who would have bought anyway |",
            "|---|---|---|---|---|---|",
        ]
        for name, r in lv["rules"].items():
            lines.append(
                f"| {name} | {inr(r['added_month'])} | {r['share_of_hindsight'] * 100:.1f}% (+/- "
                f"{r['share_ci95'] * 100:.1f}) | {inr(r['coupons_month'])} | {r['budget_used'] * 100:.0f}%, "
                f"{r['budget_used_max'] * 100:.0f}% | {inr(r['to_buyers_anyway_month'])} |"
            )
    g = res["guard"]["rows"]
    lines += [
        "",
        "## b. The coupon guard",
        "",
        "Coupons a counsellor might give by hand. The guard stops a coupon when its predicted extra profit (chance to "
        "buy with it x fee x (1 - discount) - chance without it x fee) is not positive. 'Precision': of the stopped "
        "coupons, the share that truly lose money; 'recall': of the coupons that truly lose money, the share stopped. "
        "Profit is per 100 coupons the counsellor wanted to give.",
        "",
        "| Coupons for | Discount | Stopped | Truly lose money | Precision | Recall | Profit, all given | "
        "Profit, guard on | Saved | Discount to buyers anyway avoided |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in g:
        lines.append(
            f"| {r['who']} | {r['discount']}% | {r['stopped'] * 100:.0f}% | {r['truly_lose_money'] * 100:.0f}% | "
            f"{r['precision'] * 100:.0f}% | {r['recall'] * 100:.0f}% | {inr(r['profit_per_100_all'])} | "
            f"{inr(r['profit_per_100_guarded'])} | {inr(r['saved_per_100'])} | "
            f"{inr(r['anyway_discount_avoided_per_100'])} |"
        )
    p = res["pipeline"]
    lines += [
        "",
        "## c. The pipeline in rupees",
        "",
        f"{p['snapshots']} snapshots of {p['open_leads']:,} open leads. 'Comes in anyway' is the sum of each lead's "
        "chance to buy with no contact x fee; 'the team can add' is the sum of the best step's extra profit.",
        "",
        "| | Predicted | True | Predicted / true |",
        "|---|---|---|---|",
        f"| Comes in anyway | {inr(p['anyway_pred'])} | {inr(p['anyway_true'])} | {p['anyway_ratio']:.3f} |",
        f"| The team can add (best step for every lead) | {inr(p['add_pred'])} | {inr(p['add_true'])} | "
        f"{p['add_ratio']:.3f} |",
        "",
        "By fifths of the lead score:",
        "",
        "| Lead score | Anyway, predicted / true | Can add per lead, predicted | Can add per lead, true |",
        "|---|---|---|---|",
    ]
    for bd in p["bands"]:
        lines.append(
            f"| {bd['score_from']:.3f} to {bd['score_to']:.3f} | {bd['anyway_pred_over_true']:.3f} | "
            f"{inr(bd['add_pred'])} | {inr(bd['add_true'])} |"
        )
    lines += [
        "",
        "When the team has time for only some of the open leads, each worked with the model's best step: the true "
        "profit added when they are worked in the usual order (highest score first), in money order (most to add "
        "first, the pipeline's default), at random, and with perfect knowledge (the ceiling).",
        "",
        "| Leads worked | Highest score first | Most to add first (ours) | Random | Perfect knowledge | "
        "Ours against highest score |",
        "|---|---|---|---|---|---|",
    ]
    for w in p["work"]:
        lines.append(
            f"| {w['leads_worked']:,} ({w['share_worked'] * 100:.0f}%) | {inr(w['score_added'])} "
            f"({w['score_share_of_oracle'] * 100:.0f}%) | {inr(w['money_added'])} ({w['money_share_of_oracle'] * 100:.0f}%) "
            f"| {inr(w['random_added'])} ({w['random_share_of_oracle'] * 100:.0f}%) | {inr(w['oracle_added'])} | "
            f"{w['money_minus_score']:+,} (+/- {w['money_minus_score_ci95']:,}) |"
        )
    nd = p["no_discount_badge"]
    lines += [
        "",
        f"'No discount needed' (more likely than not to buy anyway, and no coupon would add profit by the model: "
        f"{nd['share_flagged'] * 100:.1f}% of the leads who can get email): for {nd['coupon_truly_loses'] * 100:.0f}% "
        f"of them even the better coupon truly loses money (on average {inr(nd['coupon_loss_per_lead'])} a lead). "
        f"Being likely to buy anyway is not enough on its own: for all such leads "
        f"({nd['likely_buyers_share'] * 100:.1f}%) the share is {nd['likely_buyers_coupon_truly_loses'] * 100:.0f}%; "
        f"for every other lead it is {nd['others_coupon_truly_loses'] * 100:.0f}%.",
        "",
        "## d. The owner's planner",
        "",
        f"What one more counsellor ({res['counsellor']['more_calls']} more call slots a day on top of "
        f"{res['counsellor']['calls_now']}) would add in a month: the planner's estimate (from the last 7 days of "
        "predicted call advantages, production app.services.planner.slots_value) against the true extra profit of "
        "the same days run with the extra slots (re-solved slot price, E7). The planner replays last week's decisions "
        "with the CRM's own rule; 'ranked' is the simpler estimate it does not use (each day's calls ranked 9 to 16 by "
        "predicted advantage), which misses that with more slots the rule holds back fewer calls for later in the "
        "day. Demand is the number of call-worthy decisions a day as a multiple of today's slots.",
        "",
        "| Demand | Today's slots: estimate | true | estimate / true | One more counsellor: estimate | true | "
        "estimate / true | ranked / true |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for lv in res["counsellor"]["levels"]:
        mr = "n/a" if lv["more_ratio"] is None else f"{lv['more_ratio']:.2f} (+/- {lv['more_ratio_ci95']:.2f})"
        rr = "n/a" if lv.get("ranked_ratio") is None else f"{lv['ranked_ratio']:.2f}"
        lines.append(
            f"| {lv['demand']}x | {inr(lv['now_estimate'])} | {inr(lv['now_true'])} | {lv['now_ratio']:.2f} (+/- "
            f"{lv['now_ratio_ci95']:.2f}) | {inr(lv['more_estimate'])} | {inr(lv['more_true'])} | {mr} | {rr} |"
        )
    lines += [
        "",
        f"What {int(MORE_BUDGET * 100)}% more discount budget would add in a month: the planner's estimate (from the "
        "week before the month, production BudgetPricer.month_value) against the true difference between the "
        "month run with the larger budget and with the budget as it is.",
        "",
        "| Budget | Extra money | Estimate | True |",
        "|---|---|---|---|",
    ]
    for lv in b["levels"]:
        m = lv["planner_more_budget"]
        lines.append(
            f"| {lv['label']} ({inr(lv['budget'])}) | {inr(m['extra'])} | {inr(m['estimate'])} (+/- "
            f"{inr(m['estimate_ci95'])}) | {inr(m['true'])} (+/- {inr(m['true_ci95'])}) |"
        )
    lines.append("")
    (RESULTS / "money_check.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved ml/results/money_check.md ({res.get('seconds', 0)} s)")
    figure(res)


def figure(res: dict) -> None:
    """Share of the hindsight value of the budget, by budget (ml/results/figures/money_budget_share.png)."""
    try:
        import matplotlib
        import matplotlib.ticker

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("  (matplotlib is not installed, so no figure: pip install -r ml/requirements.txt)")
        return
    levels = res["budget"]["levels"]
    x = [float(lv["label"].rstrip("%")) for lv in levels]
    fig, ax = plt.subplots(figsize=(6.4, 3.8), dpi=150)
    series = [
        ("cart recovery", "Cart-recovery rule (10% to every left cart)", "#8a8f98", "v"),
        ("first come", "First come, first served", "#eb6834", "o"),
        ("fixed price", "Fixed price", "#1baf7a", "s"),
        ("re-solved price", "Re-solved price (ours)", "#2a78d6", "D"),
    ]
    for key, label, color, marker in series:
        share = [lv["rules"][key]["share_of_hindsight"] * 100 for lv in levels]
        ax.plot(x, share, color=color, linewidth=2, marker=marker, markersize=6, label=label)
    ax.set_xscale("log")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{v:g}%" for v in x])
    ax.xaxis.set_minor_locator(matplotlib.ticker.NullLocator())
    ax.set_ylim(min(0, ax.get_ylim()[0]), 105)
    ax.set_xlabel("Monthly discount budget, as a share of what every paying coupon would cost")
    ax.set_ylabel("Share of hindsight value (%)")
    ax.grid(axis="y", color="#e3e5ea", linewidth=0.8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.axhline(0, color="#b9bdc6", linewidth=0.8)
    ax.legend(loc="lower right", bbox_to_anchor=(1.0, 0.3), fontsize=8, framealpha=1, edgecolor="none")
    fig.tight_layout()
    out = RESULTS / "figures"
    out.mkdir(parents=True, exist_ok=True)
    fig.savefig(out / "money_budget_share.png")
    plt.close(fig)
    print("Saved ml/results/figures/money_budget_share.png")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "report":
        write_report(json.loads((RESULTS / "money_check.json").read_text(encoding="utf-8")))
    else:
        main()
