"""
Discount money as a priced resource: what is a rupee of discount worth this month?

A coupon costs money only when the learner buys with it, so its expected cost is

    c = P(buy | coupon) x course fee x discount

Without a budget, next-best-action sends a coupon whenever it adds the most profit (its discount is already counted
in that profit). With a monthly discount budget set by the owner (Planner page), money is limited, and the problem of
the counsellors' call slots appears again: coupons given early in the month to leads a coupon barely helps use up
money that later leads needed more, and a first come, first served budget simply runs dry. So, like a call slot
(app.ml.capacity), every rupee of expected discount gets a price:

    coupon advantage  v = profit(best allowed coupon) - max(profit of every other allowed step, including nothing)
                          (a call counted net of the price of a call slot)
    ratio             r = v / c        profit the coupon adds per rupee of expected discount
    price             the ratio r* at which the coupons with r > r*, expected in the rest of the month, use up the
                      budget that is left

The expected arrivals come from the CRM's own decision log: every automatic decision of the last ``lookback_days``
where a coupon was possible stores v and c (``nba_decisions.coupon_value``, ``coupon_cost``). With D the days seen,
T the days left in the month and B the budget left (the budget minus the discounts already given this month minus the
expected cost of the coupons still open):

    price = the (k+1)-th largest r of the window, with k the most coupons (largest r first) whose cost fits B x D / T

A coupon is sent only when v > price x c: the profit it adds beats what its money would earn on later leads this
month. Without a budget the price is 0, exactly as before; when the budget is used up, coupons stop. With fewer than
``min_decisions`` decisions where a coupon paid, the price is 0 until the budget is used up.

The owner's planner reads the same numbers: what the coupons that pay would cost in a month with no limit, and what a
larger budget would add (app.services.planner). The experiment ``ml/experiments/money_check.py`` (E9) compares this
price with a budget spent first come, first served, a fixed price and the best allocation with hindsight.
"""

from __future__ import annotations

import bisect
import calendar
import logging
import math
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app import db
from app.core import rules

log = logging.getLogger(__name__)

CONF = {"lookback_days": 7, "min_decisions": 30, **(rules.S.get("discount_budget") or {})}
COUPONS = ("email_coupon_10", "email_coupon_20")
BUDGET_KEY = "discount_budget_monthly"
BUDGET_USED_UP = "this month's discount budget is used up"
DEFAULT_REDEMPTION = 0.25  # share of coupons used, until the CRM has seen enough of its own
TS = "%Y-%m-%d %H:%M:%S"
CACHE_SECONDS = 600
_cache: dict = {"at": 0.0, "pricer": None}
_lock = threading.Lock()


# The owner's setting
def monthly_budget() -> float | None:
    """The monthly discount budget in rupees, or None when there is none (coupons whenever they pay)."""
    v = db.app_setting(BUDGET_KEY)
    if v in (None, ""):
        return None
    try:
        b = float(v)
    except ValueError:
        return None
    return b if b >= 0 else None


def set_monthly_budget(value: float | None) -> None:
    db.put_app_setting(BUDGET_KEY, "" if value is None else f"{float(value):.2f}")
    reset_cache()


# One decision
def coupon_advantage(values: dict, blocked: dict, slot_price: float = 0.0) -> tuple[float, float, str] | None:
    """(v, c, coupon): what the best allowed coupon adds over the best step without a coupon, its expected discount
    and which coupon it is. None when no coupon is possible for this person (for a reason other than the budget)."""
    allowed = [a for a in COUPONS if a in values and (not blocked.get(a) or blocked.get(a) == BUDGET_USED_UP)]
    if not allowed:
        return None
    best = max(allowed, key=lambda a: values[a]["incremental_profit"])

    def net(a):
        return values[a]["incremental_profit"] - (slot_price if a == "call" else 0.0)

    others = [net(a) for a in values if a not in COUPONS and (not blocked.get(a) or a == "none")]
    v = float(values[best]["incremental_profit"] - max(others + [0.0]))
    return v, float(values[best].get("expected_discount") or 0.0), best


# The month
def month_bounds(now: datetime) -> tuple[datetime, datetime]:
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last = calendar.monthrange(now.year, now.month)[1]
    return start, start + timedelta(days=last)


