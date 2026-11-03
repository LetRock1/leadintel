"""A person holds at most one open coupon, every coupon has its own code, and the team cannot take the same step twice
in a row by hand (the same email again within a day, or a second call while the first one is still waiting)."""

from __future__ import annotations

import re

import pytest
from support import API, CRM

from app import db
from app.core import rules


def _outside_control(new_learner, name):
    for _ in range(20):
        learner = new_learner(name)
        if not rules.in_global_control(learner["user"]["id"]):
            return learner
    pytest.fail("no learner outside the control group in 20 tries")


@pytest.fixture
def learner(client, new_learner):
    """A learner outside the control group with a phone number, who looked at a course and its price."""
    who = _outside_control(new_learner, "Ishaan Bose")
    h = who["headers"]
    profile = {
        "current_occupation": "Working Professional",
        "specialization": "Finance Management",
        "city": "Pune",
        "phone": "+91 98765 11111",
    }
    assert client.post(f"{API}/profile/complete", json=profile, headers=h).status_code == 200
    sid = client.post(f"{API}/session/start", json={"device_type": "Mobile"}, headers=h).json()["session_id"]
    for event, seconds in (("page_view", 90), ("pricing_view", 40)):
        client.post(
            f"{API}/track",
            json={"session_id": sid, "course_slug": "mba-core", "event_type": event, "time_spent_sec": seconds},
            headers=h,
        )
    return who


def _lead(client, owner, email):
    return client.get(f"{CRM}/leads", params={"search": email}, headers=owner["headers"]).json()["leads"][0]["id"]


def _act(client, owner, lead_id, action):
    return client.post(f"{CRM}/leads/{lead_id}/act", json={"action": action}, headers=owner["headers"])


def test_one_open_coupon_per_person_whoever_gives_it(client, owner, learner, new_learner):
    from app.services import money

    uid, lead_id = learner["user"]["id"], _lead(client, owner, learner["email"])
    r = _act(client, owner, lead_id, "email_coupon_20")
    assert r.status_code == 200, r.text
    coupons = db.fetchall("SELECT * FROM coupons_issued WHERE user_id=?", (uid,))
    assert len(coupons) == 1
    code = coupons[0]["coupon_code"]
    assert re.fullmatch(r"SMARTSTART20-[A-HJ-NP-Z2-9]{5}", code), code  # a personal code, not a shared one

    # the same step again at once: refused, with when it can be taken again
    r = _act(client, owner, lead_id, "email_coupon_20")
    assert r.status_code == 409 and "already done today" in r.json()["detail"], r.text
    # a different coupon while the first is open: refused too (discounts never stack)
    r = _act(client, owner, lead_id, "email_coupon_10")
    assert r.status_code == 400 and "already has an open 20% coupon until" in r.json()["detail"], r.text
    now = client.get(f"{CRM}/leads/{lead_id}/now", headers=owner["headers"]).json()
    blocked = {o["action"]: o["blocked"] for o in now["options"]}
    assert blocked["email_coupon_10"].startswith("already has an open 20% coupon")
    assert blocked["email_coupon_20"].startswith("already has an open 20% coupon")
    assert now["recommendation"]["action"] not in ("email_coupon_10", "email_coupon_20")
    assert "email_coupon_20" in now["recent"]
    # the pipeline's best step for them is not a coupon either
    assert money.board_values(fresh=True)[uid]["best"] not in ("email_coupon_10", "email_coupon_20")
    # the coupon guard and a coupon given by hand say the same, even when confirmed
    g = client.get(f"{CRM}/coupons/check", params={"user_id": uid, "discount_pct": 10}, headers=owner["headers"]).json()
    assert g["verdict"] == "has_coupon" and code in g["message"]
    r = client.post(
        f"{CRM}/coupons",
        json={"user_id": uid, "tier": "", "discount_pct": 10, "expires_hours": 24, "override": True},
        headers=owner["headers"],
    )
    assert r.status_code == 409, r.text
    assert len(db.fetchall("SELECT * FROM coupons_issued WHERE user_id=?", (uid,))) == 1

    # the code is personal: another learner cannot use it
    other = new_learner("Someone Else")
    assert client.post(f"{API}/cart", json={"course_slug": "mba-core"}, headers=other["headers"]).status_code == 200
    r = client.post(f"{API}/checkout", json={"coupon_code": code}, headers=other["headers"])
    assert r.status_code == 400
    # its owner can, once; then a coupon step is possible again for a later course
    assert client.post(f"{API}/cart", json={"course_slug": "mba-core"}, headers=learner["headers"]).status_code == 200
    r = client.post(f"{API}/checkout", json={"coupon_code": code.lower()}, headers=learner["headers"])
    assert r.status_code == 200, r.text
    assert db.open_coupon(uid) is None


