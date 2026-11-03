"""
Capacity-aware next-best-action: what is one call slot worth today?

The team can make only so many calls a day (``daily_call_capacity``). Next-best-action decides one learner at a time,
as triggers arrive, so a plain cap gives the slots away first come, first served: a call that adds a little profit in
the morning takes the slot that a call adding far more would have needed in the evening. And what a call adds is
not its whole value, only what it adds over the best step that needs no call (an email is often nearly as good).

So every call slot gets a price, the way airlines price a seat with a bid price:

    advantage of a call    d = profit(call) - max(profit of every other allowed step, including doing nothing)
    price of a slot        the smallest x for which the calls with d > x, expected in the rest of today, fit into
                           the slots that are left

The expected arrivals come from the CRM's own decision log: every automatic decision of the last ``lookback_days``
where a call was possible stores its d (``nba_decisions.call_value``) and the time of day. With R the share of a
day's call-worthy decisions that usually arrive after this time of day, D the days seen and S the slots left:

    price = the (k+1)-th largest d of the window, with k = floor(S * D / R)       (0 when there are fewer)

so the price falls when slots are left late in the day and rises when they are being used up early. A call is chosen
only when its advantage is larger than the price; the hard cap stays as a backstop. With too little history
(``min_decisions``) or ``policy: fcfs`` the price is 0: first come, first served, as before.

The experiment ``ml/experiments/capacity_check.py`` (E7) compares first come first served, a fixed price, this
re-solved price and the best possible allocation with hindsight, on simulated days with known true effects.
"""

from __future__ import annotations

import bisect
import logging
import math
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app import db
from app.core import rules

log = logging.getLogger(__name__)

CAPACITY_FULL = "today's call capacity is used up"
CONF = {"policy": "priced", "lookback_days": 7, "min_decisions": 50, **(rules.S.get("call_capacity") or {})}
TS = "%Y-%m-%d %H:%M:%S"
_cache: dict = {"at": 0.0, "pricer": None}
_lock = threading.Lock()
CACHE_SECONDS = 600


def capacity() -> int:
    return int(rules.S.get("daily_call_capacity", 20))


def call_advantage(values: dict, blocked: dict) -> float | None:
    """What a call adds over the best step that needs no call, or None when a call is not possible for this person
    for a reason other than today's capacity (no phone number, asked not to be called, not used for this trigger)."""
    why = blocked.get("call")
    if why and why != CAPACITY_FULL:
        return None
    others = [values[a]["incremental_profit"] for a in values if a != "call" and (not blocked.get(a) or a == "none")]
    return float(values["call"]["incremental_profit"] - max(others + [0.0]))


def time_of_day(t: datetime) -> float:
    """Time of day as a share of the day (0 at midnight)."""
    return (t.hour * 3600 + t.minute * 60 + t.second) / 86400.0


@dataclass
class SlotPricer:
    """The price of a call slot from a look-back window of decisions. advantages: d of every decision where a call
    was possible; tods: their times of day (0-1); days: number of days in the window that had decisions; day_of: the
    day of each decision (optional; the planner uses it to value more slots day by day)."""

    advantages: list[float]
    tods: list[float]
    days: int
    capacity: int
    policy: str = "priced"
    note: str = ""
    day_of: list = field(default_factory=list, repr=False)
    _pos: list[float] = field(default_factory=list, repr=False)
    _pos_tods: list[float] = field(default_factory=list, repr=False)

    def __post_init__(self):
        pairs = sorted(((a, t) for a, t in zip(self.advantages, self.tods) if a > 0), key=lambda p: -p[0])
        self._pos = [a for a, _ in pairs]
        self._pos_tods = sorted(t for _, t in pairs)

    @property
    def per_day(self) -> float:
        """Call-worthy decisions (d > 0) per day in the window."""
        return len(self._pos) / self.days if self.days else 0.0

    def remaining_share(self, tod: float) -> float:
        """Share of a day's call-worthy decisions that arrive after this time of day (from the window)."""
        if not self._pos_tods:
            return 1.0 - tod
        after = len(self._pos_tods) - bisect.bisect_right(self._pos_tods, tod)
        return max(after / len(self._pos_tods), 1e-6)

    def price(self, slots_left: int, tod: float = 0.0, static: bool = False) -> float:
        """The advantage a call must beat now. static=True: the same price all day (the whole capacity, all day)."""
        if self.policy != "priced" or not self._pos or not self.days:
            return 0.0
        if slots_left <= 0:
            return math.inf
        share = 1.0 if static else self.remaining_share(tod)
        slots = self.capacity if static else slots_left
        k = math.floor(slots * self.days / share)
        return float(self._pos[k]) if k < len(self._pos) else 0.0

    def summary(self) -> dict:
        return {
            "policy": self.policy,
            "capacity": self.capacity,
            "days_seen": self.days,
            "candidates": len(self.advantages),
            "per_day": round(self.per_day, 2),
            "static_price": round(self.price(self.capacity, static=True), 2),
            "note": self.note,
        }


