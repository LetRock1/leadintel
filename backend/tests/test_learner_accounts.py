"""Learner accounts: sign-up with an emailed code, sign-in, lock-out, password reset and token separation."""

from __future__ import annotations

import re

from support import API, CRM, LEARNER_PASSWORD, bearer, unique_email

from app import db


def _signup(client, email, password=LEARNER_PASSWORD, name="Asha Rao"):
    return client.post(f"{API}/auth/signup", json={"name": name, "email": email, "password": password})


def _code_for(outbox, email, purpose="signup"):
    return next(m["code"] for m in reversed(outbox) if m["to"] == email and m["purpose"] == purpose)


def test_signup_verify_and_sign_in(client, outbox):
    email = unique_email()
    r = _signup(client, email)
    assert r.status_code == 200
    # without Gmail the code is not emailed: the learner is told where to find it
    assert "backend window" in r.json()["message"]
    code = _code_for(outbox, email)
    assert re.fullmatch(r"\d{6}", code)

    wrong = "000000" if code != "000000" else "111111"
    assert client.post(f"{API}/auth/verify-otp", json={"email": email, "otp": wrong}).status_code == 400
    r = client.post(f"{API}/auth/verify-otp", json={"email": email, "otp": code})
    assert r.status_code == 200
    token = r.json()["token"]
    me = client.get(f"{API}/auth/me", headers=bearer(token)).json()
    assert me["user"]["email"] == email
    assert "password_hash" not in me["user"]

    # every verified person is a contact in the CRM straight away
    assert db.get_user_lead(r.json()["user"]["id"]) is not None

    r = client.post(f"{API}/auth/login", json={"email": email.upper(), "password": LEARNER_PASSWORD})
    assert r.status_code == 200
    assert r.json()["token"]


def test_codes_are_stored_only_as_keyed_hashes(client, outbox):
    email = unique_email()
    assert _signup(client, email).status_code == 200
    code = _code_for(outbox, email)
    row = db.fetchone("SELECT * FROM otp_tokens WHERE email=? ORDER BY id DESC LIMIT 1", (email,))
    assert "otp" not in row
    assert re.fullmatch(r"[0-9a-f]{64}", row["code_hash"])
    assert code not in str(row)


def test_a_code_is_burned_after_five_wrong_guesses(client, outbox):
    email = unique_email()
    _signup(client, email)
    code = _code_for(outbox, email)
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        assert client.post(f"{API}/auth/verify-otp", json={"email": email, "otp": wrong}).status_code == 400
    # even the right code no longer works
    assert client.post(f"{API}/auth/verify-otp", json={"email": email, "otp": code}).status_code == 400


def test_signup_rules(client, new_learner):
    assert _signup(client, unique_email(), password="short").status_code == 400
    assert _signup(client, "not-an-address").status_code == 400
    assert (
        client.post(f"{API}/auth/signup", json={"name": " ", "email": unique_email(), "password": "x" * 10}).status_code
        == 400
    )
    taken = new_learner()["email"]
    assert _signup(client, taken).status_code == 409


def test_unverified_accounts_cannot_sign_in(client, outbox):
    email = unique_email()
    _signup(client, email)
    r = client.post(f"{API}/auth/login", json={"email": email, "password": LEARNER_PASSWORD})
    assert r.status_code == 403


def test_five_wrong_passwords_lock_the_address(client, new_learner):
    learner = new_learner()
    for _ in range(5):
        r = client.post(f"{API}/auth/login", json={"email": learner["email"], "password": "Wrong-pass-2026"})
        assert r.status_code == 401
    r = client.post(f"{API}/auth/login", json={"email": learner["email"], "password": learner["password"]})
    assert r.status_code == 429  # locked, even with the right password


def test_unknown_address_gets_the_same_answer_as_a_wrong_password(client):
    r = client.post(f"{API}/auth/login", json={"email": unique_email(), "password": "Whatever-2026"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Incorrect email address or password."


def test_password_reset_with_an_emailed_code(client, new_learner, outbox):
    learner = new_learner()
    r = client.post(f"{API}/auth/forgot-password", json={"email": learner["email"]})
    assert r.status_code == 200
    code = _code_for(outbox, learner["email"], "reset")
    r = client.post(
        f"{API}/auth/reset-password",
        json={"email": learner["email"], "otp": code, "new_password": "Brand-new-2026"},
    )
    assert r.status_code == 200
    assert (
        client.post(f"{API}/auth/login", json={"email": learner["email"], "password": learner["password"]}).status_code
        == 401
    )
    assert (
        client.post(f"{API}/auth/login", json={"email": learner["email"], "password": "Brand-new-2026"}).status_code
        == 200
    )


def test_forgot_password_does_not_reveal_who_is_registered(client, outbox):
    r = client.post(f"{API}/auth/forgot-password", json={"email": unique_email()})
    assert r.status_code == 200
    assert "If an account exists" in r.json()["message"]
    assert outbox == []


def test_change_password_needs_the_current_one(client, new_learner):
    learner = new_learner()
    r = client.post(
        f"{API}/auth/change-password",
        json={"current_password": "Not-the-one-2026", "new_password": "Another-2026"},
        headers=learner["headers"],
    )
    assert r.status_code == 400
    r = client.post(
        f"{API}/auth/change-password",
        json={"current_password": learner["password"], "new_password": "Another-2026"},
        headers=learner["headers"],
    )
    assert r.status_code == 200


def test_learner_and_crm_tokens_are_not_interchangeable(client, new_learner, owner):
    learner = new_learner()
    assert client.get(f"{CRM}/me", headers=learner["headers"]).status_code == 401
    assert client.get(f"{API}/auth/me", headers=owner["headers"]).status_code == 401
    assert client.get(f"{API}/auth/me").status_code == 401
    tampered = learner["token"][:-4] + ("AAAA" if not learner["token"].endswith("AAAA") else "BBBB")
    assert client.get(f"{API}/auth/me", headers=bearer(tampered)).status_code == 401
