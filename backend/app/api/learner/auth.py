"""Learner accounts: sign-up with an emailed code, sign-in, password reset, and deleting the account."""

from __future__ import annotations

import logging
import re
import sqlite3

from fastapi import APIRouter, HTTPException, status

from app import db
from app.api.deps import Learner
from app.core import rules, security
from app.schemas.learner import (
    ChangePasswordRequest,
    EmailOnly,
    LoginRequest,
    OtpVerifyRequest,
    ResetPasswordRequest,
    SignupRequest,
)
from app.services import learner_auth as otp
from app.services import team as T
from app.services.mailer import mailer_not_configured, send_otp_email
from app.services.scoring import save_lead, score_user

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Learner accounts"])

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
LOCK_NS = "learner:"


def _check_password(pw: str) -> None:
    problem = security.password_problem(pw, require_digit=False)
    if problem:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, problem)


def _start_session(user_id: int) -> int:
    return db.execute("INSERT INTO user_sessions (user_id, device_type) VALUES (?,?)", (user_id, "Desktop"))


def _send_code(email: str, code: str, name: str, purpose: str = "signup") -> dict | None:
    ok, msg = send_otp_email(email, code, name, purpose=purpose)
    if ok and not mailer_not_configured(msg):
        return None
    if ok or rules.DEMO_MODE:
        # a local or live demo must not stop because email is not set up or Gmail is unreachable: the code goes to
        # the backend log (only then; with email working, codes are never logged)
        log.warning("The %s code for %s is %s (%s)", purpose, email, code, msg)
        return {
            "message": "Email is not set up on this computer, so your code is shown in the backend window "
            "(and in backend/data/logs/app.log)."
            if ok
            else "We could not email your code just now. In demo mode it is shown in the backend window."
        }
    raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"Could not send the code: {msg}")


@router.post("/signup", summary="Create an account and email a verification code")
def signup(body: SignupRequest):
    email = (body.email or "").strip().lower()
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Please enter your name.")
    if not EMAIL_RE.match(email):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Please enter a valid email address.")
    _check_password(body.password)
    existing = db.get_user_by_email(email)
    if existing and existing["is_verified"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "This email address is already registered. Please sign in.")
    created = False
    if existing:
        # an unfinished sign-up: refresh the details and send a new code instead of leaving the address stuck
        db.execute(
            "UPDATE users SET name=?, password_hash=? WHERE id=?",
            (name, security.hash_password(body.password), existing["id"]),
        )
        user_id = existing["id"]
    else:
        try:
            user_id = db.execute(
                "INSERT INTO users (name, email, password_hash, is_verified) VALUES (?,?,?,0)",
                (name, email, security.hash_password(body.password)),
            )
            created = True
        except sqlite3.IntegrityError:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "A sign-up is already in progress for this address. Check your inbox for the code.",
            ) from None
    code = otp.generate_otp()
    otp.save_otp(email, code)
    try:
        demo = _send_code(email, code, name)
    except HTTPException:
        if created:
            db.execute("DELETE FROM users WHERE id=?", (user_id,))
        raise
    return demo or {"message": f"We sent a code to {email}. Enter it to finish signing up."}


@router.post("/verify-otp", summary="Verify the sign-up code and sign in")
def verify_otp(body: OtpVerifyRequest):
    email = (body.email or "").strip().lower()
    if not otp.verify_otp(email, body.otp):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That code is wrong or has expired. Please try again.")
    user = db.get_user_by_email(email)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    db.execute("UPDATE users SET is_verified=1 WHERE email=?", (email,))
    db.execute("INSERT OR IGNORE INTO user_profiles (user_id) VALUES (?)", (user["id"],))
    # every verified person becomes a contact in the CRM straight away
    if not db.get_user_lead(user["id"]):
        save_lead(user["id"], score_user(user["id"], source="signup", explain=True), {}, "signup")
    return {
        "token": security.create_learner_token(user["id"], user["email"], user["password_hash"]),
        "session_id": _start_session(user["id"]),
        "user": {"id": user["id"], "name": user["name"], "email": user["email"]},
        "profile_complete": bool((db.get_profile(user["id"]) or {}).get("profile_complete")),
        "message": "Email verified. Welcome to X Education.",
    }