def pricer_from_rows(
    rows: list[dict], cap: int, lookback_days: int, policy: str | None = None, min_decisions: int | None = None
) -> SlotPricer:
    """rows: decisions of the window with created_at and call_value (None when a call was not possible)."""
    policy = policy or CONF["policy"]
    min_decisions = int(CONF["min_decisions"] if min_decisions is None else min_decisions)
    adv, tods, days, day_of = [], [], set(), []
    for r in rows:
        try:
            t = datetime.strptime(str(r["created_at"])[:19], TS)
        except (TypeError, ValueError):
            continue
        days.add(t.date())
        if r.get("call_value") is not None:
            adv.append(float(r["call_value"]))
            tods.append(time_of_day(t))
            day_of.append(t.date())
    note = ""
    if policy != "priced":
        note = "Pricing is switched off (call_capacity.policy in crm_settings.json)."
    elif len(adv) < min_decisions:
        note = (
            f"Only {len(adv)} decisions in the last {lookback_days} days could have used a call "
            f"(need {min_decisions})."
        )
        policy = "fcfs"
    return SlotPricer(adv, tods, max(len(days), 1) if adv else 0, cap, policy, note, day_of)


def pricer_at(as_of: datetime, cap: int | None = None, con=None) -> SlotPricer:
    """The pricer from the decisions before as_of (the history generator calls this with simulated time)."""
    lookback = int(CONF["lookback_days"])
    since = (as_of - timedelta(days=lookback)).strftime(TS)
    sql = """SELECT created_at, call_value FROM nba_decisions
             WHERE created_at >= ? AND created_at < ? AND COALESCE(policy, '') NOT IN ('holdout', 'manual')"""
    params = (since, as_of.strftime(TS))
    if con is not None:
        rows = [{"created_at": r[0], "call_value": r[1]} for r in con.execute(sql, params)]
    else:
        rows = db.fetchall(sql, params)
    return pricer_from_rows(rows, cap or capacity(), lookback)


def calls_today(now: datetime | None = None) -> int:
    """Call tasks created today. One team makes every call, so all calls share the daily capacity."""
    day = (now or datetime.now()).strftime("%Y-%m-%d")
    return db.fetchone(
        """SELECT COUNT(*) AS c FROM sales_tasks WHERE task_type='call' AND date(created_at)=?""", (day,)
    )["c"]


def _pricer() -> SlotPricer:
    with _lock:
        if _cache["pricer"] is None or time.time() - _cache["at"] > CACHE_SECONDS:
            p = pricer_at(datetime.now())
            _cache.update(pricer=p, at=time.time())
            _log(p)
        return _cache["pricer"]


def _log(p: SlotPricer) -> None:
    """Keep at most one price a quarter-hour in call_slot_prices (the dashboard's price chart)."""
    try:
        last = db.fetchone("SELECT computed_at FROM call_slot_prices ORDER BY id DESC LIMIT 1")
        if last and datetime.now() - datetime.strptime(last["computed_at"][:19], TS) < timedelta(minutes=15):
            return
        db.execute(
            """INSERT INTO call_slot_prices (price, policy, capacity, lookback_days, days_seen, candidates,
                      per_day, note) VALUES (?,?,?,?,?,?,?,?)""",
            (
                p.price(p.capacity, static=True),
                p.policy,
                p.capacity,
                int(CONF["lookback_days"]),
                p.days,
                len(p.advantages),
                round(p.per_day, 2),
                p.note or None,
            ),
        )
    except Exception:  # noqa: BLE001 - the log is informational
        log.debug("Could not log the call slot price", exc_info=True)


def reset_cache() -> None:
    with _lock:
        _cache.update(pricer=None, at=0.0)


def price_now(now: datetime | None = None) -> tuple[float, int]:
    """(price of a call slot right now, calls already created today)."""
    now = now or datetime.now()
    used = calls_today(now)
    return _pricer().price(capacity() - used, time_of_day(now)), used


def current() -> dict:
    """Everything the dashboard shows about call slots right now."""
    now = datetime.now()
    p = _pricer()
    used = calls_today(now)
    price = p.price(p.capacity - used, time_of_day(now))
    history = db.fetchall("""SELECT computed_at, price, policy, per_day FROM call_slot_prices
                             WHERE computed_at >= datetime('now','localtime','-14 days') ORDER BY id""")
    return {
        **p.summary(),
        "price": None if math.isinf(price) else round(price, 2),
        "calls_today": used,
        "slots_left": max(p.capacity - used, 0),
        "full": used >= p.capacity,
        "lookback_days": int(CONF["lookback_days"]),
        "history": history,
    }
