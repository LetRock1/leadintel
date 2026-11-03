"""
E3 — Does a CRM that retrains on its own results fool itself, and does our learning loop avoid it?
Real randomized data: Hillstrom email experiment (42,613 customers: men's email vs no email, each with
probability 1/2; outcome = visited the website within two weeks).

How a CRM is emulated on real data (no simulator):
  A CRM policy "email the top 30% by the current score, 15% of choices random" is emulated by keeping
  each customer with the probability the policy would have chosen the arm they really got (rejection
  sampling; both arms had probability 1/2). What remains is exactly the data that policy would have
  logged, with REAL outcomes. Like the product, the CRM has a control group: 5% of customers it never
  contacts.

  Round 0  the CRM starts with a recency/spend rule (how CRMs usually start) and emails by it.
  Round 1  it retrains on what it logged; each method's new score decides the next round's emails.
  Round 2  it retrains again on everything logged.

Ways to retrain (the same learner, gradient boosting, for every method):
  naive        fit "who visited" on everything logged: how CRMs retrain (Salesforce Einstein "analyzes your
               past converted leads"; HubSpot learns from past contacts' outcomes)
  holdout      fit only on the control group (+ the data from before the CRM): the safe-updating approach
               of clinical prediction models (Liley et al., AISTATS 2021; Haidar-Wehbe et al. 2022) —
               unbiased by construction, but it learns from few people
  IPW          fit on the customers the CRM left alone, weighted by 1 / P(left alone)
  ours         told what the CRM did: the email is an input, and the score is read with it switched off
               (what backend/app/ml/learning.py does)
  reference    the same learner on every customer the randomized experiment left alone in the same period:
               no loop at all. A deployed CRM never has this; it is the best case.

The precise metric: SELF-INFLICTED BIAS. Among the 30% each score targets, how much it over-predicts what
those customers do when left alone (held-out customers the experiment really left alone). Even the
no-loop reference over-predicts a little, because picking the top of any noisy score does (the winner's
curse), so the bias the loop itself adds is a method's overstatement MINUS the reference's in the same
repeat (paired). 95% intervals: corrected resampled t-test (Nadeau & Bengio 2003), which allows for the
overlap between repeats (a plain t-interval over repeats would be about five times too narrow).

Also: honest AUC and log-loss on the left-alone truth; calibration on all held-out left-alone customers;
the AUC a CRM sees on the data its own policy logged (the accuracy illusion); and model choice, naive vs
ours: the usual check (log-loss on the CRM's logged data) and our check (the control group: swap only if
better in >= 90% of 300 bootstrap resamples, as in the product), each against the truth.

Run:  python ml/experiments/learning_loop.py [repeats=50] [exploration=0.15] [--no-sensitivity]   (about 5 minutes)
Writes ml/results/learning_loop.md and .json
"""

import json
import os
import sys
import time

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import log_loss, roc_auc_score

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hillstrom_uplift as H  # noqa: E402

RESULTS = os.path.normpath(os.path.join(HERE, "..", "results"))
TARGET_SHARE = 0.30
HOLDOUT = 0.05  # the product's control group (crm_settings.json: global_control)
CONFIDENCE, RESAMPLES = 0.90, 300  # the product's swap rule (crm_settings.json: learning)
REPEATS = int(sys.argv[1]) if len(sys.argv) > 1 else 50
EPS = float(sys.argv[2]) if len(sys.argv) > 2 else 0.15
SPLIT = (0.10, 0.30, 0.30, 0.30)  # before the CRM, round 1, round 2, held-out test
METHODS = ["naive", "holdout", "ipw", "ours", "reference"]
LABELS = {
    "naive": "Naive retrain (how CRMs retrain)",
    "holdout": "Control group only (clinical-ML holdout approach)",
    "ipw": "Left-alone customers, weighted (IPW)",
    "ours": "**Ours** (told what the CRM did)",
    "reference": "Reference: no loop at all (oracle)",
}

h, Xall, arm = H.load()
keep = np.isin(arm, ["none", "mens"])
X = Xall[keep].reset_index(drop=True)
T = (arm[keep] == "mens").astype(int)
Y = h.loc[keep, "visit"].to_numpy().astype(int)
XN = X.to_numpy(dtype=float)
N = len(Y)


def gbm(seed):
    return HistGradientBoostingClassifier(random_state=seed, **H.GBM)


def clip(p):
    return np.clip(p, 1e-4, 1 - 1e-4)


