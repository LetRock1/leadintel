"""
The CRM's money: the pipeline in rupees, the discount budget and its price, the coupon guard and the owner's planner.

The pipeline board's numbers for every lead are the single-lead decision's own numbers, computed for everyone at once.
A discount budget gives a rupee of discount a price that keeps money for the coupons that add the most per rupee, the
way call slots are priced. A coupon given by hand that would mostly give money away is stopped unless someone
confirms it, and never reaches the control group.
"""

from __future__ import annotations

import math
import uuid

import numpy as np
import pytest
from support import API, CRM, bearer, unique_email

from app.core import rules
from app.ml import budget
from app.ml import nba_core as N
from app.services import money


def _values(**gain):
    """Option values with an incremental profit and an expected discount per step."""
    out = {}
    for a in N.ACTION_LIST:
        g, d = gain.get(a, (0.0, 0.0))
        out[a] = {"incremental_profit": float(g), "expected_discount": float(d), "p_convert": 0.3}
    return out


# The price of a rupee of discount
def test_a_coupon_is_measured_against_the_best_step_without_a_coupon():
    v = _values(
        email_info=(200.0, 0.0), email_coupon_10=(500.0, 900.0), email_coupon_20=(650.0, 2000.0), call=(900.0, 0.0)
    )
    blocked = {a: None for a in N.ACTION_LIST}
    value, cost, coupon = budget.coupon_advantage(v, blocked, slot_price=600.0)
    assert coupon == "email_coupon_20"
    assert value == pytest.approx(650.0 - 300.0)  # the call counts net of its slot price (900 - 600)
    assert cost == pytest.approx(2000.0)
    blocked["email_coupon_10"] = blocked["email_coupon_20"] = "opted out of email"
    assert budget.coupon_advantage(v, blocked) is None
    blocked["email_coupon_10"] = blocked["email_coupon_20"] = budget.BUDGET_USED_UP
    assert budget.coupon_advantage(v, blocked) is not None  # still demand: the next month's price needs it


def test_the_price_lets_exactly_the_budget_through():
    # one day of history: four coupons that pay, ratios 4, 3, 2 and 1, each with an expected discount of 100
    p = budget.BudgetPricer([400.0, 300.0, 200.0, 100.0, -50.0], [100.0] * 5, days=1)
    assert p.paying == 4
    # one day left in the month, 250 left: the two best fit, the price is the third best ratio
    assert p.price(250.0, 1.0) == pytest.approx(2.0)
    assert p.price(1000.0, 1.0) == 0.0  # money for every coupon that pays: no price
    assert math.isinf(p.price(0.0, 1.0))  # nothing left: no coupon
    # more days ahead with the same money: the price rises
    assert p.price(250.0, 2.0) > p.price(250.0, 1.0)


def test_a_bigger_budget_adds_less_and_less():
    p = budget.BudgetPricer([400.0, 300.0, 200.0, 100.0], [100.0] * 4, days=1)
    _, a = p.month_value(100.0 * 30, 30)
    _, b = p.month_value(200.0 * 30, 30)
    _, c = p.month_value(300.0 * 30, 30)
    assert 0 < a < b < c
    assert b - a > c - b  # the best coupons per rupee come first


def test_too_little_history_means_no_price_until_the_money_is_gone():
    rows = [{"created_at": "2026-10-20 10:00:00", "coupon_value": 100.0, "coupon_cost": 50.0}] * 5
    p = budget.pricer_from_rows(rows, 7, min_decisions=30)
    assert p.policy == "fcfs" and "need 30" in p.note
    assert p.price(10.0, 5.0) == 0.0 and math.isinf(p.price(0.0, 5.0))


def test_the_choice_counts_the_price_of_the_discount_against_a_coupon():
    v = _values(email_info=(300.0, 0.0), email_coupon_20=(500.0, 400.0))
    blocked = {a: None for a in N.ACTION_LIST}
    assert N.choose(v, blocked, coupon_price=0.0)[3] == "email_coupon_20"
    # at 0.6 a rupee, the coupon's 400 of discount is worth 240 elsewhere: 500 - 240 < 300
    assert N.choose(v, blocked, coupon_price=0.6)[3] == "email_info"


def test_the_priced_budget_earns_more_than_first_come_first_served():
    """A month of coupon decisions arriving in random order: spending a budget first come, first served against the
    re-solved price, with the price learned from the previous week (the production BudgetPricer)."""
    rng = np.random.default_rng(4)
    days, per_day = 30, 40
    v = rng.gamma(2.0, 150.0, (days + 7, per_day))  # profit a coupon adds
    c = rng.gamma(2.0, 200.0, (days + 7, per_day))  # its expected discount
    month_budget = 0.3 * c[7:].sum()  # money for about a third of what would pay
    fcfs = priced = 0.0
    left_f = left_p = month_budget
    for d in range(days):
        hist = slice(d, d + 7)
        pricer = budget.BudgetPricer(list(v[hist].ravel()), list(c[hist].ravel()), days=7)
        for i in range(per_day):
            vi, ci = v[d + 7, i], c[d + 7, i]
            if left_f >= ci:
                fcfs, left_f = fcfs + vi, left_f - ci
            lam = pricer.price(left_p, days - d - i / per_day)
            if vi > lam * ci and left_p >= ci:
                priced, left_p = priced + vi, left_p - ci
    assert priced > 1.2 * fcfs
    assert left_p >= 0


