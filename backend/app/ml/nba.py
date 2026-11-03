"""
Next-best-action at serving time.

decide()  for one lead at one trigger (cart, checkout, wishlist, visit ended, enquiry): estimate P(buy) under every
          allowed step with the uplift model, pick the step with the best incremental profit (or nothing), with a small
          random exploration share, and log the decision with its propensity. Those logs and later purchases are what
          the learning loop retrains on (app.ml.learning) and what lets the policy be measured honestly
          (inverse-propensity estimates). A call must also beat the price of a call slot (app.ml.capacity), and with
          a monthly discount budget a coupon must beat the price of the discount it uses (app.ml.budget).
The step is carried out by app.services.playbook: an email (with or without a coupon), or a call or WhatsApp task
for the team.
"""

from __future__ import annotations

import json
import logging
import math
import os
import threading

import joblib
import numpy as np

from app import db
from app.core import rules
from app.core.config import get_settings
from app.ml import budget, capacity
from app.ml import features as F
from app.ml import nba_core as N
from app.ml.capacity import CAPACITY_FULL
from app.services import catalog

log = logging.getLogger(__name__)

MODEL_PATH = str(get_settings().model_dir / "nba_model.pkl")
EXPLORE_RATE = float(os.getenv("NBA_EXPLORE_RATE", rules.S["exploration_rate"]))
DAILY_CALL_CAPACITY = capacity.capacity()
COUPON_GAP_DAYS = int(rules.S.get("coupon_gap_days", 7))
CURRENCY = rules.S["business"].get("currency_symbol", "")
WINDOW_DAYS = int(rules.S["outcome_window_days"])

_lock = threading.Lock()
_state = {"bundle": None, "mtime": None, "warned": False}
_rng = np.random.default_rng()


def _load():
    try:
        mtime = os.path.getmtime(MODEL_PATH)
    except OSError:
        if not _state["warned"]:
            log.warning("Uplift model %s not found: using the built-in prior until it is trained", MODEL_PATH)
            _state["warned"] = True
        return None
    if _state["mtime"] != mtime:
        with _lock:
            try:
                _state.update(bundle=joblib.load(MODEL_PATH), mtime=mtime)
                log.info("Loaded uplift model %s", _state["bundle"]["version"])
            except Exception as e:  # noqa: BLE001 - any unreadable model file falls back to the prior
                log.warning("Could not load the uplift model %s (%s): using the built-in prior", MODEL_PATH, e)
                _state.update(bundle=None, mtime=mtime)
    return _state["bundle"]


# Fallback when no trained model exists: conservative prior effects (log-odds)
_PRIOR = {
    "email_info": [0.05, 0, 0, 0, 0, 0, 0.2, 0, 0],
    "email_coupon_10": [0.1, 0, 0.4, -0.2, 0, 0, 0.1, 0, 0],
    "email_coupon_20": [0.2, 0, 0.7, -0.2, 0, 0, 0.1, 0, 0],
    "call": [0.1, 0, 0, 0, 0.7, 0.3, 0, 0, -0.4],
    "whatsapp": [0.1, 0, 0, 0, 0.2, 0, 0, 0.1, 0],
}


def _anchor(probs: dict, base_prob: float) -> dict:
    """The lead model says how likely this person is to buy on their own (the learning loop keeps that
    honest on the control group); the uplift model says how much each action changes it. Every action's
    log-odds are shifted by the same amount so that 'do nothing' equals the lead score exactly: one number
    for 'on their own' everywhere (score, decision table, what-if paths), each action keeping its effect."""
    clip = lambda p: min(max(float(p), 1e-4), 1 - 1e-4)
    d = N._logit([clip(base_prob)])[0] - N._logit([clip(probs["none"])])[0]
    return {a: float(1 / (1 + np.exp(-(N._logit([clip(p)])[0] + d)))) for a, p in probs.items()}


