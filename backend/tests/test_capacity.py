"""
Capacity-aware next-best-action (the call-slot price, app.ml.capacity): the arithmetic of the price, how it moves
with the slots left and the time of day, how the choice uses it, and what the dashboard is given.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

import pytest
from support import CRM

from app.ml import capacity as C
from app.ml import nba_core as N


def _values(**profit):
    """values as nba_core.expected_values gives them, from incremental profit per action."""
    return {a: {"incremental_profit": float(profit.get(a, 0.0))} for a in N.ACTION_LIST}


def _pricer(advantages, days=1, cap=3, tods=None, policy="priced"):
    tods = tods if tods is not None else [0.5] * len(advantages)
    return C.SlotPricer(list(advantages), list(tods), days, cap, policy)


def test_call_advantage_is_measured_against_the_best_step_without_a_call():
    values = _values(call=100, email_info=60, whatsapp=30)
    assert C.call_advantage(values, {}) == pytest.approx(40)
    # a step that is not allowed for this person does not count ...
    assert C.call_advantage(values, {"email_info": "asked not to be emailed"}) == pytest.approx(70)
    # ... and doing nothing (0) is always possible
    assert C.call_advantage(_values(call=-5), {}) == pytest.approx(-5)


def test_no_call_advantage_when_a_call_is_not_possible_for_other_reasons():
    values = _values(call=100, email_info=60)
    assert C.call_advantage(values, {"call": "no phone number"}) is None
    # a full day still has an advantage: the price is then infinite, not the advantage unknown
    assert C.call_advantage(values, {"call": C.CAPACITY_FULL}) == pytest.approx(40)


def test_the_price_lets_exactly_the_capacity_through():
    advantages = [100, 90, 80, 70, 60, 50, 40, 30, 20, 10]  # ten call-worthy decisions in one day
    p = _pricer(advantages, days=1, cap=3)
    price = p.price(3, static=True)
    assert price == 70  # the 4th largest: the three above it fill the three slots
    assert sum(a > price for a in advantages) == 3


def test_no_price_with_spare_capacity_or_without_pricing():
    assert _pricer([50, 40], cap=5).price(5, static=True) == 0.0  # fewer worthy calls than slots
    assert _pricer([100, 90, 80, 70], policy="fcfs").price(1, static=True) == 0.0
    assert _pricer([], cap=3).price(3) == 0.0
    assert _pricer([-10, -20], cap=1).price(1) == 0.0  # only call-worthy (positive) advantages count


def test_no_slot_left_means_an_infinite_price():
    assert math.isinf(_pricer([100, 90, 80]).price(0, tod=0.4))


def test_the_price_falls_as_slots_are_left_late_in_the_day():
    # 40 call-worthy decisions spread evenly over one day, 5 slots
    advantages = [float(100 - i * 2) for i in range(40)]
    tods = [i / 40 for i in range(40)]
    p = _pricer(advantages, days=1, cap=5, tods=tods)
    # the same slots are worth less later: fewer decisions are still to come
    prices = [p.price(5, tod=t) for t in (0.0, 0.25, 0.5, 0.75, 0.95)]
    assert prices == sorted(prices, reverse=True)
    assert prices[0] > prices[-1]
    # and fewer slots are worth more at the same moment
    by_slots = [p.price(k, tod=0.5) for k in (1, 2, 3, 4, 5)]
    assert by_slots == sorted(by_slots, reverse=True)


def test_remaining_share_comes_from_the_look_back_window():
    p = _pricer([10, 20, 30, 40], tods=[0.1, 0.2, 0.8, 0.9])
    assert p.remaining_share(0.0) == pytest.approx(1.0)
    assert p.remaining_share(0.5) == pytest.approx(0.5)
    assert p.remaining_share(0.95) > 0  # never zero: the price stays finite


def test_pricer_from_rows_needs_enough_history():
    now = datetime(2026, 10, 1, 12, 0, 0)
    rows = [{"created_at": (now - timedelta(hours=h)).strftime(C.TS), "call_value": 10.0 + h} for h in range(1, 31)]
    rows.append({"created_at": now.strftime(C.TS), "call_value": None})  # a call was not possible: not counted
    rows.append({"created_at": "not a time", "call_value": 5.0})  # unreadable rows are skipped
    few = C.pricer_from_rows(rows, cap=3, lookback_days=7, policy="priced", min_decisions=50)
    assert few.policy == "fcfs" and "need 50" in few.note
    assert few.price(3, tod=0.5) == 0.0
    enough = C.pricer_from_rows(rows, cap=3, lookback_days=7, policy="priced", min_decisions=10)
    assert enough.policy == "priced"
    assert len(enough.advantages) == 30 and enough.days == 2
    assert enough.per_day == pytest.approx(15.0)


def test_the_choice_counts_the_slot_price_against_a_call():
    values = _values(call=100, email_info=70, whatsapp=20)
    action, policy, propensity, best = N.choose(values, {}, explore_rate=0.0, slot_price=20.0)
    assert action == "call" and policy == "model" and propensity == 1.0  # 100 - 20 beats 70
    action, *_ = N.choose(values, {}, explore_rate=0.0, slot_price=40.0)
    assert action == "email_info"  # 100 - 40 does not
    action, *_ = N.choose(_values(call=-10, email_info=-5), {}, explore_rate=0.0)
    assert action == "none"  # nothing pays for itself


def test_exploration_keeps_honest_propensities():
    import numpy as np

    rng = np.random.default_rng(1)
    values = _values(call=100, email_info=70)
    allowed = len(N.ACTION_LIST)
    seen = {}
    for _ in range(400):
        action, policy, propensity, best = N.choose(values, {}, explore_rate=0.3, rng=rng)
        assert best == "call"
        expected = 0.7 * (action == best) + 0.3 / allowed
        assert propensity == pytest.approx(expected)
        seen[policy] = seen.get(policy, 0) + 1
    assert seen["explore"] > 50 and seen["model"] > 200


def test_the_dashboard_gets_the_current_slot_price(client, owner):
    C.reset_cache()
    r = client.get(f"{CRM}/capacity", headers=owner["headers"])
    assert r.status_code == 200
    body = r.json()
    for key in ("policy", "capacity", "price", "calls_today", "slots_left", "full", "per_day", "static_price"):
        assert key in body
    assert body["capacity"] == C.capacity()
    assert body["slots_left"] == max(body["capacity"] - body["calls_today"], 0)
