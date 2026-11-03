"""
Next-best-action: the shared core (used by training, evaluation
and the live server, exactly like app/ml/features.py).

The question a lead SCORE answers:   "How likely is this person to buy?"
The question NEXT-BEST-ACTION answers: "Which of our actions will CHANGE
whether they buy, and is it worth what it costs?"

They are different. The old playbook (and tier-based workflows in typical
CRMs) gave the biggest discount to the hottest leads — people who would
mostly have bought anyway — so the discount was money given away. An uplift
model estimates, for every action a, P(buy | person, a) and picks

    a* = argmax_a  E[profit | a] − E[profit | do nothing]
       E[profit | a] = P(buy | x, a) × price × (1 − discount_a) − cost_a

and does nothing at all when no action pays for itself.

Model: a logistic "S-learner" with action × context interactions:
    logit P(buy | x, a) = β·c(x) + γ_a·c(x)        (γ_none = 0)
where c(x) is a small, interpretable context vector built on top of the
lead-score model's own probability. Each γ_a is literally "how much action a
moves the odds for people like this", so the decision is explainable.
"""

import numpy as np
import pandas as pd

# The actions the system can take
# cost_inr = cost of performing the action (counsellor time, messaging), charged
# whether or not the person buys. discount = fraction of price given up IF they buy.
_DEFAULT_ACTIONS = {
    "none": {"label": "Do nothing for now", "channel": None, "discount": 0.00, "cost_inr": 0},
    "email_info": {"label": "Send an information email", "channel": "email", "discount": 0.00, "cost_inr": 2},
    "email_coupon_10": {"label": "Send email with 10% coupon", "channel": "email", "discount": 0.10, "cost_inr": 2},
    "email_coupon_20": {"label": "Send email with 20% coupon", "channel": "email", "discount": 0.20, "cost_inr": 2},
    "call": {"label": "Counsellor phone call", "channel": "call", "discount": 0.00, "cost_inr": 150},
    "whatsapp": {"label": "WhatsApp message", "channel": "whatsapp", "discount": 0.00, "cost_inr": 5},
}


def _actions_from_settings():
    """Labels, costs and discounts come from crm_settings.json; the set of actions is fixed
    (the uplift model is trained on exactly these)."""
    try:
        from app.core import rules

        conf = rules.S.get("actions", {})
    except Exception:  # noqa: BLE001 - research scripts may run without the settings file: defaults then
        conf = {}
    out = {}
    for key, d in _DEFAULT_ACTIONS.items():
        c = conf.get(key, {})
        out[key] = {
            "label": c.get("label", d["label"]),
            "channel": d["channel"],
            "discount": float(c.get("discount", d["discount"])),
            "cost_inr": float(c.get("cost", d["cost_inr"])),
        }
    return out


ACTIONS = _actions_from_settings()
ACTION_LIST = list(ACTIONS)
TREATMENTS = [a for a in ACTION_LIST if a != "none"]

PRICE_SENSITIVE_OCC = {"Student", "Unemployed", "Housewife"}
PROFESSIONAL_OCC = {"Working Professional", "Businessman"}

CONTEXT_NAMES = [
    "bias",
    "base_logit",
    "price_sensitive",
    "high_intent",
    "cart_or_enquiry",
    "professional",
    "email_engaged",
    "whatsapp_opt_in",
    "low_engagement",
]


