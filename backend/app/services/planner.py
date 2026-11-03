"""
The owner's planner: the month in rupees, what the team's work adds, and what one more counsellor or more discount
money would add, read from the CRM's own decisions.

The CRM already prices its two scarce resources at every decision: a call slot (app.ml.capacity) and, with a monthly
discount budget, a rupee of discount (app.ml.budget). Those prices come from the last week of decisions, each with
what a call or a coupon would have added over the best step without it. The same log answers the owner's questions:

    one more counsellor      last week's decisions replayed with k more call slots a day: the extra calls the
                             CRM's own rule would then have made, each worth what it adds over the best step
                             without a call
    a bigger budget          the coupons with the next best profit per rupee of discount that would then fit
    what the team adds       the share who bought among people the CRM worked on against its untouched control group
                             (measured, with a 95% interval), and what that difference is worth

Every number is an estimate from the CRM's own recent decisions and says so. ml/experiments/money_check.py (E9)
checks the counsellor estimate against the profit the extra slots really add in simulations with known effects.
"""

from __future__ import annotations

from datetime import datetime

from app import db
from app.core import rules
from app.ml import budget, capacity
from app.services import analytics, catalog, money

CONF = {"counsellor_daily_calls": 8, "counsellor_monthly_cost": 35000, **(rules.S.get("planner") or {})}
COST_KEY = "counsellor_monthly_cost"
TS = "%Y-%m-%d %H:%M:%S"
EXTRA_BUDGET = 10_000


def counsellor_cost() -> float:
    v = db.app_setting(COST_KEY)
    try:
        return float(v) if v not in (None, "") else float(CONF["counsellor_monthly_cost"])
    except ValueError:
        return float(CONF["counsellor_monthly_cost"])


def save_settings(monthly_budget: float | None, monthly_cost: float | None) -> None:
    budget.set_monthly_budget(monthly_budget)
    if monthly_cost is not None:
        db.put_app_setting(COST_KEY, f"{float(monthly_cost):.2f}")
    money.reset_cache()


def _replayed(pricer: capacity.SlotPricer, slots: int) -> float:
    """What the CRM's own call rule would have added per day with `slots` call slots, replayed on the look-back
    window: on each day, the decisions in time order, a call whenever its advantage beats the re-solved slot price
    for the slots still left that day (app.ml.capacity), until they are used up."""
    if slots <= 0 or not pricer.days:
        return 0.0
    by_day: dict = {}
    for a, t, d in zip(pricer.advantages, pricer.tods, pricer.day_of):
        by_day.setdefault(d, []).append((t, a))
    total = 0.0
    for items in by_day.values():
        used = 0
        for t, a in sorted(items):
            if used >= slots:
                break
            if a > 0 and a > pricer.price(slots - used, t):
                used += 1
                total += a
    return total / pricer.days


def slots_value(pricer: capacity.SlotPricer, slots_now: int, extra: int) -> float:
    """What `extra` more call slots a day would add per day: last week's decisions replayed with slots_now and with
    slots_now + extra slots (the extra calls the CRM's own rule would then have made, each worth what it adds over
    the best step without a call). A replay rather than a ranking, because the rule keeps some slots for calls that
    may still come later in the day: with more slots it holds back less (ml/experiments/money_check.py, E9).
    Without the day of each decision, the window's calls are ranked together."""
    if not pricer.days or not pricer._pos:
        return 0.0
    if len(pricer.day_of) != len(pricer.advantages):
        lo, hi = slots_now * pricer.days, (slots_now + extra) * pricer.days
        return float(sum(pricer._pos[lo:hi])) / pricer.days
    return max(_replayed(pricer, slots_now + extra) - _replayed(pricer, slots_now), 0.0)


def overview(now: datetime | None = None) -> dict:
    now = now or datetime.now()
    start, end = budget.month_bounds(now)
    days_in_month = (end - start).days
    month = db.fetchone(
        """SELECT COUNT(*) AS n, COALESCE(SUM(price_paid), 0) AS revenue, COALESCE(SUM(discount_amount), 0) AS discount
           FROM purchases WHERE purchased_at >= ?""",
        (start.strftime(TS),),
    )
    avg_paid = (
        db.fetchone(
            "SELECT AVG(price_paid) AS a FROM purchases WHERE purchased_at >= datetime('now','localtime','-90 days')"
        )["a"]
        or catalog.average_price()
    )

    # what the team's work adds, measured against the untouched control group
    impact = analytics.crm_impact()
    team = {"days": impact["days"], "worked_on": impact["worked_on"], "control": impact["control"]}
    if impact.get("lift") is not None and impact["worked_on"]["rate"]:
        people, rate = impact["worked_on"]["people"], impact["worked_on"]["rate"]
        lo, hi = impact["lift_ci"]
        team.update(
            lift=impact["lift"],
            lift_ci=[lo, hi],
            revenue=round(impact["lift"] * people * avg_paid),
            revenue_ci=[round(lo * people * avg_paid), round(hi * people * avg_paid)],
            share_of_buyers=impact["lift"] / rate,
            share_ci=[lo / rate, hi / rate],
        )

    # one more counsellor
    pricer = capacity._pricer()
    slots = capacity.capacity()
    extra = int(CONF["counsellor_daily_calls"])
    cost = counsellor_cost()
    per_day_now = slots_value(pricer, 0, slots)
    per_day_extra = slots_value(pricer, slots, extra)
    counsellor = {
        "slots_now": slots,
        "extra_slots": extra,
        "monthly_cost": cost,
        "enough_data": pricer.policy == "priced",
        "note": pricer.note,
        "calls_worth_making_per_day": round(pricer.per_day, 1),
        "slots_now_add_per_month": round(per_day_now * days_in_month),
        "extra_adds_per_month": round(per_day_extra * days_in_month),
        "net_per_month": round(per_day_extra * days_in_month - cost),
    }

    # the discount budget
    b = budget.current()
    bp = budget._pricer()
    if b["budget"] is not None:
        _, profit_now = bp.month_value(b["budget"], days_in_month)
        _, profit_more = bp.month_value(b["budget"] + EXTRA_BUDGET, days_in_month)
        b["extra"] = {"amount": EXTRA_BUDGET, "adds_per_month": round(profit_more - profit_now)}
    return {
        "as_of": now.strftime(TS),
        "month": {
            "label": now.strftime("%B %Y"),
            "days_in_month": days_in_month,
            "day": now.day,
            "revenue": round(float(month["revenue"])),
            "purchases": int(month["n"]),
            "discount_given": round(float(month["discount"])),
        },
        "pipeline": money.totals(),
        "team": team,
        "counsellor": counsellor,
        "budget": b,
        "coupons_kept": money.kept(),
        "average_fee_paid": round(float(avg_paid)),
    }
