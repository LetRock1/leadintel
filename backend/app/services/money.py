"""
The money view of the pipeline, and the coupon guard.

A standard CRM weights its pipeline by each lead's chance to close: fee x probability. That number mixes two different
things: revenue that will come in whatever the team does, and revenue the team's next step will add. It cannot tell
the team where its effort pays, and when the CRM retrains on outcomes its own follow-ups shaped, the probability
itself counts the team's work as lead quality.

Here the lead score is the chance to buy within the outcome window if the team does nothing now (the learning loop
keeps it honest on leads nobody contacts), and next-best-action knows what each step adds. So every open lead gets
two numbers, computed for the whole board at once with exactly the calculation of a single decision
(app.ml.nba.evaluate), call slots and discount money priced:

    comes in anyway      P(buy | no step now) x course fee
    the team can add     the extra profit of the best step now: after its cost and any discount, 0 when no step pays

and a plain label: Work this (a step pays), Buys anyway (more likely than not to buy without help, and no step
pays), No step pays now, Control group (never contacted: it shows what happens without the CRM), Can't be
contacted (no allowed channel), Lost, Customer. A lead more likely than not to buy anyway is also flagged "no
discount needed": the profit calculation never picks a coupon for them, while a tier rule ("hot leads get the best
offer") would.

The coupon guard uses the same numbers for coupons given by hand: a coupon for a learner who would buy anyway gives
money away, and the guard says how much before anyone confirms it. ``kept`` measures what the CRM's coupon decisions
kept, against the usual cart-recovery rule (a coupon for every left cart or checkout).
"""

from __future__ import annotations

import json
import logging
import math
import threading
import time
from datetime import datetime, timedelta

import numpy as np

from app import db
from app.core import rules
from app.ml import budget, capacity, nba
from app.ml import nba_core as N
from app.services import catalog

log = logging.getLogger(__name__)

WINDOW_DAYS = int(rules.S["outcome_window_days"])
ANYWAY = 0.5  # more likely than not to buy with no step
CACHE_SECONDS = 30
TS = "%Y-%m-%d %H:%M:%S"
_cache: dict = {"at": 0.0, "values": None}
_lock = threading.Lock()
_rng = np.random.default_rng(0)

SEGMENT_LABEL = {
    "work": "Work this",
    "anyway": "Buys anyway",
    "wait": "No step pays now",
    "control": "Control group",
    "unreachable": "Can't be contacted",
    "lost": "Lost",
    "customer": "Customer",
}


def _blocked_for(features, has_phone, past_purchases, lost, calls_full, budget_used_up, held=None, recent=None):
    """Why each step is not possible for this person now: the rules of nba.evaluate, for any trigger. held: the open
    coupon they still hold (no second coupon while it can be used)."""
    blocked = N.eligible(features, has_phone)
    if calls_full and not blocked["call"]:
        blocked["call"] = capacity.CAPACITY_FULL
    if budget_used_up:
        for a in budget.COUPONS:
            if not blocked[a]:
                blocked[a] = budget.BUDGET_USED_UP
    if past_purchases > 0:
        blocked["email_coupon_20"] = blocked["email_coupon_20"] or "existing customer"
    held_why = N.coupon_block_reason(held, recent, nba.COUPON_GAP_DAYS)
    if held_why:
        for a in N.COUPON_ACTIONS:
            blocked[a] = blocked[a] or held_why
    if lost:
        why = "closed as lost by the team"
        for a in N.ACTION_LIST:
            if a != "none":
                blocked[a] = why
    if all(blocked[a] for a in N.ACTION_LIST):
        blocked["none"] = None
    return blocked


