"""
The CRM team: the owner's first password, roles checked on every request, record-level access for counsellors,
lock-out after wrong passwords, and an audit log that names the team but not the learners.
"""

from __future__ import annotations

from support import API, CRM, OWNER_EMAIL, bearer, unique_email

from app import db
from app.core.config import get_settings


def test_the_owners_first_password_is_replaced_at_the_first_sign_in(client, owner, owner_first_password):
    # before choosing their own password the owner could only open their own account
    assert owner["first"]["member"]["must_change_password"] is True
    assert owner["first"]["leads_status"] == 403
    # the token of that first sign-in stopped working when the password changed (all other sessions end)
    assert client.get(f"{CRM}/me", headers=bearer(owner["first"]["token"])).status_code == 401
    # the file with the first password is deleted once it has been used, and the old password stops working
    assert not get_settings().initial_password_file.exists()
    r = client.post(f"{CRM}/auth/login", json={"email": OWNER_EMAIL, "password": owner_first_password})
    assert r.status_code == 401
    me = client.get(f"{CRM}/me", headers=owner["headers"]).json()
    assert me["role"] == "admin" and me["is_owner"] is True
    assert set(me["can"]) == {"team", "audit", "marketing", "leads"}


def test_the_first_password_is_never_written_to_the_log(client, owner_first_password):
    log_file = get_settings().log_path
    text = log_file.read_text(encoding="utf-8") if log_file.exists() else ""
    assert owner_first_password not in text


def test_new_accounts_must_choose_their_own_password(client, owner):
    email = unique_email("counsellor")
    r = client.post(
        f"{CRM}/team",
        json={"name": "New Counsellor", "email": email, "role": "counsellor", "password": "Given-pass-2026"},
        headers=owner["headers"],
    )
    assert r.status_code == 200
    token = client.post(f"{CRM}/auth/login", json={"email": email, "password": "Given-pass-2026"}).json()["token"]
    assert client.get(f"{CRM}/leads", headers=bearer(token)).status_code == 403
    assert client.get(f"{CRM}/me", headers=bearer(token)).status_code == 200
    r = client.post(
        f"{CRM}/me/password",
        json={"current_password": "Given-pass-2026", "new_password": "Given-pass-2026"},
        headers=bearer(token),
    )
    assert r.status_code == 400  # the same password again is refused


def test_team_rules(client, owner):
    def add(**over):
        body = {"name": "Someone", "email": unique_email("member"), "role": "counsellor", "password": "Given-pass-2026"}
        return client.post(f"{CRM}/team", json={**body, **over}, headers=owner["headers"])

    assert add(role="superuser").status_code == 400
    assert add(email="not-an-address").status_code == 400
    assert add(password="lettersonly").status_code == 400  # team passwords need a digit
    assert add(email=OWNER_EMAIL).status_code == 409


def test_roles_are_checked_by_the_api(client, team_member, owner):
    counsellor, marketing = team_member("counsellor"), team_member("marketing")
    who = (owner, marketing, counsellor)
    reads = [
        # (path, admin, marketing, counsellor): the whole team may read campaigns and tests; exports, the WhatsApp
        # log, the team and the audit log are not for everyone
        ("/leads", 200, 200, 200),
        ("/actions", 200, 200, 200),
        ("/campaigns", 200, 200, 200),
        ("/leads/export.csv", 200, 200, 403),
        ("/whatsapp/log", 200, 200, 403),
        ("/team", 200, 403, 403),
        ("/audit", 200, 403, 403),
    ]
    for path, *expected in reads:
        got = [client.get(f"{CRM}{path}", headers=w["headers"]).status_code for w in who]
        assert got == expected, f"GET {path}: {got} != {expected}"

    campaign = {
        "name": "Role check",
        "tier": "Marketing Campaign",
        "subject": "Hello",
        "body": "Hi {first_name}",
        "scheduled_at": "2099-01-01 10:00",
    }
    assert client.post(f"{CRM}/campaigns", json=campaign, headers=counsellor["headers"]).status_code == 403
    assert (
        client.post(f"{CRM}/learning/run", params={"dry_run": True}, headers=counsellor["headers"]).status_code == 403
    )
    member = {"name": "X", "email": unique_email("x"), "role": "admin", "password": "Given-pass-2026"}
    assert client.post(f"{CRM}/team", json=member, headers=marketing["headers"]).status_code == 403
    me = client.get(f"{CRM}/me", headers=counsellor["headers"]).json()
    assert me["can"] == ["leads"]


def test_counsellors_change_only_their_own_and_unassigned_leads(client, team_member, owner, new_learner):
    mine, other = team_member("counsellor"), team_member("counsellor")
    learner = new_learner()
    lead = client.get(f"{CRM}/leads", params={"search": learner["email"]}, headers=owner["headers"]).json()["leads"][0]
    r = client.put(f"{CRM}/leads/{lead['id']}/owner", json={"member_id": mine["id"]}, headers=owner["headers"])
    assert r.status_code == 200, r.text
    note = {"text": "Called, asked to ring back next week."}
    assert client.post(f"{CRM}/leads/{lead['id']}/notes", json=note, headers=mine["headers"]).status_code == 200
    assert client.post(f"{CRM}/leads/{lead['id']}/notes", json=note, headers=other["headers"]).status_code == 403
    page = client.get(f"{CRM}/leads/{lead['id']}", headers=other["headers"]).json()
    assert page["can_change"] is False and page["can_change_why"]


def test_five_wrong_passwords_lock_a_team_address(client, team_member):
    member = team_member("marketing")
    for _ in range(5):
        r = client.post(f"{CRM}/auth/login", json={"email": member["email"], "password": "Wrong-pass-2026"})
        assert r.status_code == 401
    assert (
        client.post(f"{CRM}/auth/login", json={"email": member["email"], "password": "Own-pass-2026"}).status_code
        == 429
    )


def test_switched_off_accounts_lose_access_at_once(client, team_member, owner):
    member = team_member("counsellor")
    assert client.get(f"{CRM}/leads", headers=member["headers"]).status_code == 200
    r = client.put(f"{CRM}/team/{member['id']}", json={"active": False}, headers=owner["headers"])
    assert r.status_code == 200
    assert client.get(f"{CRM}/leads", headers=member["headers"]).status_code == 401  # the token still exists


def test_the_audit_log_names_the_team_but_not_the_learners(client, owner, new_learner):
    learner = new_learner()
    lead = client.get(f"{CRM}/leads", params={"search": learner["email"]}, headers=owner["headers"]).json()["leads"][0]
    client.post(
        f"{CRM}/leads/{lead['id']}/notes", json={"text": "Interested in weekend batches."}, headers=owner["headers"]
    )
    entries = client.get(f"{CRM}/audit", headers=owner["headers"]).json()
    rows = entries["entries"] if isinstance(entries, dict) else entries
    assert any(e["action"] == "login" for e in rows)
    for e in db.fetchall("SELECT * FROM audit_log"):
        text = " ".join(str(v) for v in e.values() if v is not None)
        assert learner["email"] not in text
        assert "weekend batches" not in text


def test_learner_api_is_separate_from_the_crm(client, new_learner):
    learner = new_learner()
    # a learner cannot reach CRM data with their own token, nor read someone else's account
    assert client.get(f"{CRM}/leads", headers=learner["headers"]).status_code == 401
    assert client.get(f"{API}/dashboard", headers=learner["headers"]).json()["user"]["email"] == learner["email"]