def _logit(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def context(frame: pd.DataFrame, base_prob) -> np.ndarray:
    """c(x): interpretable context for uplift. frame = features.to_model_frame(...)."""
    f = frame
    occ = f["CurrentOccupation"].astype(str)
    return np.column_stack(
        [
            np.ones(len(f)),
            _logit(base_prob),
            (occ.isin(PRICE_SENSITIVE_OCC) | ((f["AddedToCart"] == 1) & (f["CheckoutStarted"] == 0))).astype(float),
            (f["CheckoutStarted"] == 1).astype(float),
            ((f["AddedToCart"] == 1) | (f["EnquirySubmitted"] == 1)).astype(float),
            occ.isin(PROFESSIONAL_OCC).astype(float),
            (f["EmailOpenedCount"] > 0).astype(float),
            (f["WhatsAppOptIn"] == 1).astype(float),
            (f["TotalTimeOnWebsite"] < 120).astype(float),
        ]
    )


def design(ctx: np.ndarray, actions) -> np.ndarray:
    """[c(x) | 1{a=k}·c(x) for every treatment k] — the S-learner design matrix."""
    actions = np.asarray(actions)
    blocks = [ctx]
    for k in TREATMENTS:
        blocks.append(ctx * (actions == k)[:, None])
    return np.hstack(blocks)


def eligible(features: dict, has_phone: bool) -> dict:
    """Which actions are allowed for this person (consent + contact details)."""
    out = {}
    for a in ACTION_LIST:
        ch = ACTIONS[a]["channel"]
        reason = None
        if ch == "email" and features.get("DoNotEmail"):
            reason = "opted out of email"
        elif ch == "call" and (features.get("DoNotCall") or not has_phone):
            reason = "opted out of calls" if features.get("DoNotCall") else "no phone number"
        elif ch == "whatsapp" and (not features.get("WhatsAppOptIn") or not has_phone):
            reason = "not opted in to WhatsApp" if not features.get("WhatsAppOptIn") else "no phone number"
        out[a] = reason
    return out


COUPON_ACTIONS = ("email_coupon_10", "email_coupon_20")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sept", "Oct", "Nov", "Dec")


def held_coupon_reason(coupon) -> str | None:
    """Why no coupon step is possible while the person still holds an open coupon (None when they hold none). One
    open coupon per person: a second one would only stack discounts on the same purchase."""
    if not coupon:
        return None
    until = coupon_until(coupon)
    return f"already has an open {int(coupon['discount_pct'])}% coupon" + (f" {until}" if until else "")


def coupon_block_reason(held=None, recent=None, gap_days=7) -> str | None:
    """Why no coupon step is possible: an open coupon (held), or a coupon given in the last gap_days days (recent),
    used or not. None when neither."""
    if held:
        return held_coupon_reason(held)
    if recent:
        when = str(recent.get("created_at") or "")
        day = f" on {int(when[8:10])} {MONTHS[int(when[5:7]) - 1]}" if len(when) >= 10 else " recently"
        return f"already got a coupon{day} (at most one every {int(gap_days)} days)"
    return None


def coupon_until(coupon) -> str:
    """'until 30 Oct, 18:41' from a coupon's expiry (empty when it has none)."""
    until = str(coupon.get("expires_at") or "")
    if len(until) < 16:
        return ""
    return f"until {int(until[8:10])} {MONTHS[int(until[5:7]) - 1]}, {until[11:16]}"


def expected_values(p_by_action: dict, price: float) -> dict:
    """Expected profit of each action, its uplift over doing nothing, and its expected discount (paid only when the
    person buys with it: what a coupon uses of a discount budget)."""
    base = p_by_action["none"] * price
    out = {}
    for a, p in p_by_action.items():
        spec = ACTIONS[a]
        value = p * price * (1 - spec["discount"]) - spec["cost_inr"]
        out[a] = {
            "p_convert": float(p),
            "uplift": float(p - p_by_action["none"]),
            "expected_profit": float(value),
            "incremental_profit": float(value - base),
            "expected_discount": float(p * price * spec["discount"]),
        }
    return out


class FlexibleSLearner:
    """Second model family for the closed loop: gradient boosting on ALL lead features + the action,
    with no hand-designed context. It can pick up effects the interpretable model cannot see (hidden,
    non-linear drivers) but needs more data and cannot be read as per-action effects. The robustness
    study (ml/experiments/nba_robustness.py) shows each family winning in different worlds, so
    the learning loop (learning.py) keeps whichever earns more on held-out REAL decisions."""

    kind = "flexible_gbm"

    def __init__(self, random_state=0):
        self.random_state = random_state

    def _X(self, frame, actions):
        A = np.column_stack([(np.asarray(actions) == t).astype(float) for t in TREATMENTS])
        return np.hstack([self.pre.transform(frame), A])

    def fit(self, frame, actions, y, sample_weight=None):
        from sklearn.compose import ColumnTransformer
        from sklearn.ensemble import HistGradientBoostingClassifier
        from sklearn.preprocessing import OneHotEncoder

        from app.ml import features as F

        self.pre = ColumnTransformer(
            [("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), F.MODEL_CATEGORICAL)],
            remainder="passthrough",
        ).fit(frame)
        self.clf = HistGradientBoostingClassifier(
            learning_rate=0.05,
            max_iter=300,
            max_leaf_nodes=15,
            min_samples_leaf=100,
            early_stopping=True,
            validation_fraction=0.15,
            n_iter_no_change=20,
            random_state=self.random_state,
        )
        self.clf.fit(self._X(frame, actions), y, sample_weight=sample_weight)
        return self

    def predict_all(self, frame) -> dict:
        return {a: self.clf.predict_proba(self._X(frame, np.full(len(frame), a)))[:, 1] for a in ACTION_LIST}


def predict_actions(model, frame: pd.DataFrame, base_prob) -> dict:
    """P(buy | x, a) for every action, for either model family (arrays, one entry per row of frame)."""
    if hasattr(model, "predict_all"):
        return model.predict_all(frame)
    ctx = context(frame, base_prob)
    return {a: model.predict_proba(design(ctx, np.full(len(frame), a)))[:, 1] for a in ACTION_LIST}


def model_kind(model) -> str:
    return getattr(model, "kind", "s_learner_lr")


# how the two model families are named on screen
KIND_LABEL = {"s_learner_lr": "interpretable S-learner", "flexible_gbm": "flexible S-learner (GBM)"}


def model_label(model) -> str:
    kind = model_kind(model)
    return KIND_LABEL.get(kind, kind)


def choose(
    values: dict, blocked: dict, explore_rate: float = 0.0, rng=None, slot_price: float = 0.0, coupon_price: float = 0.0
):
    """Greedy on incremental profit among allowed actions, with epsilon-exploration. The two scarce resources are
    priced: slot_price is what a call slot is worth right now (app.ml.capacity), coupon_price what a rupee of
    discount is worth this month (app.ml.budget, 0 without a budget). A step is picked on its profit net of the
    resources it uses. Returns (action, policy, propensity of the chosen action, the model's best action)."""
    allowed = [a for a in ACTION_LIST if not blocked.get(a)] or ["none"]

    def net(a):
        return (
            values[a]["incremental_profit"]
            - (slot_price if a == "call" else 0.0)
            - coupon_price * values[a].get("expected_discount", 0.0)
        )

    best = max(allowed, key=lambda a: (net(a), a == "none"))
    if net(best) <= 0 and "none" in allowed:
        best = "none"  # nothing pays for itself (when doing nothing is an option, e.g. not at an enquiry)
    rng = rng or np.random.default_rng()
    k = len(allowed)
    if explore_rate > 0 and rng.random() < explore_rate:
        chosen, policy = allowed[int(rng.integers(k))], "explore"
    else:
        chosen, policy = best, "model"
    propensity = (1 - explore_rate) * (chosen == best) + explore_rate / k
    return chosen, policy, float(propensity), best