@router.post("/login", summary="Sign in")
def login(body: LoginRequest):
    email = (body.email or "").strip().lower()
    wait = T.locked_seconds(email, ns=LOCK_NS)
    if wait:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many wrong passwords. Try again in {max(1, round(wait / 60))} minute(s) or reset " "your password.",
        )
    user = db.get_user_by_email(email)
    if not user:
        security.waste_time(body.password)
    if not user or not security.verify_password(body.password, user["password_hash"]):
        T.record_failure(email, ns=LOCK_NS)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email address or password.")
    if not user["is_verified"]:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Please verify your email address first. Check your inbox " "for the code."
        )
    T.clear_failures(email, ns=LOCK_NS)
    profile = db.get_profile(user["id"])
    return {
        "token": security.create_learner_token(user["id"], user["email"], user["password_hash"]),
        "session_id": _start_session(user["id"]),
        "user": {"id": user["id"], "name": user["name"], "email": user["email"]},
        "profile_complete": bool(profile and profile.get("profile_complete")),
    }


@router.get("/me", summary="The signed-in learner and their profile")
def me(user: Learner):
    return {"user": db.public_user(user), "profile": db.get_profile(user["id"])}


@router.post("/resend-otp", summary="Send a new sign-up code")
def resend_otp(body: EmailOnly):
    email = (body.email or "").strip().lower()
    user = db.get_user_by_email(email)
    if not user or user["is_verified"]:
        return {"message": "If that account is waiting for verification, a new code has been sent."}
    age = otp.last_otp_age_seconds(email, "signup")
    if age is not None and age < otp.RESEND_SECONDS:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Please wait {int(otp.RESEND_SECONDS - age)} seconds before asking for a new code.",
        )
    code = otp.generate_otp()
    otp.save_otp(email, code, "signup")
    demo = _send_code(email, code, user["name"])
    return demo or {"message": f"A new code has been sent to {email}."}


@router.post("/forgot-password", summary="Email a password reset code")
def forgot_password(body: EmailOnly):
    email = (body.email or "").strip().lower()
    generic = {"message": "If an account exists for that address, a reset code has been sent."}
    user = db.get_user_by_email(email)
    if not user or not user["is_verified"]:
        return generic  # do not reveal which addresses are registered
    age = otp.last_otp_age_seconds(email, "reset")
    if age is not None and age < otp.RESEND_SECONDS:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Please wait {int(otp.RESEND_SECONDS - age)} seconds before asking for a new code.",
        )
    code = otp.generate_otp()
    otp.save_otp(email, code, "reset")
    send_otp_email(email, code, user["name"], purpose="reset")
    return generic


@router.post("/reset-password", summary="Set a new password with the reset code")
def reset_password(body: ResetPasswordRequest):
    email = (body.email or "").strip().lower()
    _check_password(body.new_password)
    if not otp.verify_otp(email, body.otp, "reset"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That code is wrong or has expired.")
    db.execute("UPDATE users SET password_hash=? WHERE email=?", (security.hash_password(body.new_password), email))
    T.clear_failures(email, ns=LOCK_NS)
    return {"message": "Password updated. You can sign in now."}


@router.post("/change-password", summary="Change the password of the signed-in learner")
def change_password(body: ChangePasswordRequest, user: Learner):
    if not security.verify_password(body.current_password, user["password_hash"]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Your current password is not right.")
    _check_password(body.new_password)
    new_hash = security.hash_password(body.new_password)
    db.execute("UPDATE users SET password_hash=? WHERE id=?", (new_hash, user["id"]))
    # every other session is signed out; this one goes on with a new token
    return {"message": "Password changed.", "token": security.create_learner_token(user["id"], user["email"], new_hash)}
