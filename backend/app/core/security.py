"""
Passwords and sign-in tokens for both kinds of user: learners on the website and people on the CRM team.

Passwords are stored as salted PBKDF2-SHA256 hashes (600,000 iterations, the OWASP 2023 recommendation),
never in clear text; checking a password takes the same time whether the account exists or not.

Tokens are JWTs (HS256). Learner tokens and team tokens carry different audiences ("learner", "crm"),
so a learner's token can never open the CRM and the other way round. Every token also carries a short
fingerprint of the account's password hash ("pv"): changing or resetting a password changes it, so every
token issued before then stops working (all other sessions are signed out). The signing secret comes from
JWT_SECRET in backend/.env; without it a random secret is created once and kept in the database.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import get_settings

ITERATIONS = 600_000
ALGORITHM = "HS256"
AUD_LEARNER = "learner"
AUD_CRM = "crm"
_secret: dict[str, str] = {}
_dummy: dict[str, str] = {}


# passwords
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str | None, stored: str | None) -> bool:
    try:
        algo, iterations, salt, dk = (stored or "").split("$")
        if algo != "pbkdf2_sha256":
            return False
        calc = hashlib.pbkdf2_hmac("sha256", (password or "").encode("utf-8"), base64.b64decode(salt), int(iterations))
        return hmac.compare_digest(calc, base64.b64decode(dk))
    except (ValueError, TypeError):
        return False


def waste_time(password: str | None) -> None:
    """A wrong address costs as long as a wrong password, so nobody can find out which addresses exist."""
    if "hash" not in _dummy:
        _dummy["hash"] = hash_password(secrets.token_hex(8))
    verify_password(password, _dummy["hash"])


def password_problem(password: str | None, *, require_digit: bool = True) -> str | None:
    """None if the password is acceptable, else what is missing (NIST SP 800-63B: at least 8 characters)."""
    p = password or ""
    if len(p) < 8:
        return "Use at least 8 characters."
    if len(p) > 128:
        return "Use at most 128 characters."
    if require_digit and (not any(ch.isalpha() for ch in p) or not any(ch.isdigit() for ch in p)):
        return "Use letters and at least one digit."
    return None


def generate_password(length: int = 16) -> str:
    """A random password with letters and digits (no look-alike characters), for first sign-ins."""
    alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    while True:
        p = "".join(secrets.choice(alphabet) for _ in range(length))
        if any(c.isdigit() for c in p) and any(c.isalpha() for c in p):
            return p


def constant_time_equals(a: str | None, b: str | None) -> bool:
    return hmac.compare_digest((a or "").encode("utf-8"), (b or "").encode("utf-8"))


# tokens
def signing_secret() -> str:
    """JWT_SECRET from .env, else a random secret created once and kept in the database."""
    if "v" not in _secret:
        configured = get_settings().jwt_secret
        if configured:
            _secret["v"] = configured
        else:
            from app.db import app_setting, put_app_setting

            v = app_setting("jwt_secret")
            if not v:
                v = secrets.token_urlsafe(48)
                put_app_setting("jwt_secret", v)
            _secret["v"] = v
    return _secret["v"]


def reset_secret_cache() -> None:
    _secret.clear()


def create_token(subject: str, audience: str, hours: float, **claims) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(subject), "aud": audience, "iat": now, "exp": now + timedelta(hours=hours), **claims}
    return jwt.encode(payload, signing_secret(), algorithm=ALGORITHM)


def decode_token(token: str, audience: str) -> dict | None:
    try:
        return jwt.decode(token, signing_secret(), algorithms=[ALGORITHM], audience=audience)
    except jwt.PyJWTError:
        return None


def password_version(password_hash: str | None) -> str:
    """A fingerprint of the stored password hash (not of the password): it changes with every new password."""
    return hashlib.sha256((password_hash or "").encode("utf-8")).hexdigest()[:16]


def token_is_current(claims: dict, password_hash: str | None) -> bool:
    """False for a token issued before the account's password was last changed or reset."""
    return constant_time_equals(str(claims.get("pv") or ""), password_version(password_hash))


def create_learner_token(user_id: int, email: str, password_hash: str | None) -> str:
    return create_token(
        str(user_id), AUD_LEARNER, get_settings().learner_token_hours, email=email, pv=password_version(password_hash)
    )


def create_member_token(member_id: int, role: str, password_hash: str | None) -> str:
    return create_token(
        f"member:{member_id}",
        AUD_CRM,
        get_settings().crm_token_hours,
        mid=member_id,
        role=role,
        pv=password_version(password_hash),
    )
