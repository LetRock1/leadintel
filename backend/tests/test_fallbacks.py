"""
A live demo must not stop because Gmail or Gemini is missing, slow or down. Nothing here sends a real email or calls
Google: SMTP and the Gemini client are replaced by stand-ins.
"""

from __future__ import annotations

import json
import re
import smtplib
import time

import pytest
from support import API, LEARNER_PASSWORD, unique_email

from app import db
from app.core import rules
from app.services import content, gemini, mailer


class FakeSMTP:
    """Stands in for smtplib.SMTP_SSL. behaviour: 'ok', or an exception to raise on login."""

    behaviour: object = "ok"
    sent: list = []
    opened = 0

    def __init__(self, host, port, timeout=None):
        FakeSMTP.opened += 1
        if isinstance(FakeSMTP.behaviour, OSError):
            raise FakeSMTP.behaviour

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def login(self, user, password):
        if isinstance(FakeSMTP.behaviour, Exception):
            raise FakeSMTP.behaviour

    def sendmail(self, sender, to, message):
        FakeSMTP.sent.append((sender, to, message))


@pytest.fixture
def gmail(monkeypatch):
    """Gmail 'configured' with a stand-in SMTP server; the pause after a network error starts cleared."""
    monkeypatch.setattr(mailer, "GMAIL_USER", "sender@example.com")
    monkeypatch.setattr(mailer, "GMAIL_PASS", "app-password")
    monkeypatch.setattr(mailer, "_paused_until", {"t": 0.0})
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
    FakeSMTP.behaviour, FakeSMTP.sent, FakeSMTP.opened = "ok", [], 0
    return FakeSMTP


def test_without_gmail_emails_are_recorded_not_sent():
    ok, message = mailer.send_simple_email("someone@example.com", "Hello", "Body")
    assert ok and mailer.mailer_not_configured(message)


def test_simulated_learners_are_never_mailed(gmail):
    ok, message = mailer.send_otp_email("asha.1@demo.xeducation.test", "123456", "Asha")
    assert ok and "Simulated learner" in message
    assert gmail.opened == 0
    inbox = db.fetchone(
        "SELECT subject FROM simulated_inbox WHERE email=? ORDER BY id DESC LIMIT 1", ("asha.1@demo.xeducation.test",)
    )
    assert inbox and inbox["subject"].endswith("123456")  # where the simulator reads its code


def test_a_marketing_email_carries_one_click_unsubscribe(gmail):
    ok, message = mailer.send_marketing_email(
        "learner@example.com",
        "New batch",
        "Hi **Asha**",
        "https://site.example/c",
        "View course",
        unsubscribe_url="https://site.example/unsubscribe?t=abc",
    )
    assert ok and message == "Sent to learner@example.com"
    raw = gmail.sent[-1][2]
    assert "List-Unsubscribe: <https://site.example/unsubscribe?t=abc>" in raw
    assert "List-Unsubscribe-Post: List-Unsubscribe=One-Click" in raw


def test_a_network_error_pauses_email_for_five_minutes(gmail):
    gmail.behaviour = OSError("Network is unreachable")
    ok, message = mailer.send_simple_email("a@example.com", "One", "Body")
    assert not ok and "Could not reach Gmail" in message
    opened = gmail.opened
    started = time.perf_counter()
    ok, message = mailer.send_simple_email("b@example.com", "Two", "Body")
    assert not ok and "paused" in message
    assert gmail.opened == opened  # no second connection attempt
    assert time.perf_counter() - started < 0.5
    assert mailer._paused_until["t"] - time.time() > 250


def test_a_refused_address_or_password_does_not_pause_the_others(gmail):
    gmail.behaviour = smtplib.SMTPAuthenticationError(535, b"bad credentials")
    ok, message = mailer.send_simple_email("a@example.com", "One", "Body")
    assert not ok and "refused the login" in message
    assert mailer._paused_until["t"] == 0.0
    gmail.behaviour = "ok"
    assert mailer.send_simple_email("b@example.com", "Two", "Body")[0]


