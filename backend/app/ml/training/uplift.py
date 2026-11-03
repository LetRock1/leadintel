"""
The starting next-best-action (uplift) model, and how it compares with other targeting policies.

  1. Simulated leads (app.simulation.population), scored by the lead model (the base P(buy) with no step).
  2. A simulated randomised campaign: every eligible lead gets one random step and only that step's outcome is
     observed, as in a real experiment (app.simulation.effects).
  3. Fit the S-learner (app.ml.nba_core.design) by logistic regression.
  4. Evaluate on fresh leads against the simulator's ground truth: uplift accuracy per step (correlation with the true
     uplift) and the expected profit of the targeting policies per 1,000 leads, all with the same counsellor-call
     capacity (10% of leads).

The model learned here is the cold-start prior. Once the website has logged real decisions and outcomes, the learning
loop (app.ml.learning) updates it. Writes backend/data/models/nba_model.pkl (and nba_card.json) and the policy
comparison ml/results/nba_policy_comparison.{json,md}.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.linear_model import LogisticRegression

from app.core.config import PROJECT_DIR
from app.ml import features as F
from app.ml import lead_model as LM
from app.ml import nba_core as N
from app.ml.training import lead as T
from app.simulation import effects as S
from app.simulation import population as G

log = logging.getLogger(__name__)

NBA_PATH = os.path.join(T.MODEL_DIR, "nba_model.pkl")
NBA_STARTER_PATH = os.path.join(T.MODEL_DIR, "nba_model.starter.pkl")  # what a history starts from
NBA_CARD = os.path.join(T.MODEL_DIR, "nba_card.json")
RESULTS_DIR = str(PROJECT_DIR / "ml" / "results")
CALL_CAPACITY = 0.10


def base_probability(frame, bundle=None):
    """The live lead model's P(buy | no step): the base every step is compared with."""
    if bundle is None:
        if not os.path.exists(T.MODEL_PATH):
            raise SystemExit("Train the lead model first: python -m app.cli train lead")
        bundle = joblib.load(T.MODEL_PATH)
    if "starter" not in bundle:
        raise SystemExit("The lead model is from an older version. Train it again: python -m app.cli train lead")
    return LM.predict_proba(bundle, frame)


def fit_uplift(frame, base_p, actions, y, weights=None, C=1.0):
    X = N.design(N.context(frame, base_p), actions)
    clf = LogisticRegression(C=C, max_iter=5000, fit_intercept=False)
    clf.fit(X, y, sample_weight=weights)
    return clf


def fit_flexible(frame, actions, y, weights=None):
    """The second model family (nba_core.FlexibleSLearner), a challenger in the learning loop."""
    return N.FlexibleSLearner().fit(frame, actions, y, sample_weight=weights)


def predict_all(model, frame, base_p):
    """P(buy | x, a) for every action, for either model family."""
    return N.predict_actions(model, frame, base_p)


def blocked_matrix(frame):
    return S.blocked_matrix(frame)


def apply_capacity(choice, gain_call, gain_alt, alt_choice, capacity):
    """At most `capacity` share of leads get a call: keep the calls with the largest extra gain."""
    is_call = choice == "call"
    k = int(capacity * len(choice))
    if is_call.sum() > k:
        extra = np.where(is_call, gain_call - gain_alt, -np.inf)
        keep = np.argsort(-extra)[:k]
        mask = np.zeros(len(choice), dtype=bool)
        mask[keep] = True
        choice = np.where(is_call & ~mask, alt_choice, choice)
    return choice


def greedy_policy(p_by_action, price, blocked, capacity=CALL_CAPACITY):
    """Our policy: max incremental profit per lead, 'none' if nothing pays, call capacity respected."""
    acts = N.ACTION_LIST
    gains = {}
    for a in acts:
        spec = N.ACTIONS[a]
        value = p_by_action[a] * price * (1 - spec["discount"]) - spec["cost_inr"]
        gains[a] = np.where(blocked[a], -np.inf, value - p_by_action["none"] * price)
    gains["none"] = np.zeros(len(price))
    M = np.column_stack([gains[a] for a in acts])
    choice = np.array(acts)[M.argmax(1)]
    non_call = [a for a in acts if a != "call"]
    Mn = np.column_stack([gains[a] for a in non_call])
    alt = np.array(non_call)[Mn.argmax(1)]
    return apply_capacity(choice, gains["call"], Mn.max(1), alt, capacity)