def action_probabilities(features: dict, base_prob: float) -> dict:
    """P(buy within the outcome window | this person, action), for every action."""
    frame = F.to_model_frame([features])
    ctx = N.context(frame, np.array([base_prob]))
    b = _load()
    if b is None:
        base = N._logit([base_prob])[0]
        return {
            a: float(1 / (1 + np.exp(-(base + (np.dot(ctx[0], _PRIOR[a]) if a != "none" else 0)))))
            for a in N.ACTION_LIST
        }
    probs = N.predict_actions(b["model"], frame, np.array([base_prob]))
    return _anchor({a: float(p[0]) for a, p in probs.items()}, base_prob)


def action_probabilities_many(features_list: list, base_probs) -> dict:
    """action_probabilities for many people at once: {action: array}, the same numbers one person at a time gets."""
    frame = F.to_model_frame(features_list)
    base = np.clip(np.asarray(base_probs, dtype=float), 1e-4, 1 - 1e-4)
    b = _load()
    if b is None:
        ctx = N.context(frame, base)
        lb = N._logit(base)
        return {
            a: 1 / (1 + np.exp(-(lb + (ctx @ np.asarray(_PRIOR[a], dtype=float) if a != "none" else 0.0))))
            for a in N.ACTION_LIST
        }
    probs = N.predict_actions(b["model"], frame, base)
    shift = N._logit(base) - N._logit(np.clip(probs["none"], 1e-4, 1 - 1e-4))
    return {a: 1 / (1 + np.exp(-(N._logit(np.clip(p, 1e-4, 1 - 1e-4)) + shift))) for a, p in probs.items()}


def _money(x: float) -> str:
    return f"{CURRENCY}{x:,.0f}"


def _why(action, values, base_p, price, blocked=None, slot_price=None, call_value=None, coupon_price=None):
    """The decision in plain words, in chances of buying (no rupees: the team reads chances, the value behind the
    choice stays inside the decision). Also used by the simulated history. blocked (optional): why steps are not
    possible; then "do nothing" names the reason when nothing else is possible (for example a lead closed as lost).
    slot_price / call_value: the price of a call slot and what a call would add over the best step without one.
    coupon_price is accepted for the callers and not shown."""
    v = values[action]
    slot_note = ""
    if (
        action != "call"
        and slot_price
        and call_value is not None
        and 0 < call_value <= slot_price
        and not (blocked or {}).get("call")
    ):
        slot_note = (
            " A call would raise the chance a little more, but today's call slots are kept for learners a call "
            "helps more."
        )
    if action == "none":
        others = [a for a in values if a != "none" and not (blocked or {}).get(a)]
        if blocked is not None and not others:
            reasons = sorted({blocked[a] for a in values if a != "none" and blocked.get(a)})
            return "No step is possible for this person right now" + (f": {'; '.join(reasons)}." if reasons else ".")
        best_other = max(others, key=lambda a: values[a]["incremental_profit"]) if others else None
        if base_p >= 0.7:
            return (
                f"Likely to buy anyway ({base_p * 100:.0f}% chance with no step): a discount or a call would hardly "
                f"change that." + slot_note
            )
        if best_other is None:
            return "No step is possible for this person right now."
        o = values[best_other]
        return (
            f"No step is worth taking right now: the best one ({N.ACTIONS[best_other]['label'].lower()}) would "
            f"change the chance of buying by only {o['uplift'] * 100:+.1f} points, too little for its cost"
            + (" and its discount" if N.ACTIONS[best_other]["discount"] else "")
            + "."
            + slot_note
        )
    disc = N.ACTIONS[action]["discount"]
    p_from, p_to = values["none"]["p_convert"] * 100, v["p_convert"] * 100
    verb = "Expected to lower" if v["uplift"] < 0 else "Raises"
    change = (
        f"{verb} the chance of buying within {WINDOW_DAYS} days from {p_from:.0f}% to {p_to:.0f}% "
        f"({v['uplift'] * 100:+.1f} points)."
    )
    if v["incremental_profit"] >= 0:
        reason = (
            f" The extra buyers it brings outweigh the {int(disc * 100)}% discount, which also goes to anyone who "
            "would have bought anyway."
            if disc
            else ""
        )
        if action == "call" and slot_price:
            reason += " A call slot is used because a call helps this learner more than most."
    else:
        reason = " On its own it is not worth its cost" + (
            " (the discount would mostly go to people who would buy anyway)." if disc else "."
        )
    return change + reason + slot_note