def compute(user_ids=None) -> dict:
    """{user_id: money view} for these people (default: everyone with a lead record), all at once."""
    from app.ml import predict
    from app.services import scoring

    if user_ids is None:
        user_ids = [r["user_id"] for r in db.fetchall("SELECT DISTINCT user_id FROM leads")]
    ids = sorted({int(u) for u in user_ids})
    if not ids:
        return {}
    raws = scoring.build_raw_many(ids)
    carts: dict[int, list[str]] = {}
    for r in db.fetchall("SELECT user_id, course_slug FROM cart ORDER BY added_at DESC"):
        carts.setdefault(r["user_id"], []).append(r["course_slug"])
    owned: dict[int, set] = {}
    for r in db.fetchall("SELECT user_id, course_slug FROM purchases"):
        owned.setdefault(r["user_id"], set()).add(r["course_slug"])
    phones = {
        r["user_id"]: bool((r["phone"] or "").strip()) for r in db.fetchall("SELECT user_id, phone FROM user_profiles")
    }
    lost = {r["user_id"] for r in db.fetchall("SELECT user_id FROM pipeline_overrides WHERE stage='Lost'")}
    held = db.open_coupons()
    recent = db.recent_coupons(nba.COUPON_GAP_DAYS)
    slot_price, used = capacity.price_now()
    calls_full = used >= capacity.capacity()
    coupon_price, left = budget.price_now()
    budget_used_up = left is not None and left <= 0
    avg_price = catalog.average_price()

    out, todo, slugs = {}, [], {}
    for u in ids:
        cart = [s for s in carts.get(u, []) if s not in owned.get(u, set())]
        if u in owned and not cart:
            out[u] = {"segment": "customer"}
            continue
        slug = cart[0] if cart else (raws[u].get("_top_course_slug") or None)
        if slug in owned.get(u, set()):
            slug = None
        raws[u]["CourseType"] = slug  # as scoring.build_raw(course=slug)
        slugs[u] = slug
        todo.append(u)
    features, probs = predict.features_and_probs([raws[u] for u in todo])
    P = nba.action_probabilities_many(features, probs) if todo else {}
    for i, u in enumerate(todo):
        slug = slugs[u]
        price = float(catalog.price_of(slug) or avg_price)
        base_p = probs[i]
        values = N.expected_values({a: float(P[a][i]) for a in N.ACTION_LIST}, price)
        blocked = _blocked_for(
            features[i],
            phones.get(u, False),
            raws[u].get("past_purchases") or 0,
            u in lost,
            calls_full,
            budget_used_up,
            held.get(u),
            recent.get(u),
        )
        call_value = capacity.call_advantage(values, blocked)
        sp = slot_price if (call_value is not None and not blocked.get("call") and math.isfinite(slot_price)) else 0.0
        cp = coupon_price if math.isfinite(coupon_price) else 0.0
        _, _, _, best = N.choose(values, blocked, 0.0, _rng, slot_price=sp, coupon_price=cp)
        add = float(values[best]["incremental_profit"]) if best != "none" else 0.0
        # no discount needed: more likely than not to buy anyway, and no coupon would add profit (what the coupon
        # guard would say to a coupon given by hand)
        no_discount = base_p >= ANYWAY and all(values[c]["incremental_profit"] <= 0 for c in budget.COUPONS)
        control = rules.in_global_control(u)
        if control:
            segment = "control"
        elif u in lost:
            segment = "lost"
        elif all(blocked.get(a) for a in N.ACTION_LIST if a != "none"):
            segment = "unreachable"
        elif best != "none" and add > 0:
            segment = "work"
        elif base_p >= ANYWAY:
            segment = "anyway"
        else:
            segment = "wait"
        out[u] = {
            "segment": segment,
            "p_anyway": round(base_p, 4),
            "price": round(price, 2),
            "course_slug": slug,
            "anyway": round(base_p * price, 2),
            "best": best if segment == "work" else "none",
            "best_label": N.ACTIONS[best]["label"] if segment == "work" else None,
            "add": round(add, 2) if segment == "work" else 0.0,
            "p_with_step": round(float(values[best]["p_convert"]), 4) if segment == "work" else None,
            "no_discount": bool(no_discount) and not control,
        }
    return out


def board_values(fresh: bool = False) -> dict:
    """compute() for everyone, kept for CACHE_SECONDS (the pipeline board asks every 30 seconds). Someone who became
    a lead after the last full run (signed up a moment ago) is worked out at once and added, so a new lead never shows
    an empty money line, or is left out of the totals, while the rest waits for the next refresh."""
    with _lock:
        if fresh or _cache["values"] is None or time.time() - _cache["at"] > CACHE_SECONDS:
            started = time.perf_counter()
            _cache.update(values=compute(), at=time.time())
            log.debug("Money view of %d leads in %.2f s", len(_cache["values"]), time.perf_counter() - started)
        else:
            known = _cache["values"]
            missing = [
                r["user_id"] for r in db.fetchall("SELECT DISTINCT user_id FROM leads") if r["user_id"] not in known
            ]
            if missing:
                _cache["values"] = {**known, **compute(missing)}
        return _cache["values"]