def rule(Z):
    return H.rfm_score(pd.DataFrame(Z, columns=H.FEATURES))


def log_round(idx, score_fn, rng, hold, eps):
    """One deployment round on customers idx: the rows the policy would have logged, and the probability
    it gave the arm each kept customer really got. The control group is never emailed."""
    s = score_fn(XN[idx])
    ctl = hold[idx]
    thr = np.quantile(s[~ctl], 1 - TARGET_SHARE)
    p1 = np.where(ctl, 0.0, np.where(s >= thr, 1 - eps / 2, eps / 2))
    p_got = np.where(T[idx] == 1, p1, 1 - p1)
    kept = rng.random(len(idx)) < p_got
    return idx[kept], p_got[kept]


def fit_plain(rows, seed, weight=None):
    m = gbm(seed).fit(XN[rows], Y[rows], sample_weight=weight)
    return lambda Z: m.predict_proba(Z)[:, 1]


def fit_ours(rows, seed):
    m = gbm(seed).fit(np.column_stack([XN[rows], T[rows]]), Y[rows])
    return lambda Z: m.predict_proba(np.column_stack([Z, np.zeros(len(Z))]))[:, 1]


def train(method, rows, probs, clean, seed):
    """rows: logged customers; probs: P(the arm they got); clean: before the CRM or in the control group."""
    if method == "naive":
        return fit_plain(rows, seed)
    if method == "ours":
        return fit_ours(rows, seed)
    if method == "ipw":
        alone = T[rows] == 0
        return fit_plain(rows[alone], seed, 1.0 / probs[alone])
    if method == "holdout":
        return fit_plain(rows[clean[rows]], seed)
    raise ValueError(method)


def judge(f, C, own_logged, live_C):
    s = f(XN[C])
    alone = T[C] == 0
    top = s >= np.quantile(s, 1 - TARGET_SHARE)
    pred, actual = s[top & alone].mean(), Y[C][top & alone].mean()
    return {
        "overstatement_pct": 100 * (pred - actual) / actual,
        "calibration_pts": 100 * (s[alone].mean() - Y[C][alone].mean()),
        "actual_rate_pts": 100 * Y[C][alone].mean(),
        "honest_auc": roc_auc_score(Y[C][alone], s[alone]),
        "honest_logloss": log_loss(Y[C][alone], clip(s[alone])),
        "apparent_auc": roc_auc_score(Y[own_logged], f(XN[own_logged])),
        "live_logloss": log_loss(Y[live_C], clip(f(XN[live_C]))),
    }


def prob_better(y, p_old, p_new, seed):
    """The product's check (learning.prob_better): share of bootstrap resamples of the control group in
    which the new model's log-loss is lower."""
    loss = lambda p: -(y * np.log(clip(p)) + (1 - y) * np.log(clip(1 - p)))
    lo, ln = loss(p_old), loss(p_new)
    pick = np.random.default_rng(seed).integers(0, len(y), (RESAMPLES, len(y)))
    return float((ln[pick].sum(1) < lo[pick].sum(1)).mean())


def interval(x):
    """Mean and 95% interval over repeats, corrected for overlapping training/test sets (Nadeau & Bengio)."""
    x = np.asarray(x, float)
    r = len(x)
    test_over_train = SPLIT[3] / (1 - SPLIT[3])
    se = np.sqrt((1 / r + test_over_train) * x.var(ddof=1))
    t = stats.t.ppf(0.975, r - 1)
    return float(x.mean()), float(x.mean() - t * se), float(x.mean() + t * se)


def fmt(x, digits=1, unit="", sign=True):
    m, lo, hi = interval(x)
    f = f"+.{digits}f" if sign else f".{digits}f"
    return f"{m:{f}}{unit} [{lo:{f}}, {hi:{f}}]"