def days_left(now: datetime) -> float:
    """Days left in this month, today's remaining hours included."""
    return max((month_bounds(now)[1] - now).total_seconds() / 86400.0, 1e-3)


def spent_this_month(now: datetime | None = None) -> float:
    """Discounts actually given on purchases this month."""
    start, _ = month_bounds(now or datetime.now())
    r = db.fetchone(
        "SELECT COALESCE(SUM(discount_amount), 0) AS s FROM purchases WHERE purchased_at >= ?", (start.strftime(TS),)
    )
    return float(r["s"] or 0.0)


def redemption_rate() -> float:
    """Share of the coupons of the last 60 days that were used (DEFAULT_REDEMPTION with fewer than 20)."""
    r = db.fetchone(
        """SELECT COUNT(*) AS n, COALESCE(SUM(used), 0) AS u FROM coupons_issued
           WHERE created_at >= datetime('now','localtime','-60 days')"""
    )
    return float(r["u"]) / r["n"] if r and r["n"] >= 20 else DEFAULT_REDEMPTION


def committed(now: datetime | None = None) -> float:
    """Expected discount of the coupons still open (issued, not used, not expired): money already promised."""
    from app.services import catalog

    now_s = (now or datetime.now()).strftime(TS)
    rows = db.fetchall(
        """SELECT discount_pct, expected_cost FROM coupons_issued
           WHERE used = 0 AND (expires_at IS NULL OR expires_at > ?)""",
        (now_s,),
    )
    if not rows:
        return 0.0
    guess = None
    total = 0.0
    for r in rows:
        if r["expected_cost"] is not None:
            total += float(r["expected_cost"])
        else:  # coupons of A/B tests and of older versions: the usual share of coupons is used
            if guess is None:
                guess = redemption_rate() * catalog.average_price()
            total += guess * float(r["discount_pct"] or 0) / 100.0
    return total


# The price
@dataclass
class BudgetPricer:
    """The price of a rupee of discount from a look-back window of decisions. values / costs: v and c of every
    decision of the window where a coupon was possible; days: days in the window that had decisions."""

    values: list[float]
    costs: list[float]
    days: int
    policy: str = "priced"
    note: str = ""
    _ratios: list[float] = field(default_factory=list, repr=False)
    _cum_cost: list[float] = field(default_factory=list, repr=False)
    _cum_value: list[float] = field(default_factory=list, repr=False)

    def __post_init__(self):
        rows = sorted(((v / c, c, v) for v, c in zip(self.values, self.costs) if v > 0 and c > 0), key=lambda x: -x[0])
        self._ratios = [r for r, _, _ in rows]
        cost = value = 0.0
        for _, c, v in rows:
            cost += c
            value += v
            self._cum_cost.append(cost)
            self._cum_value.append(value)

    @property
    def paying(self) -> int:
        """Decisions of the window where a coupon added profit."""
        return len(self._ratios)

    def per_day(self, which: str = "cost") -> float:
        """Expected discount (or added profit) per day if every coupon that pays were sent (no budget)."""
        cum = self._cum_cost if which == "cost" else self._cum_value
        return cum[-1] / self.days if cum and self.days else 0.0

    def price(self, budget_left: float, days_left_in_month: float) -> float:
        """The profit a rupee of expected discount must earn now (math.inf when nothing is left)."""
        if budget_left <= 0:
            return math.inf
        if self.policy != "priced" or not self._ratios or not self.days:
            return 0.0
        fits = budget_left * self.days / max(days_left_in_month, 1e-6)  # cost the window's coupons may use
        k = bisect.bisect_right(self._cum_cost, fits)
        return float(self._ratios[k]) if k < len(self._ratios) else 0.0

    def month_value(self, budget: float, days_in_month: float) -> tuple[float, float]:
        """(expected discount, profit added) in a month with this budget, spent on the coupons that pay most per
        rupee (what the price aims at)."""
        if not self.days or not self._cum_cost:
            return 0.0, 0.0
        fits = budget * self.days / days_in_month
        k = bisect.bisect_right(self._cum_cost, fits)
        scale = days_in_month / self.days
        if k == 0:
            return 0.0, 0.0
        return self._cum_cost[k - 1] * scale, self._cum_value[k - 1] * scale

    def summary(self) -> dict:
        return {
            "policy": self.policy,
            "days_seen": self.days,
            "decisions": len(self.values),
            "paying": self.paying,
            "cost_per_day": round(self.per_day("cost"), 2),
            "profit_per_day": round(self.per_day("value"), 2),
            "note": self.note,
        }


