"""
A learner's whole journey through the API, and what the CRM sees of it: profile, a visit with tracked events
(each one re-scores the person), cart, wishlist, checkout, review, and finally the right to erasure.
"""

from __future__ import annotations

from support import API, CRM

from app import db

COURSE = "data-science-analytics"
OTHER_COURSE = "digital-marketing"


def _visit(client, learner, events):
    r = client.post(
        f"{API}/session/start", json={"device_type": "Mobile", "lead_source": "Google"}, headers=learner["headers"]
    )
    assert r.status_code == 200
    session_id = r.json()["session_id"]
    scores = []
    for event, seconds in events:
        r = client.post(
            f"{API}/track",
            json={"session_id": session_id, "course_slug": COURSE, "event_type": event, "time_spent_sec": seconds},
            headers=learner["headers"],
        )
        assert r.status_code == 200, r.text
        scores.append(r.json()["live_score"])
    return session_id, scores


def test_catalogue_and_faq_come_from_the_server(client):
    courses = client.get(f"{API}/courses").json()["courses"]
    assert len(courses) == 24
    one = client.get(f"{API}/courses/{COURSE}").json()
    assert one["slug"] == COURSE and one["price"] > 0
    assert client.get(f"{API}/courses/no-such-course").status_code == 404
    faq = client.get(f"{API}/faq").json()["faq"]
    assert faq and all(item["question"] and item["answer"] for item in faq)


def test_profile_uses_the_lead_models_vocabulary(client, new_learner):
    learner = new_learner()
    options = client.get(f"{API}/profile/options").json()
    assert "Unknown" not in options["occupations"]
    r = client.post(
        f"{API}/profile/complete",
        json={
            "current_occupation": options["occupations"][0],
            "specialization": options["specializations"][0],
            "city": "Pune",
            "phone": "+91 98765 43210",
        },
        headers=learner["headers"],
    )
    assert r.status_code == 200
    profile = db.get_profile(learner["user"]["id"])
    assert profile["profile_complete"] == 1
    assert profile["current_occupation"] == options["occupations"][0]
    bad = client.post(
        f"{API}/profile/complete",
        json={"current_occupation": "Student", "specialization": "Finance Management", "phone": "12"},
        headers=learner["headers"],
    )
    assert bad.status_code == 400


def test_every_event_rescores_the_learner(client, new_learner):
    learner = new_learner()
    _, scores = _visit(client, learner, [("page_view", 90), ("pricing_view", 60), ("video_play", 240)])
    assert all(0 <= s <= 100 for s in scores)
    state = db.fetchone("SELECT live_score FROM live_user_state WHERE user_id=?", (learner["user"]["id"],))
    assert state is not None and state["live_score"] == scores[-1]
    lead = db.get_user_lead(learner["user"]["id"])
    assert lead["pricing_page_visited"] == 1 and lead["video_watched"] == 1


def test_unknown_events_and_other_peoples_visits_are_refused(client, new_learner):
    a, b = new_learner(), new_learner()
    session_a, _ = _visit(client, a, [("page_view", 30)])
    r = client.post(f"{API}/track", json={"session_id": session_a, "event_type": "teleport"}, headers=a["headers"])
    assert r.status_code == 400
    r = client.post(
        f"{API}/track",
        json={"session_id": session_a, "course_slug": COURSE, "event_type": "page_view", "time_spent_sec": 5},
        headers=b["headers"],
    )
    assert r.status_code == 200
    row = db.fetchone(
        "SELECT session_id FROM behaviour_events WHERE user_id=? ORDER BY id DESC LIMIT 1", (b["user"]["id"],)
    )
    assert row["session_id"] is None  # a stale tab's visit id from another account is not counted