def model_version():
    b = _load()
    return b["version"] if b else "prior"


# how a step that a follow-up does not use is described on the receipt ("not used after a visit")
TRIGGER_PHRASE = {
    "session_end": "after a visit",
    "enquiry": "for an enquiry",
    "wishlist": "for a wishlist reminder",
    "cart_abandon": "for a left cart",
    "checkout_abandon": "for a left checkout",
    "signup": "right after sign-up",
}


def evaluate(user_id, pred, course_slug=None, allowed=None, trigger=None):
    """What every possible step is worth for this person now: chance to buy, change against doing nothing, extra
    profit, why a step is not allowed, and the price of a call slot. The one calculation behind the automatic
    decisions, the lead page's recommendation and the what-if paths, so they can never disagree."""
    features = pred["features"]
    profile = db.get_profile(user_id) or {}
    has_phone = bool((profile.get("phone") or "").strip())
    base_p = float(pred["conversion_probability"])
    price = catalog.price_of(course_slug) or catalog.average_price()
    probs = action_probabilities(features, base_p)
    values = N.expected_values(probs, price)
    blocked = N.eligible(features, has_phone)
    slot_price, used = capacity.price_now()
    if used >= DAILY_CALL_CAPACITY and not blocked["call"]:
        blocked["call"] = CAPACITY_FULL
    coupon_price, budget_left = budget.price_now()
    if budget_left is not None and budget_left <= 0:
        for a in budget.COUPONS:
            if not blocked[a]:
                blocked[a] = budget.BUDGET_USED_UP
    if allowed is not None:
        for a in N.ACTION_LIST:
            if a not in allowed and not blocked[a]:
                blocked[a] = f"not used {TRIGGER_PHRASE.get(trigger, 'for this follow-up')}"
    if (pred.get("raw", {}).get("past_purchases") or 0) > 0:
        blocked["email_coupon_20"] = blocked["email_coupon_20"] or "existing customer"
    held = N.coupon_block_reason(db.open_coupon(user_id), db.recent_coupon(user_id, COUPON_GAP_DAYS), COUPON_GAP_DAYS)
    if held:  # one open coupon per person, and at most one coupon every COUPON_GAP_DAYS days
        for a in N.COUPON_ACTIONS:
            blocked[a] = blocked[a] or held
    lost = db.lost_status(user_id)
    if lost:  # the team closed this lead as lost: no automatic steps until someone re-opens it
        why = "closed as lost by the team" + (f" ({lost['reason'].lower()})" if lost.get("reason") else "")
        for a in N.ACTION_LIST:
            if a != "none":
                blocked[a] = why
    if all(blocked[a] for a in N.ACTION_LIST):
        blocked["none"] = None  # nothing else is possible (opted out everywhere): do nothing
    call_value = capacity.call_advantage(values, blocked)
    if call_value is None or blocked.get("call") or math.isinf(slot_price):
        slot_price = None
    adv = budget.coupon_advantage(values, blocked, slot_price or 0.0)
    coupon_value, coupon_cost = (adv[0], adv[1]) if adv else (None, None)
    if adv is None or all(blocked.get(a) for a in budget.COUPONS) or not math.isfinite(coupon_price):
        coupon_price = 0.0
    options = [
        {
            "action": a,
            "label": N.ACTIONS[a]["label"],
            "blocked": blocked[a],
            "discount": N.ACTIONS[a]["discount"],
            "cost": N.ACTIONS[a]["cost_inr"],
            **values[a],
        }
        for a in N.ACTION_LIST
    ]
    for o in options:
        if o["action"] == "call" and slot_price is not None:
            o["slot_price"] = round(slot_price, 2)
            o["net_of_slot"] = round(o["incremental_profit"] - slot_price, 2)
        if o["action"] in budget.COUPONS and coupon_price > 0:
            o["budget_price"] = round(coupon_price, 4)
            o["net_of_budget"] = round(o["incremental_profit"] - coupon_price * o["expected_discount"], 2)
    return {
        "features": features,
        "base_p": base_p,
        "price": price,
        "probs": probs,
        "values": values,
        "blocked": blocked,
        "has_phone": has_phone,
        "options": options,
        "slot_price": slot_price,
        "call_value": call_value,
        "calls_today": used,
        "coupon_price": coupon_price,
        "coupon_value": coupon_value,
        "coupon_cost": coupon_cost,
        "budget_left": budget_left,
    }


