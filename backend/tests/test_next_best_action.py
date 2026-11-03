"""
Next-best-action for one learner: one calculation behind the decision receipt, the recommendation and the what-if
paths; consent, contact details and a lost status are respected; a step taken by hand is logged like an automatic
decision.
"""

from __future__ import annotations

import pytest
from support import API, CRM

from app import db
from app.core import rules


@pytest.fixture
def engaged_learner(client, new_learner):
    """A learner outside the control group who has looked at a course, its price and a video."""
    for _ in range(20):
        learner = new_learner()
        if not rules.in_global_control(learner["user"]["id"]):
            break
    else:
        pytest.fail("no learner outside the control group in 20 tries")
    h = learner["headers"]
    sid = client.post(f"{API}/session/start", json={"device_type": "Desktop"}, headers=h).json()["session_id"]
    for event, seconds in (("page_view", 120), ("pricing_view", 60), ("video_play", 300)):
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
    return learner


def _lead_id(client, owner, email):
    return client.get(f"{CRM}/leads", params={"search": email}, headers=owner["headers"]).json()["leads"][0]["id"]


def _now(client, owner, lead_id):
    r = client.get(f"{CRM}/leads/{lead_id}/now", headers=owner["headers"])
    assert r.status_code == 200, r.text
    return r.json()


def _net(option):
    return option["incremental_profit"] - (option.get("slot_price") or 0.0 if option["action"] == "call" else 0.0)


def test_the_receipt_adds_up(client, owner, engaged_learner):
    now = _now(client, owner, _lead_id(client, owner, engaged_learner["email"]))
    price = now["course"]["price"]
    assert now["course"]["slug"] == "business-analytics" and price > 0
    options = {o["action"]: o for o in now["options"]}
    none = options["none"]
    for o in options.values():
        profit = o["p_convert"] * price * (1 - o["discount"]) - o["cost"]
        assert o["expected_profit"] == pytest.approx(profit)
        assert o["incremental_profit"] == pytest.approx(profit - none["p_convert"] * price)
        assert o["uplift"] == pytest.approx(o["p_convert"] - none["p_convert"])
        assert 0.0 <= o["p_convert"] <= 1.0


def test_the_recommendation_is_the_best_allowed_step(client, owner, engaged_learner):
    now = _now(client, owner, _lead_id(client, owner, engaged_learner["email"]))
    allowed = [o for o in now["options"] if not o["blocked"]]
    best = max(allowed, key=lambda o: (_net(o), o["action"] == "none"))
    if _net(best) <= 0 and any(o["action"] == "none" for o in allowed):
        best = next(o for o in allowed if o["action"] == "none")
    assert now["recommendation"]["action"] == best["action"]
    assert now["recommendation"]["why"]


def test_the_what_if_paths_start_with_the_recommendation(client, owner, engaged_learner):
    lead_id = _lead_id(client, owner, engaged_learner["email"])
    now = _now(client, owner, lead_id)
    paths = client.get(f"{CRM}/leads/{lead_id}/paths", headers=owner["headers"]).json()
    assert paths["best"] == now["recommendation"]["action"]
    assert paths["steps"][0]["action"] == now["recommendation"]["action"]
    by_action = {o["action"]: o for o in now["options"]}
    for step in paths["steps"]:
        assert step["extra_profit"] == pytest.approx(by_action[step["action"]]["incremental_profit"])