def test_cart_checkout_and_enrolment(client, new_learner):
    learner = new_learner()
    h = learner["headers"]
    price = client.get(f"{API}/courses/{COURSE}").json()["price"]
    assert client.post(f"{API}/cart", json={"course_slug": COURSE}, headers=h).status_code == 200
    assert client.post(f"{API}/cart", json={"course_slug": COURSE}, headers=h).status_code == 200  # once only
    assert len(client.get(f"{API}/cart", headers=h).json()["cart"]) == 1
    assert client.post(f"{API}/cart", json={"course_slug": "nope"}, headers=h).status_code == 404
    assert client.post(f"{API}/wishlist", json={"course_slug": OTHER_COURSE}, headers=h).status_code == 200
    assert [w["course_slug"] for w in client.get(f"{API}/wishlist", headers=h).json()["wishlist"]] == [OTHER_COURSE]

    start = client.post(f"{API}/checkout/start", headers=h).json()
    assert start["checkout_id"] and start["cart_value"] == price
    assert client.post(f"{API}/coupons/check", json={"code": "NOTREAL10"}, headers=h).status_code == 400
    assert client.post(f"{API}/checkout", json={"coupon_code": "NOTREAL10"}, headers=h).status_code == 400

    r = client.post(f"{API}/checkout", json={}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["discount_applied"] == "None"
    purchases = client.get(f"{API}/purchases", headers=h).json()["purchases"]
    assert [p["course_slug"] for p in purchases] == [COURSE]
    assert purchases[0]["price_paid"] == price
    assert client.get(f"{API}/cart", headers=h).json()["cart"] == []
    assert client.post(f"{API}/cart", json={"course_slug": COURSE}, headers=h).status_code == 409
    assert client.post(f"{API}/checkout", json={}, headers=h).status_code == 400  # the cart is empty now

    dashboard = client.get(f"{API}/dashboard", headers=h).json()
    assert len(dashboard["purchases"]) == 1


def test_only_enrolled_learners_can_review(client, new_learner):
    learner = new_learner(name="Kavya Iyer")
    h = learner["headers"]
    review = {"course_slug": COURSE, "rating": 5, "review_text": "Clear and practical."}
    assert client.post(f"{API}/reviews", json=review, headers=h).status_code == 403
    client.post(f"{API}/cart", json={"course_slug": COURSE}, headers=h)
    client.post(f"{API}/checkout", json={}, headers=h)
    assert client.post(f"{API}/reviews", json={**review, "rating": 9}, headers=h).status_code == 400
    assert client.post(f"{API}/reviews", json=review, headers=h).status_code == 200
    names = [r["name"] for r in client.get(f"{API}/reviews/{COURSE}").json()["reviews"]]
    assert "Kavya I." in names  # public pages show the first name and an initial only


def test_the_crm_sees_the_purchase(client, new_learner, owner):
    learner = new_learner(name="Meera Nair")
    h = learner["headers"]
    client.post(f"{API}/cart", json={"course_slug": COURSE}, headers=h)
    client.post(f"{API}/checkout", json={}, headers=h)
    found = client.get(f"{CRM}/leads", params={"search": learner["email"]}, headers=owner["headers"]).json()
    assert len(found["leads"]) == 1
    row = found["leads"][0]
    assert row["customer"] is True and row["simulated"] is False
    page = client.get(f"{CRM}/leads/{row['id']}", headers=owner["headers"]).json()
    assert [p["course_slug"] for p in page["purchases"]] == [COURSE]
    # customers are not sold the course they own: no next step for them
    now = client.get(f"{CRM}/leads/{row['id']}/now", headers=owner["headers"]).json()
    assert now["recommendation"] is None


def test_deleting_the_account_removes_every_record(client, new_learner, owner):
    learner = new_learner(name="Deepa Menon")
    uid, h = learner["user"]["id"], learner["headers"]
    _visit(client, learner, [("page_view", 45), ("pricing_view", 20)])
    client.post(f"{API}/wishlist", json={"course_slug": COURSE}, headers=h)
    client.post(f"{API}/qna", json={"course_slug": COURSE, "question": "Is there a weekend batch?"}, headers=h)
    assert db.fetchone("SELECT COUNT(*) AS n FROM behaviour_events WHERE user_id=?", (uid,))["n"] > 0

    r = client.delete(f"{API}/me", headers=h)
    assert r.status_code == 200
    tables = [r["name"] for r in db.fetchall("SELECT name FROM sqlite_master WHERE type='table'")]
    for table in tables:
        cols = [c["name"] for c in db.fetchall(f"PRAGMA table_info({table})")]
        if "user_id" in cols:
            n = db.fetchone(f"SELECT COUNT(*) AS n FROM {table} WHERE user_id=?", (uid,))["n"]
            assert n == 0, f"{table} still has rows of the deleted learner"
    assert db.get_user_by_email(learner["email"]) is None
    assert db.fetchone("SELECT COUNT(*) AS n FROM otp_tokens WHERE email=?", (learner["email"],))["n"] == 0
    audit = db.fetchall("SELECT detail FROM audit_log")
    assert all(learner["email"] not in (a["detail"] or "") for a in audit)
    assert client.get(f"{API}/auth/me", headers=h).status_code == 401
    found = client.get(f"{CRM}/leads", params={"search": learner["email"]}, headers=owner["headers"]).json()
    assert found["leads"] == []