def reset_cache() -> None:
    with _lock:
        _cache.update(values=None, at=0.0)


def totals(values: dict | None = None) -> dict:
    """The whole pipeline in rupees over the next outcome window: what comes in anyway, what the team can add, how
    many leads to work."""
    values = board_values() if values is None else values
    open_ = [v for v in values.values() if v["segment"] not in ("customer", "lost")]
    work = [v for v in open_ if v["segment"] == "work"]
    by_step: dict[str, dict] = {}
    for v in work:
        s = by_step.setdefault(v["best"], {"label": v["best_label"], "leads": 0, "add": 0.0})
        s["leads"] += 1
        s["add"] += v["add"]
    return {
        "window_days": WINDOW_DAYS,
        "open_leads": len(open_),
        "anyway": round(sum(v["anyway"] for v in open_)),
        "add": round(sum(v["add"] for v in work)),
        # in buyers, which is what the CRM shows: expected buyers if the team does nothing, and how many more the
        # best steps add (the rupee figures above stay for the decisions and the research)
        "buyers_anyway": round(sum(v["p_anyway"] for v in open_ if v.get("p_anyway") is not None), 1),
        "buyers_add": round(sum((v["p_with_step"] or 0) - v["p_anyway"] for v in work), 1),
        "work": len(work),
        "buys_anyway": sum(v["segment"] == "anyway" for v in open_),
        "no_discount": sum(bool(v.get("no_discount")) for v in open_),
        "by_step": {k: {**s, "add": round(s["add"])} for k, s in sorted(by_step.items(), key=lambda kv: -kv[1]["add"])},
    }


# The coupon guard (coupons given by hand)
def coupon_check(user_id: int, pct: int) -> dict:
    """What a personal coupon of pct% would do for this learner, from the same numbers as next-best-action: their
    chance to buy without it and with it, the discount it would give away, the profit it adds, and a verdict."""
    now = nba.recommend_now(user_id)
    if now is None:
        raise LookupError("Learner not found")
    name = now["name"]
    if now["control_group"]:
        return {
            "verdict": "control",
            "allowed": False,
            "message": (
                f"{name} is in the control group: the CRM never contacts them, so their outcome shows what happens "
                "without us. A coupon would spoil that check."
            ),
        }
    if now.get("recommendation") is None:
        return {
            "verdict": "customer",
            "allowed": True,
            "message": now.get("message") or f"{name} is already a customer.",
        }
    recent = db.recent_coupon(user_id, nba.COUPON_GAP_DAYS)
    if recent and not db.open_coupon(user_id):  # the last coupon expired or was used, but only days ago
        return {
            "verdict": "has_coupon",
            "allowed": False,
            "message": (
                f"{name} {N.coupon_block_reason(None, recent, nba.COUPON_GAP_DAYS)}: "
                f"{recent['coupon_code']} ({int(recent['discount_pct'])}% off). Coupons that come too often teach "
                "people to wait for the next one."
            ),
            "name": name,
            "coupon_code": recent["coupon_code"],
            "discount_pct": int(recent["discount_pct"]),
            "expires_at": recent["expires_at"],
        }
    held = db.open_coupon(user_id)
    if held:  # one open coupon per person, whoever gave it: discounts never stack on one purchase
        return {
            "verdict": "has_coupon",
            "allowed": False,
            "message": (
                f"{name} already holds the coupon {held['coupon_code']} ({int(held['discount_pct'])}% off"
                + (f", {N.coupon_until(held)}" if N.coupon_until(held) else "")
                + "). One open coupon per person, so discounts never stack: withdraw it in the list first to give "
                "a different one."
            ),
            "name": name,
            "coupon_code": held["coupon_code"],
            "discount_pct": int(held["discount_pct"]),
            "expires_at": held["expires_at"],
        }
    opts = {o["action"]: o for o in now["options"]}
    nearest = "email_coupon_10" if pct <= 15 else "email_coupon_20"
    price = float(now["course"]["price"])
    p0 = float(now["probability"])
    p1 = float(opts[nearest]["p_convert"])  # the model's chance with a coupon of about this size
    d = pct / 100.0
    expected_discount = p1 * price * d
    extra_profit = p1 * price * (1 - d) - p0 * price
    anyway_share = min(p0 / p1, 1.0) if p1 > 0 else 1.0
    b = budget.state()
    over_budget = b["left"] is not None and expected_discount > max(b["left"], 0.0)
    pays = extra_profit > 0
    course = now["course"]["title"] or "a course"
    if pays and not over_budget:
        verdict, msg = (
            "pays",
            f"A {pct}% coupon is worth giving: it raises {name}'s chance to buy {course} from {p0 * 100:.0f}% to "
            f"{p1 * 100:.0f}%, enough extra buyers to make up for the discount.",
        )
    elif not pays:
        verdict = "costs"
        if p1 <= p0:
            msg = (
                f"A {pct}% coupon is not expected to raise {name}'s {p0 * 100:.0f}% chance to buy {course}, so the "
                "discount would be given away for nothing."
            )
        elif anyway_share >= 0.5:
            msg = (
                f"{name} has a {p0 * 100:.0f}% chance to buy {course} without a coupon, and {p1 * 100:.0f}% with a "
                f"{pct}% coupon: {anyway_share * 100:.0f}% of the discount would go to someone who would have paid "
                "in full."
            )
        else:
            msg = (
                f"A {pct}% coupon would raise {name}'s chance to buy {course} only from {p0 * 100:.0f}% to "
                f"{p1 * 100:.0f}%, not enough extra buyers to make up for the discount."
            )
    else:
        verdict, msg = (
            "over_budget",
            "This coupon would go over what is left of this month's discount budget.",
        )
    return {
        "verdict": verdict,
        "allowed": verdict == "pays",
        "message": msg,
        "name": name,
        "course": course,
        "price": price,
        "p_without": round(p0, 4),
        "p_with": round(p1, 4),
        "expected_discount": round(expected_discount, 2),
        "extra_profit": round(extra_profit, 2),
        "anyway_share": round(anyway_share, 3),
        "budget_left": None if b["left"] is None else round(b["left"], 2),
        "note": None
        if pct in (10, 20)
        else (
            f"The CRM has learned what 10% and 20% coupons do; for {pct}% it uses the "
            f"{N.ACTIONS[nearest]['discount'] * 100:.0f}% coupon's effect, so treat the numbers as rough."
        ),
    }


