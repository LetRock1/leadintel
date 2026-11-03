"""
The true effect of every CRM step on a simulated learner: a semi-synthetic simulator for next-best-action.

An uplift model needs to know what would have happened under each step, but every person only ever receives one
(the fundamental problem of causal inference). The accepted way to evaluate uplift and next-best-action policies,
used throughout the causal-ML literature (for example the IHDP and ACIC benchmarks), is a semi-synthetic set-up:
realistic covariates and outcome functions whose treatment effects are known, so every policy can be scored against
the truth. Real randomised data (the Hillstrom email experiment) is used separately to validate on real outcomes.

The response assumptions are explicit, so they can be reported and challenged:
  * discounts mostly move price-sensitive people (students, unemployed, homemakers, or people who added to the cart
    but stopped before checkout); they barely move people already at checkout ("sure things")
  * a counsellor call helps people who showed explicit intent (cart, enquiry) and professionals; calling cold,
    barely-engaged people backfires
  * emails help people who engage with emails; WhatsApp gives a small lift
  * each person also has an individual, unobservable response (noise)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.ml import features as F
from app.ml import nba_core as N

# true effect on the log-odds of buying, per step, as a function of the context c(x) (app.ml.nba_core.context)
#                      bias  base  price  high   cart/enq  prof  email  wa   low_eng
TRUE_EFFECTS = {
    "none": [0.00, 0, 0.00, 0.00, 0.00, 0.00, 0.00, 0.0, 0.00],
    "email_info": [0.08, 0, 0.00, 0.00, 0.05, 0.00, 0.30, 0.0, -0.05],
    "email_coupon_10": [0.15, 0, 0.60, -0.20, 0.05, -0.05, 0.10, 0.0, 0.00],
    "email_coupon_20": [0.25, 0, 1.00, -0.20, 0.05, -0.05, 0.10, 0.0, 0.00],
    "call": [0.10, 0, 0.00, 0.10, 0.90, 0.35, 0.00, 0.0, -0.50],
    "whatsapp": [0.12, 0, 0.10, 0.00, 0.25, 0.00, 0.00, 0.15, 0.00],
}
EFFECT_NOISE_SD = 0.15


def _catalog_prices():
    from app.services import catalog

    courses = catalog.all_courses()
    if not courses:
        return {}, 40000.0
    by_type = {}
    for c in courses:
        by_type.setdefault(F.COURSE_TYPE_BY_SLUG.get(c["slug"], "Unknown"), []).append(c["price"])
    return {k: float(np.mean(v)) for k, v in by_type.items()}, float(np.mean([c["price"] for c in courses]))


def prices_for(frame: pd.DataFrame) -> np.ndarray:
    by_type, avg = _catalog_prices()
    return frame["CourseType"].map(lambda t: by_type.get(t, avg)).to_numpy(dtype=float)


def blocked_matrix(frame: pd.DataFrame) -> dict:
    """Which steps cannot reach each person (consent), assuming a phone number unless they opted out."""
    n = len(frame)
    b = {"none": np.zeros(n, dtype=bool)}
    for a in ("email_info", "email_coupon_10", "email_coupon_20"):
        b[a] = frame["DoNotEmail"].to_numpy() == 1
    b["call"] = frame["DoNotCall"].to_numpy() == 1
    b["whatsapp"] = frame["WhatsAppOptIn"].to_numpy() == 0
    return b


def true_probabilities(frame: pd.DataFrame, p_true_none, seed: int = 0) -> dict:
    """True P(buy | x, a) for every step (the simulation's ground truth)."""
    rng = np.random.default_rng(seed)
    ctx = N.context(frame, np.full(len(frame), 0.5))  # the base-logit column is unused (coefficient 0)
    base = N._logit(p_true_none)
    blocked = blocked_matrix(frame)
    out = {}
    for a in N.ACTION_LIST:
        eff = ctx @ np.asarray(TRUE_EFFECTS[a])
        if a != "none":
            eff = eff + rng.normal(0, EFFECT_NOISE_SD, len(frame))
            eff = np.where(blocked[a], 0.0, eff)  # cannot reach them: no effect
        out[a] = 1 / (1 + np.exp(-(base + eff)))
    return out


def simulate_randomized_campaign(raw: pd.DataFrame, seed: int = 1):
    """A logged campaign: each person gets a uniformly random allowed step (a randomised experiment), and only that
    step's outcome is observed. Returns (frame, actions, propensities, outcomes, true probabilities)."""
    rng = np.random.default_rng(seed)
    frame = F.to_model_frame(raw)
    truth = true_probabilities(frame, raw["_p_true"].to_numpy(), seed=seed + 7)
    blocked = blocked_matrix(frame)
    actions, props = [], []
    for i in range(len(frame)):
        allowed = [a for a in N.ACTION_LIST if not blocked[a][i]]
        a = allowed[int(rng.integers(len(allowed)))]
        actions.append(a)
        props.append(1 / len(allowed))
    actions = np.array(actions)
    p = np.array([truth[a][i] for i, a in enumerate(actions)])
    y = (rng.random(len(frame)) < p).astype(int)
    return frame, actions, np.array(props), y, truth
