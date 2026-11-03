"""Constants and small helpers the tests share (kept out of conftest.py, which pytest loads by itself)."""

from __future__ import annotations

import uuid

OWNER_EMAIL = "owner@example.com"
OWNER_PASSWORD = "Owner-tests-2026"
LEARNER_PASSWORD = "Learner-tests-2026"
API = "/api/v1"
CRM = "/api/v1/crm"


def unique_email(prefix: str = "learner") -> str:
    """A fresh address on example.com (reserved for documentation and tests, RFC 2606)."""
    return f"{prefix}.{uuid.uuid4().hex[:10]}@example.com"


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
