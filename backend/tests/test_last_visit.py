"""The team sees when a person was last on the website (their own visits, not the CRM's follow-ups), and the leads
list puts the latest visitors first."""

from __future__ import annotations

from support import API, CRM


def test_the_last_visit_is_the_persons_own_activity_and_orders_the_list(client, owner, new_learner):
    from app import db

    older, newer = new_learner("Older Visitor"), new_learner("Newer Visitor")
    db.execute(
        "UPDATE user_sessions SET login_at=?, last_active=? WHERE user_id=?",
        ("2026-01-05 09:00:00", "2026-01-05 09:20:00", older["user"]["id"]),
    )
    db.execute(
        "UPDATE user_sessions SET login_at=?, last_active=? WHERE user_id=?",
        ("2026-01-05 09:00:00", "2026-01-05 09:30:00", newer["user"]["id"]),
    )
    # the newer visitor comes back: the ping moves their last visit to now
    r = client.post(f"{API}/session/ping", json={"session_id": newer["session_id"]}, headers=newer["headers"])
    assert r.status_code == 200, r.text

    def row(who):
        r = client.get(f"{CRM}/leads", params={"search": who["email"]}, headers=owner["headers"])
        assert r.status_code == 200, r.text
        return r.json()["leads"][0]

    assert row(older)["last_active_at"] == "2026-01-05 09:20:00"
    assert row(newer)["last_active_at"] > "2026-01-05 09:30:00"  # now
    page = client.get(f"{CRM}/leads/{row(older)['id']}", headers=owner["headers"]).json()
    assert page["last_active_at"] == "2026-01-05 09:20:00"

    listed = client.get(f"{CRM}/leads", params={"limit": 5000}, headers=owner["headers"]).json()["leads"]
    seen = [x["last_active_at"] for x in listed]
    assert seen == sorted(seen, reverse=True)  # latest visit first by default
    ids = [x["user_id"] for x in listed]
    assert ids.index(newer["user"]["id"]) < ids.index(older["user"]["id"])