def evaluate_policy(choice, truth, price):
    """Expected outcomes of a policy, scored with the simulator's TRUE probabilities."""
    n = len(choice)
    p = np.array([truth[a][i] for i, a in enumerate(choice)])
    disc = np.array([N.ACTIONS[a]["discount"] for a in choice])
    cost = np.array([N.ACTIONS[a]["cost_inr"] for a in choice])
    revenue = p * price * (1 - disc)
    base_rev = truth["none"] * price
    per_k = 1000 / n
    return {
        "incremental_conversions_per_1000": round(float((p - truth["none"]).sum() * per_k), 1),
        "net_incremental_profit_per_1000_inr": round(float((revenue - cost - base_rev).sum() * per_k), 0),
        "discount_given_per_1000_inr": round(float((p * price * disc).sum() * per_k), 0),
        "contact_cost_per_1000_inr": round(float(cost.sum() * per_k), 0),
        "calls_per_1000": round(float((choice == "call").sum() * per_k), 0),
        "coupons_per_1000": round(float(np.isin(choice, ["email_coupon_10", "email_coupon_20"]).sum() * per_k), 0),
        "contacted_per_1000": round(float((choice != "none").sum() * per_k), 0),
    }


def baseline_policies(frame, base_p, blocked, rng):
    n = len(frame)
    pick = lambda a, fallback="none": np.where(blocked[a], fallback, a)
    tiers = pd.Series(base_p * 100).apply(F.tier_for).to_numpy()
    rank = np.argsort(-base_p)
    k_call = int(CALL_CAPACITY * n)

    # 1) tier playbook, the usual rule-based workflow: hot leads get the biggest discount and a call
    tier_choice = np.array(["email_info"] * n, dtype=object)
    tier_choice[tiers == "Marketing Campaign"] = "email_coupon_10"
    tier_choice[tiers == "Nurture via Email/WhatsApp"] = "email_coupon_10"
    tier_choice[tiers == "Target Immediately"] = "email_coupon_20"
    target_idx = [i for i in rank if tiers[i] == "Target Immediately" and not blocked["call"][i]][:k_call]
    tier_choice[target_idx] = "call"
    tier_choice = np.array([c if not blocked[c][i] else "none" for i, c in enumerate(tier_choice)])

    # 2) predictive lead-score targeting (what score-based CRMs do): call the top-scored
    #    leads up to capacity, coupon the next 30%, inform the rest
    score_choice = np.array(["email_info"] * n, dtype=object)
    order = [i for i in rank]
    callable_top = [i for i in order if not blocked["call"][i]][:k_call]
    score_choice[callable_top] = "call"
    top = set(callable_top)
    rest = [i for i in order if i not in top]
    score_choice[rest[: int(0.30 * n)]] = "email_coupon_10"
    score_choice = np.array([c if not blocked[c][i] else "none" for i, c in enumerate(score_choice)])

    allowed = [[a for a in N.ACTION_LIST if not blocked[a][i]] for i in range(n)]
    random_choice = np.array([al[int(rng.integers(len(al)))] for al in allowed])
    random_choice = apply_capacity(
        random_choice, np.ones(n), np.zeros(n), np.where(blocked["email_info"], "none", "email_info"), CALL_CAPACITY
    )
    return {
        "No contact": np.array(["none"] * n),
        "Email everyone (no discount)": pick("email_info"),
        "20% coupon to everyone": pick("email_coupon_20"),
        "Random action": random_choice,
        "Tier playbook (rule-based workflow)": tier_choice,
        "Lead-score targeting (score-based CRM)": score_choice,
    }


