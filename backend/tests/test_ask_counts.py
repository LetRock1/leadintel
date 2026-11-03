"""Ask the CRM answers the plain counting questions a new marketer asks first ("How many leads do we have?"), from
the live data, with real people and simulated learners kept apart."""

from __future__ import annotations

from support import CRM


def _ask(client, owner, q):
    r = client.post(f"{CRM}/copilot", json={"question": q}, headers=owner["headers"])
    assert r.status_code == 200, r.text
    return r.json()


def test_counting_questions_are_answered_from_the_data(client, owner, new_learner):
    from app import db

    new_learner("Count Me")
    out = _ask(client, owner, "How many real leads do we have?")
    assert out["intent"] == "counts"
    facts = out["tools"][0]["data"]
    people = db.fetchall("SELECT email FROM users WHERE id IN (SELECT user_id FROM leads)")
    sim = sum(1 for p in people if p["email"].endswith("@demo.xeducation.test"))
    assert facts["leads"] == {"all": len(people), "real": len(people) - sim, "simulated": sim}
    assert facts["leads"]["real"] >= 1
    assert f"Leads: {len(people):,}" in out["answer"]
    customers = db.fetchone("SELECT COUNT(DISTINCT user_id) AS c FROM purchases")["c"]
    assert facts["customers"]["all"] == customers

    today = _ask(client, owner, "How many sign-ups today?")
    assert today["intent"] == "counts" and today["tools"][0]["data"]["days"] == 1
    assert today["tools"][0]["data"]["new_leads"]["all"] >= 1  # the learner made above signed up today
    assert "New today" in today["answer"]
    month = _ask(client, owner, "number of customers in the last 2 months")
    assert month["intent"] == "counts" and month["tools"][0]["data"]["days"] == 60
    # questions that belong to another tool still go there
    assert _ask(client, owner, "How many counsellors should we hire?")["intent"] == "planner"
    assert _ask(client, owner, "How much did we sell in the last 30 days?")["intent"] == "revenue"