# One more counsellor
def test_more_call_slots_are_valued_day_by_day_with_the_crms_own_rule():
    from app.ml import capacity
    from app.services import planner

    # day 1 is busy (10 calls that would add value), day 2 quiet (3): with 8 slots, 2 calls of day 1 miss out, and
    # the quiet day's spare slots cannot take them
    adv = [100.0 + i for i in range(10)] + [50.0, 40.0, 30.0, -20.0]
    tods = [0.3 + 0.05 * i for i in range(10)] + [0.4, 0.5, 0.6, 0.7]
    days = ["d1"] * 10 + ["d2"] * 4
    p = capacity.SlotPricer(adv, tods, 2, 8, policy="fcfs", day_of=days)
    # first come, first served (no price yet): the first 8 of day 1 and all 3 of day 2
    assert planner.slots_value(p, 0, 8) == pytest.approx((sum(adv[:8]) + 120.0) / 2)
    assert planner.slots_value(p, 8, 8) == pytest.approx((adv[8] + adv[9]) / 2)
    assert planner.slots_value(p, 16, 8) == 0.0
    # without the day of each decision: the window's calls ranked together
    pooled = capacity.SlotPricer(adv, tods, 2, 8, policy="fcfs")
    assert planner.slots_value(pooled, 8, 8) == 0.0  # 13 calls fit in 16 slots over 2 days


# The money view of the pipeline, through the API
@pytest.fixture
def worked_learner(client, new_learner):
    from support import API

    for _ in range(20):
        learner = new_learner()
        if not rules.in_global_control(learner["user"]["id"]):
            break
    else:
        pytest.fail("no learner outside the control group in 20 tries")
    h = learner["headers"]
    sid = client.post(f"{API}/session/start", json={"device_type": "Desktop"}, headers=h).json()["session_id"]
    for event, seconds in (("page_view", 200), ("pricing_view", 90), ("video_play", 300)):
        client.post(
            f"{API}/track",
            json={
                "session_id": sid,
                "course_slug": "business-analytics",
                "event_type": event,
                "time_spent_sec": seconds,
            },
            headers=h,
        )
    money.reset_cache()
    return learner


def test_the_board_shows_the_single_decisions_numbers(client, owner, worked_learner):
    from app.ml import nba

    uid = worked_learner["user"]["id"]
    v = money.compute([uid])[uid]
    now = nba.recommend_now(uid)
    assert v["p_anyway"] == pytest.approx(now["probability"], abs=2e-3)
    assert v["anyway"] == pytest.approx(v["p_anyway"] * v["price"], rel=1e-3)
    rec = now["recommendation"]
    if v["segment"] == "work":
        assert v["best"] == rec["action"]
        assert v["add"] == pytest.approx(rec["extra_profit"], rel=0.02, abs=2.0)
    else:
        assert rec["action"] == "none" and v["add"] == 0.0
    board = client.get(f"{CRM}/pipeline", params={"limit": 500}, headers=owner["headers"]).json()
    card = next(c for col in board["columns"] for c in col["cards"] if c["user_id"] == uid)
    assert card["segment"] == v["segment"] and card["anyway"] == round(v["anyway"])
    open_cols = [c for c in board["columns"] if c["stage"] not in ("Customer", "Lost")]
    assert board["totals"]["anyway"] == pytest.approx(sum(c["anyway"] for c in open_cols), abs=len(open_cols))
    assert board["sort"] == "money"
    for col in open_cols:  # the most the team can add first
        adds = [c["add"] for c in col["cards"]]
        assert adds == sorted(adds, reverse=True)


def test_the_control_group_has_nothing_to_add(client, owner, new_learner):
    for _ in range(80):
        learner = new_learner()
        if rules.in_global_control(learner["user"]["id"]):
            break
    else:
        pytest.skip("no control-group learner in 80 tries")
    uid = learner["user"]["id"]
    v = money.compute([uid])[uid]
    assert v["segment"] == "control" and v["add"] == 0.0 and v["best"] == "none"
    r = client.get(f"{CRM}/coupons/check", params={"user_id": uid, "discount_pct": 10}, headers=owner["headers"])
    assert r.status_code == 200 and r.json()["verdict"] == "control"
    r = client.post(
        f"{CRM}/coupons",
        json={"user_id": uid, "tier": "Low Priority", "discount_pct": 10, "override": True},
        headers=owner["headers"],
    )
    assert r.status_code == 409  # never, not even confirmed: it would spoil the control group