def train(say=print, train_rows: int = 60000, test_rows: int = 30000, write_report: bool = True) -> dict:
    """Train and save the starting uplift model. write_report: also write the policy comparison to ml/results (the
    paper's table); the tests train a small model without it."""
    say(f"Simulating a randomised campaign on {train_rows:,} leads (training) ...")
    train_raw = G.generate(train_rows, seed=2024, return_truth=True)
    frame, actions, props, y, _ = S.simulate_randomized_campaign(train_raw, seed=11)
    base_p = base_probability(frame)
    clf = fit_uplift(frame, base_p, actions, y)

    say(f"Evaluating on {test_rows:,} fresh leads against the simulator's ground truth ...")
    test_raw = G.generate(test_rows, seed=7777, return_truth=True)
    tf = F.to_model_frame(test_raw)
    tb = base_probability(tf)
    truth = S.true_probabilities(tf, test_raw["_p_true"].to_numpy(), seed=99)
    pred = predict_all(clf, tf, tb)
    blocked = blocked_matrix(tf)
    price = S.prices_for(tf)

    uplift_quality = {}
    for a in N.TREATMENTS:
        ok = ~blocked[a]
        true_u = (truth[a] - truth["none"])[ok]
        pred_u = (pred[a] - pred["none"])[ok]
        uplift_quality[a] = {
            "corr_with_true_uplift": round(float(np.corrcoef(true_u, pred_u)[0, 1]), 3),
            "mean_true_uplift_pts": round(float(true_u.mean() * 100), 2),
            "mean_pred_uplift_pts": round(float(pred_u.mean() * 100), 2),
        }
    say("\nUplift accuracy (correlation of predicted vs true per-person uplift):")
    for a, q in uplift_quality.items():
        say(
            f"  {a:16s} r={q['corr_with_true_uplift']:.3f}   true {q['mean_true_uplift_pts']:+.2f} pts   "
            f"predicted {q['mean_pred_uplift_pts']:+.2f} pts"
        )

    rng = np.random.default_rng(5)
    policies = baseline_policies(tf, tb, blocked, rng)
    policies["Next-best-action (ours, uplift)"] = greedy_policy(pred, price, blocked)
    say("Fitting the flexible challenger family for comparison ...")
    flex = fit_flexible(frame, actions, y)
    policies["Next-best-action (flexible GBM challenger)"] = greedy_policy(predict_all(flex, tf, tb), price, blocked)
    policies["Oracle (knows true effects)"] = greedy_policy(truth, price, blocked)
    table = {name: evaluate_policy(choice, truth, price) for name, choice in policies.items()}

    say("\nPolicy comparison per 1,000 leads (call capacity 10%, true outcomes from the simulator):")
    hdr = f"  {'Policy':46s} {'+conv':>7s} {'net profit':>14s} {'discount':>12s} {'calls':>6s} {'coupons':>8s}"
    say(hdr)
    for name, m in table.items():
        say(
            f"  {name:46s} {m['incremental_conversions_per_1000']:7.1f} "
            f"{m['net_incremental_profit_per_1000_inr']:14,.0f} "
            f"{m['discount_given_per_1000_inr']:12,.0f} {m['calls_per_1000']:6.0f} {m['coupons_per_1000']:8.0f}"
        )

    version = dt.datetime.now().strftime("nba-%Y%m%d-%H%M%S")
    bundle = {
        "model": clf,
        "kind": N.model_kind(clf),
        "version": version,
        "context_names": N.CONTEXT_NAMES,
        "treatments": N.TREATMENTS,
        "trained_at": dt.datetime.now().isoformat(timespec="seconds"),
        "sklearn_version": sklearn.__version__,
        "trained_on": {"simulated_rows": int(len(y)), "real_rows": 0},
        "uplift_quality": uplift_quality,
    }
    joblib.dump(bundle, NBA_PATH)
    joblib.dump(bundle, NBA_STARTER_PATH)
    coefs = clf.coef_[0].reshape(1 + len(N.TREATMENTS), len(N.CONTEXT_NAMES))
    card = {k: v for k, v in bundle.items() if k != "model"}
    card["action_effects_logodds"] = {
        a: dict(zip(N.CONTEXT_NAMES, np.round(coefs[i + 1], 3).tolist())) for i, a in enumerate(N.TREATMENTS)
    }
    card["policy_comparison_per_1000"] = table
    with open(NBA_CARD, "w", encoding="utf-8") as f:
        json.dump(card, f, indent=2)
    if not write_report:
        say(f"\nSaved {NBA_PATH} ({version})")
        return bundle
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(os.path.join(RESULTS_DIR, "nba_policy_comparison.json"), "w", encoding="utf-8") as f:
        json.dump(
            {
                "uplift_quality": uplift_quality,
                "policies": table,
                "assumptions": S.TRUE_EFFECTS,
                "call_capacity": CALL_CAPACITY,
            },
            f,
            indent=2,
        )
    with open(os.path.join(RESULTS_DIR, "nba_policy_comparison.md"), "w", encoding="utf-8") as f:
        f.write(
            "| Policy | Incremental conversions / 1000 | Net incremental profit / 1000 (INR) | Discount given (INR) "
            "| Calls | Coupons |\n|---|---|---|---|---|---|\n"
        )
        for name, m in table.items():
            f.write(
                f"| {name} | {m['incremental_conversions_per_1000']} | "
                f"{m['net_incremental_profit_per_1000_inr']:,.0f} | "
                f"{m['discount_given_per_1000_inr']:,.0f} | {m['calls_per_1000']:.0f} | {m['coupons_per_1000']:.0f} |\n"
            )
    say(f"\nSaved {NBA_PATH} ({version}) and ml/results/nba_policy_comparison.md")
    return bundle
