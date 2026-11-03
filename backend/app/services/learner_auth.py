"""
One-time codes for learners: sign-up verification and password reset.

A code is six random digits (``secrets``), valid for OTP_EXPIRY_MINUTES (default 10). Only a keyed hash of it is
stored (HMAC-SHA256 with the server's signing secret), so a copy of the database does not reveal a live code. Each
wrong guess counts; after five the code is burned, so a six-digit code cannot be brute-forced. A new code replaces
the previous one for the same address and purpose.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import string
from datetime import datetime, timedelta

from app import db
from app.core import security
from app.core.config import get_settings

MAX_OTP_ATTEMPTS = 5
RESEND_SECONDS = 60


def generate_otp() -> str:
    return "".join(secrets.choice(string.digits) for _ in range(6))


def code_digest(email: str, code: str, purpose: str = "signup") -> str:
    """The stored form of a code: HMAC-SHA256 of purpose, address and code, keyed with the server's signing secret."""
    message = f"{purpose}:{(email or '').strip().lower()}:{(code or '').strip()}".encode()
    return hmac.new(security.signing_secret().encode(), message, hashlib.sha256).hexdigest()


def save_otp(email: str, otp: str, purpose: str = "signup") -> None:
    db.execute("UPDATE otp_tokens SET used=1 WHERE email=? AND COALESCE(purpose,'signup')=?", (email, purpose))
    expires = (datetime.now() + timedelta(minutes=get_settings().otp_expiry_minutes)).strftime("%Y-%m-%d %H:%M:%S")
    db.execute(
        "INSERT INTO otp_tokens (email, code_hash, expires_at, purpose, attempts) VALUES (?,?,?,?,0)",
        (email, code_digest(email, otp, purpose), expires, purpose),
    )


def last_otp_age_seconds(email: str, purpose: str = "signup") -> float | None:
    row = db.fetchone(
        """SELECT (julianday('now','localtime') - julianday(created_at)) * 86400 AS age
                         FROM otp_tokens WHERE email=? AND COALESCE(purpose,'signup')=?
                         ORDER BY id DESC LIMIT 1""",
        (email, purpose),
    )
    return row["age"] if row else None


def verify_otp(email: str, otp: str, purpose: str = "signup") -> bool:
    """Checks the latest live code. Each wrong guess counts; after five the code is burned."""
    row = db.fetchone(
        """SELECT * FROM otp_tokens
                         WHERE email=? AND COALESCE(purpose,'signup')=? AND used=0
                           AND expires_at > datetime('now','localtime')
                         ORDER BY id DESC LIMIT 1""",
        (email, purpose),
    )
    if not row or not row.get("code_hash"):
        return False
    if hmac.compare_digest(row["code_hash"], code_digest(email, otp, purpose)):
        db.execute("UPDATE otp_tokens SET used=1 WHERE id=?", (row["id"],))
        return True
    attempts = (row.get("attempts") or 0) + 1
    db.execute(
        "UPDATE otp_tokens SET attempts=?, used=? WHERE id=?",
        (attempts, 1 if attempts >= MAX_OTP_ATTEMPTS else 0, row["id"]),
    )
    return False


def purge_old(days: int = 1) -> int:
    """Delete codes and simulated inbox emails older than a day (the hourly housekeeping job)."""
    cutoff = f"-{int(days)} days"
    removed = db.execute_rowcount("DELETE FROM otp_tokens WHERE created_at < datetime('now','localtime',?)", (cutoff,))
    removed += db.execute_rowcount(
        "DELETE FROM simulated_inbox WHERE created_at < datetime('now','localtime',?)", (cutoff,)
    )
    return removed