def test_the_coupon_guard_stops_a_coupon_that_gives_money_away(client, owner, worked_learner):
    uid = worked_learner["user"]["id"]
    check = client.get(f"{CRM}/coupons/check", params={"user_id": uid, "discount_pct": 50}, headers=owner["headers"])
    assert check.status_code == 200, check.text
    g = check.json()
    tol = g["price"] * 2e-4  # the chances are rounded to 4 decimals
    assert g["expected_discount"] == pytest.approx(g["p_with"] * g["price"] * 0.5, abs=tol)
    assert g["extra_profit"] == pytest.approx(g["p_with"] * g["price"] * 0.5 - g["p_without"] * g["price"], abs=tol)
    assert g["note"]  # 50% is far from the 10% and 20% coupons the model knows
    body = {"user_id": uid, "tier": "Low Priority", "discount_pct": 50}
    r = client.post(f"{CRM}/coupons", json=body, headers=owner["headers"])
    if g["verdict"] == "pays":
        assert r.status_code == 200
    else:
        assert r.status_code == 409 and "Confirm" in r.json()["detail"]
        r = client.post(f"{CRM}/coupons", json={**body, "override": True}, headers=owner["headers"])
        assert r.status_code == 200, r.text
    assert r.json()["guard"]["verdict"] == g["verdict"]
    coupons = client.get(f"{CRM}/coupons", headers=owner["headers"]).json()["coupons"]
    mine = next(c for c in coupons if c["user_id"] == uid and c["discount_pct"] == 50)
    assert mine["source"] == "manual" and mine["expected_cost"] == pytest.approx(g["expected_discount"], rel=1e-3)


def test_the_owner_sets_a_discount_budget_and_the_planner_prices_it(client, owner, team_member):
    marketing = team_member("marketing")
    r = client.put(f"{CRM}/planner/settings", json={"monthly_discount_budget": 50000}, headers=marketing["headers"])
    assert r.status_code == 403  # the owner's decision (admin)
    try:
        r = client.put(
            f"{CRM}/planner/settings",
            json={"monthly_discount_budget": 50000, "counsellor_monthly_cost": 30000},
            headers=owner["headers"],
        )
        assert r.status_code == 200, r.text
        p = r.json()
        assert p["budget"]["budget"] == 50000
        assert p["budget"]["left"] == pytest.approx(50000 - p["budget"]["spent"] - p["budget"]["committed"], abs=1)
        assert p["counsellor"]["monthly_cost"] == 30000
        assert p["counsellor"]["net_per_month"] == p["counsellor"]["extra_adds_per_month"] - 30000
        assert {"anyway", "add", "work"} <= set(p["pipeline"])
        # a budget that is used up stops every automatic coupon
        client.put(f"{CRM}/planner/settings", json={"monthly_discount_budget": 0}, headers=owner["headers"])
        price, left = budget.price_now()
        assert left is not None and left <= 0 and math.isinf(price)
    finally:
        client.put(f"{CRM}/planner/settings", json={"monthly_discount_budget": None}, headers=owner["headers"])
    assert budget.monthly_budget() is None
    member = client.get(f"{CRM}/planner", headers=bearer(marketing["token"]))
    assert member.status_code == 200 and member.json()["budget"]["budget"] is None


def test_the_coupon_list_reports_every_coupon_not_the_size_of_one_page(client, owner):
    from app import db

    uid = db.execute(
        "INSERT INTO users (name, email, password_hash) VALUES ('Coupon count test', ?, 'x')", (unique_email(),)
    )
    for used in (0, 0, 1):
        db.execute(
            """INSERT INTO coupons_issued (user_id, coupon_code, discount_pct, tier, used, source)
               VALUES (?, ?, 10, 'Low Priority', ?, 'manual')""",
            (uid, f"COUNT{uuid.uuid4().hex[:6].upper()}", used),
        )
    issued = "SELECT COUNT(*) AS n FROM coupons_issued ci JOIN users u ON u.id = ci.user_id"
    n, n_used = db.fetchone(issued)["n"], db.fetchone(issued + " WHERE ci.used = 1")["n"]
    page = client.get(f"{CRM}/coupons", params={"limit": 1}, headers=owner["headers"]).json()
    assert len(page["coupons"]) == 1 and page["all"] == n >= 3 and page["used"] == n_used >= 1 and page["total"] == n
    used = client.get(f"{CRM}/coupons", params={"show": "used", "limit": 500}, headers=owner["headers"]).json()
    assert used["total"] == n_used and all(c["used"] == 1 for c in used["coupons"])
    still = client.get(f"{CRM}/coupons", params={"show": "open", "limit": 1, "offset": 1}, headers=owner["headers"])
    assert still.json()["total"] == n - n_used and all(c["used"] == 0 for c in still.json()["coupons"])
    assert client.get(f"{CRM}/coupons", params={"show": "expired"}, headers=owner["headers"]).status_code == 422


def test_a_new_lead_gets_its_money_line_at_once_while_the_view_is_cached(client, owner, new_learner):
    money.board_values(fresh=True)  # the cached view of everyone, as the pipeline board keeps it for 30 seconds
    learner = new_learner("Fresh Money")
    uid = learner["user"]["id"]
    values = money.board_values()  # still within the 30 seconds
    assert uid in values and values[uid]["anyway"] > 0
    totals = money.totals()
    assert totals["open_leads"] >= 1
    # deleting the account takes them out at once
    assert client.delete(f"{API}/me", headers=learner["headers"]).status_code == 200
    assert uid not in money.board_values()