def test_signup_goes_on_in_demo_mode_when_the_code_cannot_be_emailed(client, monkeypatch):
    from app.api.learner import auth

    monkeypatch.setattr(auth, "send_otp_email", lambda *a, **k: (False, "Could not reach Gmail (OSError)"))
    monkeypatch.setattr(rules, "DEMO_MODE", True)
    email = unique_email()
    r = client.post(f"{API}/auth/signup", json={"name": "Asha", "email": email, "password": LEARNER_PASSWORD})
    assert r.status_code == 200 and "demo mode" in r.json()["message"]
    assert db.get_user_by_email(email) is not None


def test_outside_demo_mode_signup_is_refused_and_the_half_made_account_removed(client, monkeypatch):
    from app.api.learner import auth

    monkeypatch.setattr(auth, "send_otp_email", lambda *a, **k: (False, "Could not reach Gmail (OSError)"))
    monkeypatch.setattr(rules, "DEMO_MODE", False)
    email = unique_email()
    r = client.post(f"{API}/auth/signup", json={"name": "Asha", "email": email, "password": LEARNER_PASSWORD})
    assert r.status_code == 503
    assert db.get_user_by_email(email) is None


# Gemini


class FakeModels:
    def __init__(self, behaviour):
        self.behaviour, self.calls = behaviour, []

    def generate_content(self, model, contents, config=None):
        self.calls.append(model)
        what = self.behaviour.get(model, "ok")
        if isinstance(what, Exception):
            raise what
        return type("Response", (), {"text": what if what != "ok" else "fine"})()


class FakeClient:
    def __init__(self, behaviour):
        self.models = FakeModels(behaviour)


@pytest.fixture
def fake_gemini(monkeypatch):
    def use(behaviour):
        client = FakeClient(behaviour)
        monkeypatch.setattr(gemini, "_key", lambda: "test-key")
        monkeypatch.setattr(gemini, "_state", {"model": None, "down_until": 0.0, "disabled": False, "client": client})
        return client.models

    return use


def _draft():
    return content.generate_content(
        "Asha Rao",
        "Working Professional",
        "Finance Management",
        "Business Analytics",
        "Nurture via Email/WhatsApp",
        course_slug="business-analytics",
    )


def test_without_a_key_the_templates_write_the_message():
    assert not gemini.enabled()
    with pytest.raises(RuntimeError):
        gemini.generate("hello")
    draft = _draft()
    assert "Business Analytics" in draft["email_body"] and draft["email_subject"] and draft["whatsapp_message"]


def test_a_retired_model_name_falls_through_to_the_next(fake_gemini):
    first, second = gemini.CANDIDATES[0], gemini.CANDIDATES[1]
    models = fake_gemini({first: Exception(f"404 NOT_FOUND: models/{first} is not found")})
    assert gemini.generate("hello") == "fine"
    assert models.calls == [first, second]
    assert gemini.model_name() == second
    gemini.generate("again")
    assert models.calls[-1] == second  # the one that works is remembered


def test_a_network_error_pauses_gemini_and_the_templates_take_over(fake_gemini):
    models = fake_gemini({m: Exception("connection reset by peer") for m in gemini.CANDIDATES})
    with pytest.raises(Exception, match="connection"):
        gemini.generate("hello")
    assert not gemini.enabled()
    calls = len(models.calls)
    draft = _draft()  # no waiting: Gemini is skipped while paused
    assert len(models.calls) == calls
    assert "Business Analytics" in draft["email_body"]


def test_gemini_writes_the_message_when_it_answers(fake_gemini):
    answer = {
        "email_subject": "Business Analytics for your career",
        "email_body": "Hi Asha, a short note about Business Analytics.",
        "whatsapp_message": "Hi Asha",
        "call_script": "Hello",
    }
    fake_gemini({m: json.dumps(answer) for m in gemini.CANDIDATES})
    draft = _draft()
    assert draft["email_subject"] == answer["email_subject"]
    # a personal code for the offer's discount level (random characters, so every copy is unique)
    prefix = content.coupon_code_for(draft["offer_pct"]).rsplit("-", 1)[0]
    assert re.fullmatch(rf"{prefix}-[A-HJ-NP-Z2-9]{{5}}", draft["coupon_code"]), draft["coupon_code"]


def test_a_malformed_gemini_answer_falls_back_to_the_templates(fake_gemini):
    fake_gemini({m: '{"email_subject": ""}' for m in gemini.CANDIDATES})
    draft = _draft()
    assert draft["email_subject"] and "Business Analytics" in draft["email_body"]