def one_repeat(seed, eps):
    rng = np.random.default_rng(seed)
    perm = rng.permutation(N)
    cuts = np.cumsum(np.array(SPLIT[:3]) * N).astype(int)
    before, B1, B2, C = np.split(perm, cuts)
    hold = rng.random(N) < HOLDOUT  # the control group: never contacted
    clean = hold.copy()
    clean[before] = True
    hist = before[T[before] == 0]  # before the CRM: nobody was emailed
    L1, P1 = log_round(B1, rule, rng, hold, eps)
    rows1, probs1 = np.r_[hist, L1], np.r_[np.ones(len(hist)), P1]
    models = {}
    for m in ("naive", "holdout", "ipw", "ours"):
        f1 = train(m, rows1, probs1, clean, seed)
        L2, P2 = log_round(B2, f1, rng, hold, eps)  # each method's score runs round 2 itself
        models[m] = train(m, np.r_[rows1, L2], np.r_[probs1, P2], clean, seed + 100)
    models["reference"] = fit_plain(np.r_[hist, B1[T[B1] == 0], B2[T[B2] == 0]], seed + 200)
    live_C, _ = log_round(C, rule, np.random.default_rng(5000 + seed), hold, eps)  # the CRM's own logged data
    out = []
    for m, f in models.items():
        own, _ = log_round(C, f, np.random.default_rng(1000 + seed), hold, eps)
        r = judge(f, C, own, live_C)
        r.update(method=m, repeat=seed)
        out.append(r)
    # model choice between naive and ours, on the control group of the held-out period (as in the product)
    ctl = C[hold[C] & (T[C] == 0)]
    y = Y[ctl].astype(float)
    pn, po = models["naive"](XN[ctl]), models["ours"](XN[ctl])
    choice = {
        "repeat": seed,
        "control_people": int(len(ctl)),
        "ours_beats_naive_p": prob_better(y, pn, po, 7000 + seed),  # champion naive, challenger ours
        "naive_beats_ours_p": prob_better(y, po, pn, 8000 + seed),
    }  # champion ours, challenger naive
    return out, choice


def run(eps, repeats, say=print):
    t0 = time.time()
    rows_out, choices = [], []
    for seed in range(repeats):
        out, choice = one_repeat(seed, eps)
        rows_out += out
        choices.append(choice)
        say(f"  exploration {eps:.0%}: repeat {seed + 1}/{repeats} done ({time.time() - t0:.0f} s)")
    return pd.DataFrame(rows_out), pd.DataFrame(choices)


def removed_share(piv):
    """Per repeat: the share of naive retraining's feedback bias that ours removes (vs the no-loop reference)."""
    cal = piv["calibration_pts"]
    return 100 * (1 - (cal["ours"] - cal["reference"]) / (cal["naive"] - cal["reference"]))