def test_every_coupon_gets_its_own_code(client):
    from app.services.content import coupon_code_for

    codes = {coupon_code_for(20) for _ in range(200)}
    assert len(codes) == 200 and all(c.startswith("SMARTSTART20-") for c in codes)
    assert coupon_code_for(10, returning=True).startswith("LOYAL10-")
    assert coupon_code_for(0) == ""


def test_the_same_email_or_a_second_call_is_not_taken_twice_by_hand(client, owner, learner):
    lead_id = _lead(client, owner, learner["email"])
    uid = learner["user"]["id"]
    assert _act(client, owner, lead_id, "email_info").status_code == 200
    r = _act(client, owner, lead_id, "email_info")
    assert r.status_code == 409 and "Send an information email: already done today" in r.json()["detail"], r.text
    assert len(db.fetchall("SELECT id FROM email_sends WHERE user_id=?", (uid,))) == 1

    assert _act(client, owner, lead_id, "call").status_code == 200
    r = _act(client, owner, lead_id, "call")
    assert r.status_code == 409 and "already waiting in Today's actions" in r.json()["detail"], r.text
    assert len(db.fetchall("SELECT id FROM sales_tasks WHERE user_id=? AND status='open'", (uid,))) == 1
    # once the call is done, another call can be planned
    task = db.fetchone("SELECT id FROM sales_tasks WHERE user_id=? AND status='open'", (uid,))
    db.execute("UPDATE sales_tasks SET status='done', outcome='reached' WHERE id=?", (task["id"],))
    assert _act(client, owner, lead_id, "call").status_code == 200
    # every decision taken by hand is logged once
    assert db.fetchone("SELECT COUNT(*) AS n FROM nba_decisions WHERE user_id=? AND policy='manual'", (uid,))["n"] == 3


def test_at_most_one_coupon_a_week_even_after_the_last_one_expired(client, owner, learner):
    uid, lead_id = learner["user"]["id"], _lead(client, owner, learner["email"])
    assert _act(client, owner, lead_id, "email_coupon_10").status_code == 200
    # the coupon expires unused two days later: still no new coupon that week
    db.execute("UPDATE coupons_issued SET expires_at=datetime('now','localtime','-1 hours') WHERE user_id=?", (uid,))
    assert db.open_coupon(uid) is None
    now = client.get(f"{CRM}/leads/{lead_id}/now", headers=owner["headers"]).json()
    blocked = {o["action"]: o["blocked"] for o in now["options"]}
    assert blocked["email_coupon_20"].startswith("already got a coupon on"), blocked["email_coupon_20"]
    g = client.get(f"{CRM}/coupons/check", params={"user_id": uid, "discount_pct": 10}, headers=owner["headers"]).json()
    assert g["verdict"] == "has_coupon"
    # a week later a coupon is possible again
    db.execute("UPDATE coupons_issued SET created_at=datetime('now','localtime','-8 days') WHERE user_id=?", (uid,))
    db.execute("DELETE FROM nba_decisions WHERE user_id=?", (uid,))  # the by-hand repeat window is a separate rule
    now = client.get(f"{CRM}/leads/{lead_id}/now", headers=owner["headers"]).json()
    blocked = {o["action"]: o["blocked"] for o in now["options"]}
    assert not blocked["email_coupon_20"]