# What the coupon decisions kept
def kept(days: int = 7, now: datetime | None = None) -> dict:
    """At left carts and checkouts in the last `days`: the discount the usual cart-recovery rule (a coupon for every
    left cart or checkout, 10%) would have given to people who were going to buy anyway, against what the CRM's own
    decisions gave them. From the honest score, so it is an estimate; the coupons actually used are counted too."""
    now = now or datetime.now()
    since = (now - timedelta(days=days)).strftime(TS)
    rows = db.fetchall(
        """SELECT action, base_probability AS p, price, options_json FROM nba_decisions
           WHERE created_at >= ? AND trigger_reason IN ('cart_abandon', 'checkout_abandon')
                 AND COALESCE(policy, '') IN ('model', 'explore')""",
        (since,),
    )
    usual = ours = 0.0
    usual_n = ours_n = 0
    for r in rows:
        p, price = float(r["p"] or 0.0), float(r["price"] or 0.0)
        try:
            opts = {o["action"]: o for o in json.loads(r["options_json"] or "[]")}
        except ValueError:
            continue
        if "email_coupon_10" in opts and not opts["email_coupon_10"].get("blocked"):
            usual += p * price * 0.10
            usual_n += 1
        if r["action"] in budget.COUPONS:
            ours += p * price * N.ACTIONS[r["action"]]["discount"]
            ours_n += 1
    given = db.fetchone(
        """SELECT COUNT(*) AS n, COALESCE(SUM(discount_amount), 0) AS d FROM purchases
           WHERE purchased_at >= ? AND discount_amount > 0""",
        (since,),
    )
    return {
        "days": days,
        "decisions": len(rows),
        "usual": {"coupons": usual_n, "to_buyers_anyway": round(usual)},
        "ours": {"coupons": ours_n, "to_buyers_anyway": round(ours)},
        "kept": round(usual - ours),
        "discount_given": round(float(given["d"] or 0.0)),
        "purchases_with_discount": int(given["n"] or 0),
    }