def best_action(ev):
    """The step the model picks (no random exploration): highest extra profit, a call net of its slot price and a
    coupon net of the price of its discount (with a discount budget)."""
    _, _, _, best = N.choose(
        ev["values"],
        ev["blocked"],
        0.0,
        _rng,
        slot_price=ev.get("slot_price") or 0.0,
        coupon_price=ev.get("coupon_price") or 0.0,
    )
    return best


def decide(user_id, trigger, pred, course_slug=None, explore=True, allowed=None, lead_id=None, force_action=None):
    """Choose the next best action for this lead and log the decision.
    force_action: a step a person on the team chose by hand ("Take this step" on the lead page). It is carried out
    and logged like any decision (policy 'manual'), so the learning loop is told about it too."""
    ev = evaluate(user_id, pred, course_slug, allowed=allowed, trigger=trigger)
    values, blocked, base_p, price = ev["values"], ev["blocked"], ev["base_p"], ev["price"]
    slot_price, call_value = ev["slot_price"], ev["call_value"]
    coupon_price = ev.get("coupon_price") or 0.0
    holdout = rules.in_global_control(user_id)
    if force_action is not None:
        if force_action not in N.ACTIONS:
            raise ValueError(f"Unknown step '{force_action}'.")
        # the capacity limits the CRM's own call tasks; a person on the team may still decide to call
        if blocked.get(force_action) and blocked[force_action] != CAPACITY_FULL:
            raise ValueError(f"Not possible for this person: {blocked[force_action]}.")
        if holdout:
            raise ValueError(
                "This person is in the control group: the CRM never contacts them, so their outcome "
                "shows what happens without us."
            )
        best = best_action(ev)
        action, policy, propensity = force_action, "manual", 1.0
    else:
        action, policy, propensity, best = N.choose(
            values,
            blocked,
            EXPLORE_RATE if explore else 0.0,
            _rng,
            slot_price=slot_price or 0.0,
            coupon_price=coupon_price,
        )
        if holdout:  # the untouched control group: decide (for the record) but never act
            action, policy, propensity = "none", "holdout", 1.0
    b = _load()
    options = ev["options"]
    label = N.ACTIONS[best]["label"]
    first = label.split(" ", 1)[0]
    # inside a sentence: "send email with 20% coupon", but "WhatsApp message" stays as it is
    best_label = label if any(c.isupper() for c in first[1:]) else label[:1].lower() + label[1:]
    if holdout:
        why = (
            f"In the {rules.S['global_control']['share']:.0%} control group: the CRM never contacts this lead "
            f"automatically, so what they do shows what happens without us. (The model would have chosen: "
            f"{best_label}.)"
        )
    elif policy == "manual":
        why = (
            "Chosen by hand. "
            + _why(action, values, base_p, price, blocked)
            + ("" if action == best else f" (The model's own pick: {best_label}.)")
        )
    else:
        why = _why(action, values, base_p, price, blocked, slot_price, call_value, coupon_price)
        if policy == "explore" and action != best:
            why += (
                f" (Chosen at random as part of the {EXPLORE_RATE:.0%} learning sample; the model's own pick: "
                f"{best_label}.)"
            )
    version = b["version"] if b else "prior"
    decision = {
        "action": action,
        "label": N.ACTIONS[action]["label"],
        "policy": policy,
        "propensity": propensity,
        "model_best": best,
        "model_best_label": N.ACTIONS[best]["label"],
        "trigger": trigger,
        "why": why,
        "detail": f"Course price {_money(price)}, uplift model {version}, trigger {trigger}",
        "options": options,
        "model_version": version,
        "price": price,
        "base_probability": base_p,
        "lead_model_version": pred.get("model_version"),
        "slot_price": slot_price,
        "call_value": call_value,
        "budget_price": coupon_price or None,
        "coupon_value": ev.get("coupon_value"),
        "coupon_cost": ev.get("coupon_cost"),
    }
    decision["decision_id"] = db.execute(
        """
        INSERT INTO nba_decisions (user_id, lead_id, trigger_reason, action, model_best, policy, propensity,
                                   base_probability, price, options_json, features_json, model_version,
                                   slot_price, call_value, coupon_value, coupon_cost, budget_price)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            user_id,
            lead_id,
            trigger,
            action,
            best,
            policy,
            propensity,
            base_p,
            price,
            json.dumps(options),
            json.dumps(ev["features"]),
            version,
            slot_price,
            call_value,
            ev.get("coupon_value"),
            ev.get("coupon_cost"),
            coupon_price or None,
        ),
    )
    return decision


# a step taken by hand is not taken again for the same person within this many hours (an email or coupon twice in a
# row only annoys); calls and WhatsApp wait while their task is still open in Today's actions
REPEAT_HOURS = float(rules.S["cooldown_hours"].get("manual_repeat", 24))


def _when(ts: str) -> str:
    """'today at 18:47' or 'on 26 Oct at 18:47' for a stored local time."""
    today = db.fetchone("SELECT date('now','localtime') AS d")["d"]
    day = "today" if ts[:10] == today else f"on {int(ts[8:10])} {N.MONTHS[int(ts[5:7]) - 1]}"
    return f"{day} at {ts[11:16]}"


def recent_steps(user_id) -> dict:
    """{action: why it cannot be taken by hand again yet} for this person: the same email step in the last
    REPEAT_HOURS hours, or a call or WhatsApp task that is still open."""
    out = {}
    rows = db.fetchall(
        """SELECT action, MAX(created_at) AS at, datetime(MAX(created_at), ?) AS again FROM nba_decisions
            WHERE user_id=? AND action LIKE 'email%' AND created_at >= datetime('now','localtime',?)
            GROUP BY action""",
        (f"+{REPEAT_HOURS:g} hours", user_id, f"-{REPEAT_HOURS:g} hours"),
    )
    for r in rows:
        out[r["action"]] = (
            f"{N.ACTIONS[r['action']]['label']}: already done {_when(r['at'])}. The same step can be taken again "
            f"{_when(r['again'])}."
        )
    for r in db.fetchall("SELECT task_type, created_at FROM sales_tasks WHERE user_id=? AND status='open'", (user_id,)):
        action = {"call": "call", "whatsapp": "whatsapp"}.get(r["task_type"])
        if action:
            out[action] = (
                f"{'A call' if action == 'call' else 'A WhatsApp message'} is already waiting in Today's actions "
                f"(added {_when(r['created_at'])})."
            )
    return out


def recommend_now(user_id):
    """What the CRM would do for this person if a step were taken right now (nothing is logged or sent).
    Same calculation as an automatic decision (evaluate), on the person as they are now: current behaviour,
    time since their last visit, current models. Used by the lead page and the what-if paths."""
    from app.ml.predict import predict_lead
    from app.services import scoring

    user = db.get_user_by_id(user_id)
    if not user:
        return None
    purchases = db.get_purchases(user_id)
    owned = {p["course_slug"] for p in purchases}
    cart = [c for c in db.get_cart(user_id) if c["course_slug"] not in owned]
    base = {
        "user_id": user_id,
        "name": user["name"],
        "control_group": rules.in_global_control(user_id),
        "customer": bool(purchases),
        "away_days": scoring.days_since(scoring.last_seen(user_id)),
        "purchases": [
            {
                "course": p["course_title"],
                "course_slug": p["course_slug"],
                "paid": p["price_paid"],
                "coupon": p.get("coupon_used"),
                "at": p["purchased_at"],
            }
            for p in purchases
        ],
        "lead_model": None,
        "nba_model": model_version(),
    }
    if purchases and not cart:
        return {
            **base,
            "recommendation": None,
            "message": (
                f"{user['name']} is a customer (bought {purchases[0]['course_title']}). The CRM does not "
                "chase customers for a course they own; it acts again only if they put another course in "
                "the cart."
            ),
        }
    slug = cart[0]["course_slug"] if cart else scoring.interest_slug(user_id)
    if slug in owned:
        slug = None
    raw = scoring.build_raw(user_id, course=slug, recency=True)
    pred = predict_lead(raw, explain=True)
    pred["raw"] = raw
    ev = evaluate(user_id, pred, slug)
    best = best_action(ev)
    tips = []
    try:
        from app.ml import recourse

        tips = recourse.tips_for(pred["features"], pred["lead_score"], lead_age_days=pred.get("lead_age_days"))
    except Exception:  # noqa: BLE001 - tips are optional on the page
        log.debug("No tips for user %s", user_id, exc_info=True)
    return {
        **base,
        "lead_model": pred["model_version"],
        "course": {"slug": slug, "title": catalog.title_of(slug) if slug else None, "price": ev["price"]},
        "score": pred["lead_score"],
        "probability": pred["conversion_probability"],
        "tier": pred["recommended_action"],
        "away_days": pred.get("away_days"),
        "lead_age_days": pred.get("lead_age_days"),
        "factors": pred.get("factors") or [],
        "tips": tips,
        "features": ev["features"],
        "options": ev["options"],
        "slot_price": ev["slot_price"],
        "call_value": ev["call_value"],
        "calls_today": ev["calls_today"],
        "recommendation": {
            "action": best,
            "label": N.ACTIONS[best]["label"],
            "why": _why(
                best,
                ev["values"],
                ev["base_p"],
                ev["price"],
                ev["blocked"],
                ev["slot_price"],
                ev["call_value"],
                ev.get("coupon_price"),
            ),
            "extra_profit": ev["values"][best]["incremental_profit"],
            "p_buy": ev["values"][best]["p_convert"],
        },
    }


def offer_pct(action):
    return int(round(N.ACTIONS[action]["discount"] * 100))


def attach_to_lead(lead_id, decision):
    db.execute(
        "UPDATE leads SET nba_action=?, nba_json=? WHERE id=?",
        (decision["action"], json.dumps({k: v for k, v in decision.items()}), lead_id),
    )
    db.execute("UPDATE nba_decisions SET lead_id=? WHERE id=?", (lead_id, decision["decision_id"]))


def create_task(user_id, lead_id, decision, title, detail):
    ch = N.ACTIONS[decision["action"]]["channel"]
    gain = next(o["incremental_profit"] for o in decision["options"] if o["action"] == decision["action"])
    existing = db.fetchone(
        "SELECT id, expected_gain FROM sales_tasks WHERE user_id=? AND task_type=? AND status='open'", (user_id, ch)
    )
    if existing:  # one open call or WhatsApp task per person: refresh it instead of making another
        db.execute(
            "UPDATE sales_tasks SET lead_id=?, decision_id=?, title=?, detail=?, expected_gain=? WHERE id=?",
            (
                lead_id,
                decision["decision_id"],
                title,
                detail,
                max(gain, existing["expected_gain"] or 0),
                existing["id"],
            ),
        )
        return existing["id"]
    task_id = db.execute(
        """INSERT INTO sales_tasks (user_id, lead_id, decision_id, task_type, title, detail,
                                                     expected_gain)
                            VALUES (?,?,?,?,?,?,?)""",
        (user_id, lead_id, decision["decision_id"], ch, title, detail, gain),
    )
    return task_id


def mark_executed(decision_id):
    db.execute("UPDATE nba_decisions SET executed_at=datetime('now','localtime') WHERE id=?", (decision_id,))
