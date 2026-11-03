"""
Shared set-up for the backend tests.

Every run works in its own temporary data folder (database, models, logs), so backend/data is never touched, no
email is sent and Gemini is never called. The environment is set here, before the app is imported, because the
settings are read once at import time.

The starting models are trained once per run on a small simulated sample: a few seconds instead of minutes, through
exactly the same code as the real ones.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest
from support import API, CRM, LEARNER_PASSWORD, OWNER_EMAIL, OWNER_PASSWORD, bearer, unique_email

DATA_DIR = Path(tempfile.mkdtemp(prefix="xeducation-tests-"))

for _name in (
    "DATABASE_PATH",
    "DB_PATH",
    "DB_PATH_OVERRIDE",
    "MODELS_DIR",
    "SIMULATION_DB_PATH",
    "SIM_WORLD_DB",
    "LOG_FILE",
    "RULES_PATH",
    "CRM_SETTINGS",
):
    os.environ.pop(_name, None)
os.environ.update(
    DATA_DIR=str(DATA_DIR),
    ENVIRONMENT="test",
    DEMO_MODE="true",
    LOG_LEVEL="WARNING",
    SCHEDULER_ENABLED="false",
    SIMULATION_ENABLED="false",
    GMAIL_USER="",
    GMAIL_APP_PASSWORD="",
    GEMINI_API_KEY="",
    GEMINI_MODEL="",
    JWT_SECRET="tests-only-signing-secret-0123456789abcdef",
    CRM_OWNER_EMAIL=OWNER_EMAIL,
    CRM_OWNER_NAME="Test Owner",
    CRM_OWNER_PASSWORD="",
)


@pytest.fixture(scope="session", autouse=True)
def starting_models():
    """The database and small starting models, made once per run in the temporary data folder."""
    from app import db
    from app.ml.training import lead, uplift

    def quiet(*_args, **_kwargs):
        return None

    db.init_db()
    lead.train(rows=6000, say=quiet)
    uplift.train(say=quiet, train_rows=8000, test_rows=4000, write_report=False)
    yield
    shutil.rmtree(DATA_DIR, ignore_errors=True)


@pytest.fixture(scope="session")
def client(starting_models):
    """The API in-process, with its start-up and shut-down (the background jobs stay off)."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def outbox(monkeypatch):
    """Every one-time code the learner API sends, as dicts with to, code and purpose (the real mailer still runs:
    without Gmail it only records the email)."""
    from app.api.learner import auth
    from app.services import mailer

    sent: list[dict] = []

    def record(to, code, name, purpose="signup"):
        sent.append({"to": to, "code": code, "purpose": purpose})
        return mailer.send_otp_email(to, code, name, purpose=purpose)

    monkeypatch.setattr(auth, "send_otp_email", record)
    return sent


@pytest.fixture
def new_learner(client, outbox):
    """Factory: sign up and verify a learner through the API, the way the website does."""

    def make(name: str = "Riya Sharma", email: str | None = None, password: str = LEARNER_PASSWORD) -> dict:
        email = email or unique_email()
        r = client.post(f"{API}/auth/signup", json={"name": name, "email": email, "password": password})
        assert r.status_code == 200, r.text
        code = next(m["code"] for m in reversed(outbox) if m["to"] == email and m["purpose"] == "signup")
        r = client.post(f"{API}/auth/verify-otp", json={"email": email, "otp": code})
        assert r.status_code == 200, r.text
        body = r.json()
        return {
            "email": email,
            "password": password,
            "token": body["token"],
            "headers": bearer(body["token"]),
            "user": body["user"],
            "session_id": body["session_id"],
        }

    return make


@pytest.fixture(scope="session")
def owner_first_password(client) -> str:
    """The random first password the owner account gets when CRM_OWNER_PASSWORD is not set."""
    from app.core.config import get_settings

    text = get_settings().initial_password_file.read_text(encoding="utf-8")
    return next(line.split()[-1] for line in text.splitlines() if line.strip().startswith("password"))


@pytest.fixture(scope="session")
def owner(client, owner_first_password) -> dict:
    """The owner (an admin), signed in after choosing their own password at the first sign-in."""
    r = client.post(f"{CRM}/auth/login", json={"email": OWNER_EMAIL, "password": owner_first_password})
    assert r.status_code == 200, r.text
    first = r.json()
    # until they choose their own password, the owner can only open their own account
    first["leads_status"] = client.get(f"{CRM}/leads", headers=bearer(first["token"])).status_code
    r = client.post(
        f"{CRM}/me/password",
        json={"current_password": owner_first_password, "new_password": OWNER_PASSWORD},
        headers=bearer(first["token"]),
    )
    assert r.status_code == 200, r.text
    r = client.post(f"{CRM}/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD})
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    return {"token": token, "headers": bearer(token), "member": r.json()["member"], "first": first}


@pytest.fixture
def team_member(client, owner):
    """Factory: an account made by the owner, signed in after choosing its own password."""

    def make(role: str = "counsellor") -> dict:
        email = unique_email(role)
        given, own = "Given-pass-2026", "Own-pass-2026"
        r = client.post(
            f"{CRM}/team",
            json={"name": f"Test {role}", "email": email, "role": role, "password": given},
            headers=owner["headers"],
        )
        assert r.status_code == 200, r.text
        member_id = r.json()["member"]["id"]
        r = client.post(f"{CRM}/auth/login", json={"email": email, "password": given})
        assert r.status_code == 200, r.text
        r = client.post(
            f"{CRM}/me/password",
            json={"current_password": given, "new_password": own},
            headers=bearer(r.json()["token"]),
        )
        assert r.status_code == 200, r.text
        r = client.post(f"{CRM}/auth/login", json={"email": email, "password": own})
        token = r.json()["token"]
        return {"id": member_id, "email": email, "role": role, "token": token, "headers": bearer(token)}

    return make