def test_consent_and_contact_details_decide_what_is_allowed(client, owner, engaged_learner):
    lead_id = _lead_id(client, owner, engaged_learner["email"])
    blocked = {o["action"]: o["blocked"] for o in _now(client, owner, lead_id)["options"]}
    assert blocked["call"] == "no phone number"
    assert blocked["whatsapp"]  # not opted in

    h = engaged_learner["headers"]
    r = client.put(
        f"{API}/profile/preferences",
        json={"phone": "+91 98200 11223", "whatsapp_opt_in": True, "do_not_email": True},
        headers=h,
    )
    assert r.status_code == 200
    client.post(f"{CRM}/leads/{lead_id}/rescore", headers=owner["headers"])
    now = _now(client, owner, lead_id)
    blocked = {o["action"]: o["blocked"] for o in now["options"]}
    assert blocked["email_info"] == "opted out of email"
    assert blocked["email_coupon_10"] and blocked["email_coupon_20"]
    assert not blocked["whatsapp"]
    assert blocked["call"] in (None, "today's call capacity is used up")
    assert not blocked[now["recommendation"]["action"]]


def test_a_step_taken_by_hand_is_logged_like_an_automatic_one(client, owner, engaged_learner):
    lead_id = _lead_id(client, owner, engaged_learner["email"])
    uid = engaged_learner["user"]["id"]
    r = client.post(f"{CRM}/leads/{lead_id}/act", json={"action": "email_info"}, headers=owner["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["action"] == "email_info" and body["model_pick"]
    decision = db.fetchone("SELECT * FROM nba_decisions WHERE id=?", (body["decision_id"],))
    assert decision["user_id"] == uid and decision["policy"] == "manual" and decision["action"] == "email_info"
    # the email exists with its own tracking token (without Gmail it is recorded, not sent)
    send = db.fetchone("SELECT * FROM email_sends WHERE user_id=? ORDER BY id DESC LIMIT 1", (uid,))
    assert send is not None and len(send["token"]) == 32
    # a step the person does not allow is refused
    r = client.post(f"{CRM}/leads/{lead_id}/act", json={"action": "call"}, headers=owner["headers"])
    assert r.status_code == 400
    r = client.post(f"{CRM}/leads/{lead_id}/act", json={"action": "teleport"}, headers=owner["headers"])
    assert r.status_code == 400


def test_a_lost_lead_gets_no_automatic_steps_until_reopened(client, owner, engaged_learner):
    lead_id = _lead_id(client, owner, engaged_learner["email"])
    r = client.post(
        f"{CRM}/leads/{lead_id}/status", json={"status": "lost", "reason": "made up"}, headers=owner["headers"]
    )
    assert r.status_code == 400  # the reason must come from the list
    r = client.post(
        f"{CRM}/leads/{lead_id}/status", json={"status": "lost", "reason": "Too expensive"}, headers=owner["headers"]
    )
    assert r.status_code == 200, r.text
    now = _now(client, owner, lead_id)
    assert all(o["blocked"] for o in now["options"] if o["action"] != "none")
    assert now["recommendation"]["action"] == "none"
    r = client.post(f"{CRM}/leads/{lead_id}/status", json={"status": "open"}, headers=owner["headers"])
    assert r.status_code == 200
    now = _now(client, owner, lead_id)
    assert not all(o["blocked"] for o in now["options"] if o["action"] != "none")


def test_the_control_group_is_never_contacted_by_hand(client, owner, new_learner):
    # the control group is a fixed hash of the account number: skip ahead to the next number inside it
    next_id = (db.fetchone("SELECT seq FROM sqlite_sequence WHERE name='users'") or {"seq": 0})["seq"] + 1
    while not rules.in_global_control(next_id):
        db.execute(
            "INSERT INTO users (name, email, password_hash, is_verified) VALUES ('Filler', ?, '!', 0)",
            (f"filler.{next_id}@example.com",),
        )
        next_id += 1
    learner = new_learner()
    assert learner["user"]["id"] == next_id and rules.in_global_control(next_id)
    lead_id = _lead_id(client, owner, learner["email"])
    r = client.post(f"{CRM}/leads/{lead_id}/act", json={"action": "email_info"}, headers=owner["headers"])
    assert r.status_code == 409
    assert "control group" in r.json()["detail"]
    db.execute("DELETE FROM users WHERE name='Filler' AND email LIKE 'filler.%@example.com'")