def pricer_from_rows(rows: list[dict], lookback_days: int, min_decisions: int | None = None) -> BudgetPricer:
    """rows: decisions of the window with created_at, coupon_value and coupon_cost (None: no coupon was possible)."""
    min_decisions = int(CONF["min_decisions"] if min_decisions is None else min_decisions)
    values, costs, days = [], [], set()
    for r in rows:
        try:
            days.add(datetime.strptime(str(r["created_at"])[:19], TS).date())
        except (TypeError, ValueError):
            continue
        if r.get("coupon_value") is not None and r.get("coupon_cost") is not None:
            values.append(float(r["coupon_value"]))
            costs.append(float(r["coupon_cost"]))
    pricer = BudgetPricer(values, costs, max(len(days), 1) if values else 0)
    if pricer.paying < min_decisions:
        pricer.policy = "fcfs"
        pricer.note = (
            f"Only {pricer.paying} decisions in the last {lookback_days} days had a coupon that paid (need "
            f"{min_decisions}); until then coupons simply stop when the budget is used up."
        )
    return pricer


def pricer_at(as_of: datetime, con=None) -> BudgetPricer:
    lookback = int(CONF["lookback_days"])
    sql = """SELECT created_at, coupon_value, coupon_cost FROM nba_decisions
             WHERE created_at >= ? AND created_at < ? AND COALESCE(policy, '') NOT IN ('holdout', 'manual')"""
    params = ((as_of - timedelta(days=lookback)).strftime(TS), as_of.strftime(TS))
    if con is not None:
        rows = [{"created_at": r[0], "coupon_value": r[1], "coupon_cost": r[2]} for r in con.execute(sql, params)]
    else:
        rows = db.fetchall(sql, params)
    return pricer_from_rows(rows, lookback)


def _pricer() -> BudgetPricer:
    with _lock:
        if _cache["pricer"] is None or time.time() - _cache["at"] > CACHE_SECONDS:
            _cache.update(pricer=pricer_at(datetime.now()), at=time.time())
        return _cache["pricer"]


def reset_cache() -> None:
    with _lock:
        _cache.update(pricer=None, at=0.0)


def state(now: datetime | None = None) -> dict:
    """The budget right now: budget, given, open coupons, left, the price, days left."""
    now = now or datetime.now()
    budget = monthly_budget()
    out = {"budget": budget, "days_left": round(days_left(now), 2)}
    if budget is None:
        return {**out, "spent": spent_this_month(now), "committed": committed(now), "left": None, "price": 0.0}
    spent, open_ = spent_this_month(now), committed(now)
    left = budget - spent - open_
    price = _pricer().price(left, days_left(now))
    return {**out, "spent": spent, "committed": open_, "left": left, "price": price}


def price_now(now: datetime | None = None) -> tuple[float, float | None]:
    """(price of a rupee of expected discount right now, budget left this month or None without a budget)."""
    if monthly_budget() is None:
        return 0.0, None
    s = state(now)
    return s["price"], s["left"]


def current() -> dict:
    """Everything the dashboard shows about the discount budget."""
    now = datetime.now()
    s = state(now)
    p = _pricer()
    days_in_month = (month_bounds(now)[1] - month_bounds(now)[0]).days
    natural_cost, natural_profit = p.per_day("cost") * days_in_month, p.per_day("value") * days_in_month
    return {
        **p.summary(),
        **s,
        "price": None if math.isinf(s["price"]) else round(s["price"], 3),
        "used_up": s["left"] is not None and s["left"] <= 0,
        "lookback_days": int(CONF["lookback_days"]),
        "min_decisions": int(CONF["min_decisions"]),  # paying decisions needed before a month's pace is stated
        "days_in_month": days_in_month,
        # what the coupons that pay would cost, and add, in a month with no limit (from the last lookback_days)
        "month_without_limit": {"discount": round(natural_cost), "profit_added": round(natural_profit)},
    }