def main():
    t0 = time.time()
    df, ch = run(EPS, REPEATS)
    piv = df.pivot(index="repeat", columns="method")
    cal, over, rate = piv["calibration_pts"], piv["overstatement_pct"], piv["actual_rate_pts"]["reference"]
    removed = removed_share(piv).to_numpy()
    cols = ["overstatement_pct", "calibration_pts", "honest_auc", "apparent_auc", "honest_logloss", "live_logloss"]
    mean = df.groupby("method")[cols].mean().reindex(METHODS)
    sd = df.groupby("method")[cols].std().reindex(METHODS)
    wins = lambda a: int(np.sum(a))
    diff = lambda col, a, b: (piv[col][a] - piv[col][b]).to_numpy()

    # model choice against the truth (honest log-loss on all held-out left-alone customers)
    truth_ours = diff("honest_logloss", "ours", "naive") < 0
    usual_picks_naive = diff("live_logloss", "naive", "ours") < 0
    swap_to_ours = (ch["ours_beats_naive_p"] >= CONFIDENCE).to_numpy()
    swap_to_naive = (ch["naive_beats_ours_p"] >= CONFIDENCE).to_numpy()
    # one number for "best of all": honest log-loss (a proper scoring rule: ranking and honest probabilities at once)
    deployable = ["naive", "holdout", "ipw", "ours"]
    ll = piv["honest_logloss"][deployable]
    best_of_all = (ll.idxmin(axis=1) == "ours").to_numpy()

    lines = [
        f"# E3 Learning loop on real randomized data (Hillstrom, {N:,} customers: men's email vs none)",
        "",
        f"{REPEATS} repeats (random splits: {SPLIT[0]:.0%} before the CRM, two rounds of {SPLIT[1]:.0%}, "
        f"{SPLIT[3]:.0%} held out). The CRM emails the top {TARGET_SHARE:.0%} by its score, {EPS:.0%} of its "
        f"choices random, and never contacts its {HOLDOUT:.0%} control group; it retrains twice. Everything is "
        f"judged on held-out customers the real experiment left alone (visit rate {rate.mean():.1f}%). "
        "Intervals: 95%, corrected resampled t-test (Nadeau & Bengio 2003).",
        "",
        "## The precise metric: feedback bias",
        "",
        "**Feedback bias** = mean predicted minus actual visit rate of held-out customers the randomized "
        "experiment left alone (percentage points). A score that learned the CRM's own emails as customer "
        "quality over-predicts what customers do when nobody contacts them. No selection is involved, so the "
        "no-loop reference sits at zero.",
        "",
        "| Method | Feedback bias (points) | In % of the true rate | Over-predicts its own targeted 30% by | "
        "Honest AUC | Honest log-loss |",
        "|---|---|---|---|---|---|",
    ]
    for m in METHODS:
        rel = 100 * cal[m].to_numpy() / rate.to_numpy()
        lines.append(
            f"| {LABELS[m]} | {fmt(cal[m], 2)} | {fmt(rel, 0)}% | {fmt(over[m], 1)}% | "
            f"{mean.loc[m, 'honest_auc']:.3f} | {mean.loc[m, 'honest_logloss']:.4f} |"
        )
    lines += [
        "",
        f"- **Best of all deployable methods on one proper scoring rule:** ours has the lowest honest log-loss of "
        f"naive, holdout, IPW and ours in **{wins(best_of_all)} of {REPEATS}** repeats (and is level with the no-loop "
        f"oracle: lower in {wins(diff('honest_logloss', 'ours', 'reference') < 0)} of {REPEATS}).",
        f"- **Ours removes {fmt(removed, 0, sign=False)}% of the feedback bias** of naive retraining; ours minus the no-loop "
        f"reference: {fmt(diff('calibration_pts', 'ours', 'reference'), 2)} points. Ours is less biased than "
        f"naive in **{wins(cal['ours'] < cal['naive'])} of {REPEATS}** repeats.",
        f"- Against the clinical-ML holdout approach (unbiased by construction, but it learns from the control "
        f"group only): honest AUC {fmt(diff('honest_auc', 'ours', 'holdout'), 3)} higher, log-loss "
        f"{fmt(diff('honest_logloss', 'holdout', 'ours'), 4)} lower with ours (ours better in "
        f"{wins(diff('honest_auc', 'ours', 'holdout') > 0)} and {wins(diff('honest_logloss', 'holdout', 'ours') > 0)} "
        f"of {REPEATS}).",
        f"- Against IPW (left-alone customers, weighted): the same idea, but the weights (up to "
        f"{2 / EPS:.0f}x) make it noisy: its feedback bias varies with sd {sd.loc['ipw', 'calibration_pts']:.2f} "
        f"points between repeats, ours {sd.loc['ours', 'calibration_pts']:.2f}.",
        f"- Against naive: honest AUC {fmt(diff('honest_auc', 'ours', 'naive'), 3)}, log-loss "
        f"{fmt(diff('honest_logloss', 'naive', 'ours'), 4)} lower with ours (ours more accurate on the truth in "
        f"{wins(truth_ours)} of {REPEATS}).",
        f"- The last column includes the winner's curse: picking the top 30% of any noisy score over-predicts them "
        f"(the no-loop reference: {mean.loc['reference', 'overstatement_pct']:+.1f}%); scores learned from fewer "
        "people are noisier, so the holdout and IPW models show more of it.",
        "",
        "## The accuracy illusion",
        "",
        "| Method | AUC on the data its own policy logged | Honest AUC | Illusion |",
        "|---|---|---|---|",
    ]
    for m in METHODS:
        lines.append(
            f"| {LABELS[m]} | {mean.loc[m, 'apparent_auc']:.3f} | {mean.loc[m, 'honest_auc']:.3f} | "
            f"{fmt(piv['apparent_auc'][m].to_numpy() - piv['honest_auc'][m].to_numpy(), 3)} |"
        )
    lines += [
        "",
        "Every model looks better on the data its own emails shaped: an AUC measured on a CRM's own "
        "logged data is not its accuracy.",
        "",
        "## Choosing the model: naive vs ours",
        "",
        "| Check | Result |",
        "|---|---|",
        f"| Truth: honest log-loss on all held-out left-alone customers | ours better in {wins(truth_ours)} of {REPEATS} |",
        f"| Usual check: log-loss on the CRM's own logged data | picks naive in **{wins(usual_picks_naive)} of "
        f"{REPEATS}** |",
        f"| Our check with naive in place: the control group, swap if better in >= {CONFIDENCE:.0%} of "
        f"{RESAMPLES} resamples | swaps to ours in {wins(swap_to_ours)} of {REPEATS}; otherwise keeps naive |",
        f"| Our check with ours in place | swaps to naive in **{wins(swap_to_naive)} of {REPEATS}** |",
        "",
        f"The held-out period's control group has {ch['control_people'].mean():.0f} left-alone people on "
        "average: our check rarely makes a wrong swap; with so few people it often keeps the current model "
        "(the right swap needs more control-group outcomes).",
    ]
    sens = {}
    if "--no-sensitivity" not in sys.argv:
        lines += [
            "",
            "## Different exploration rates",
            "",
            "| Random share of the CRM's choices | Feedback bias, naive (points) | Feedback bias, ours | "
            "Bias removed | Honest AUC naive / ours |",
            "|---|---|---|---|---|",
        ]
        for eps in sorted({0.0, 0.05, EPS, 0.30}):
            d2, _ = (df, ch) if eps == EPS else run(eps, max(20, REPEATS // 2))
            p2 = d2.pivot(index="repeat", columns="method")
            sens[eps] = {
                "naive": interval(p2["calibration_pts"]["naive"]),
                "ours": interval(p2["calibration_pts"]["ours"]),
                "removed": interval(removed_share(p2)),
                "repeats": int(len(p2)),
                "auc_naive": float(p2["honest_auc"]["naive"].mean()),
                "auc_ours": float(p2["honest_auc"]["ours"].mean()),
            }
            lines.append(
                f"| {eps:.0%} ({len(p2)} repeats) | {fmt(p2['calibration_pts']['naive'], 2)} | "
                f"{fmt(p2['calibration_pts']['ours'], 2)} | {fmt(removed_share(p2), 0, sign=False)}% | "
                f"{sens[eps]['auc_naive']:.3f} / {sens[eps]['auc_ours']:.3f} |"
            )
        lines += [
            "",
            "Ours needs customers the CRM did NOT email among those it would target (overlap). The random "
            "choices give some, and so does the control group, which the CRM never contacts: that is why "
            "the result hardly depends on the exploration rate here, even at 0%.",
        ]
    os.makedirs(RESULTS, exist_ok=True)
    with open(os.path.join(RESULTS, "learning_loop.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    summary = {
        "repeats": REPEATS,
        "exploration": EPS,
        "holdout": HOLDOUT,
        "split": SPLIT,
        "interval": "mean, 95% low, 95% high; corrected resampled t-test (Nadeau & Bengio 2003)",
        "true_rate_pts": interval(rate),
        "feedback_bias_pts": {m: interval(cal[m]) for m in METHODS},
        "feedback_bias_removed_pct": interval(removed),
        "ours_minus_reference_pts": interval(diff("calibration_pts", "ours", "reference")),
        "targeted_overstatement_pct": {m: interval(over[m]) for m in METHODS},
        "honest_auc": {m: interval(piv["honest_auc"][m]) for m in METHODS},
        "honest_logloss": {m: interval(piv["honest_logloss"][m]) for m in METHODS},
        "apparent_auc": {m: interval(piv["apparent_auc"][m]) for m in METHODS},
        "ours_minus_holdout_auc": interval(diff("honest_auc", "ours", "holdout")),
        "holdout_minus_ours_logloss": interval(diff("honest_logloss", "holdout", "ours")),
        "ours_minus_naive_auc": interval(diff("honest_auc", "ours", "naive")),
        "naive_minus_ours_logloss": interval(diff("honest_logloss", "naive", "ours")),
        "sd_between_repeats": sd.round(5).to_dict(orient="index"),
        "wins": {
            "ours_lowest_honest_logloss_of_deployable": wins(best_of_all),
            "ours_less_biased_than_naive": wins(cal["ours"] < cal["naive"]),
            "ours_better_than_naive_on_truth": wins(truth_ours),
            "usual_check_picks_naive": wins(usual_picks_naive),
            "our_check_swaps_naive_to_ours": wins(swap_to_ours),
            "our_check_swaps_ours_to_naive": wins(swap_to_naive),
        },
        "control_people_mean": float(ch["control_people"].mean()),
        "exploration_sensitivity": {f"{k:.2f}": v for k, v in sens.items()},
        "per_repeat": df.round(6).to_dict(orient="records"),
        "choices": ch.round(4).to_dict(orient="records"),
    }
    with open(os.path.join(RESULTS, "learning_loop.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=1)
    print("\n" + "\n".join(lines))
    print(f"\n({time.time() - t0:.0f} s) Saved ml/results/learning_loop.md")


if __name__ == "__main__":
    main()
