"""The Start here page: every team member can open it, and it says honestly what is set up."""

from __future__ import annotations

from support import CRM


def test_every_team_member_sees_what_is_set_up(client, owner, team_member):
    for who in (owner, team_member("marketing"), team_member("counsellor")):
        r = client.get(f"{CRM}/start", headers=who["headers"])
        assert r.status_code == 200, r.text
        s = r.json()
        assert s["email_sending"] is False  # the tests run without Gmail: emails are only recorded
        assert 0 < s["rules"]["control_share"] < 1
        assert 0 <= s["rules"]["learning_steps"] < 1
        assert s["rules"]["daily_calls"] >= 1 and s["rules"]["outcome_window_days"] >= 1
        assert s["team_members"] >= 1 and s["learners"]["real"] >= 0 and s["learners"]["simulated"] >= 0
    assert client.get(f"{CRM}/start").status_code == 401  # only for the team


def test_a_sign_up_without_the_code_is_not_counted_as_a_learner(client, owner, new_learner):
    from support import API, unique_email

    count = lambda: client.get(f"{CRM}/start", headers=owner["headers"]).json()["learners"]["real"]  # noqa: E731
    before = count()
    r = client.post(f"{API}/auth/signup", json={"name": "No Code", "email": unique_email(), "password": "No-code-2026"})
    assert r.status_code == 200, r.text
    assert count() == before  # signed up, never entered the emailed code
    new_learner("With Code")
    assert count() == before + 1
