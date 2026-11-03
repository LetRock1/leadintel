"""Request bodies of the learner API (the course website). Lengths are limited so no field can flood the database."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SignupRequest(BaseModel):
    name: str = Field(max_length=80)
    email: str = Field(max_length=120)
    password: str = Field(max_length=128)


class OtpVerifyRequest(BaseModel):
    email: str = Field(max_length=120)
    otp: str = Field(max_length=12)


class LoginRequest(BaseModel):
    email: str = Field(max_length=120)
    password: str = Field(max_length=128)


class EmailOnly(BaseModel):
    email: str = Field(max_length=120)


class ResetPasswordRequest(BaseModel):
    email: str = Field(max_length=120)
    otp: str = Field(max_length=12)
    new_password: str = Field(max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(max_length=128)


class ProfileRequest(BaseModel):
    current_occupation: str = Field(max_length=60)
    specialization: str = Field(max_length=80)
    age_bracket: str | None = Field(default=None, max_length=20)
    city: str | None = Field(default="Unknown", max_length=60)
    country: str | None = Field(default="India", max_length=60)
    phone: str | None = Field(default=None, max_length=20)
    how_did_you_hear: str | None = Field(default="Unknown", max_length=60)


class PreferencesRequest(BaseModel):
    do_not_email: bool | None = None
    do_not_call: bool | None = None
    whatsapp_opt_in: bool | None = None
    phone: str | None = Field(default=None, max_length=20)


class BehaviourEvent(BaseModel):
    session_id: int
    course_slug: str | None = Field(default=None, max_length=80)
    event_type: str = Field(max_length=40)
    time_spent_sec: int | None = 0


class SessionStart(BaseModel):
    device_type: str | None = Field(default=None, max_length=20)
    lead_source: str | None = Field(default=None, max_length=40)


class SessionPing(BaseModel):
    session_id: int


class EmailToken(BaseModel):
    token: str = Field(max_length=64)


class CartItem(BaseModel):
    course_slug: str = Field(max_length=80)


class WishlistItem(BaseModel):
    course_slug: str = Field(max_length=80)


class CouponCheck(BaseModel):
    code: str = Field(max_length=40)


class CheckoutRequest(BaseModel):
    coupon_code: str | None = Field(default="", max_length=40)


class EnquiryRequest(BaseModel):
    course_slug: str = Field(max_length=80)
    course_type: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=20)
    whatsapp_opt_in: int = 0
    lead_source: str | None = Field(default="Direct Traffic", max_length=40)


class ReviewRequest(BaseModel):
    course_slug: str = Field(max_length=80)
    rating: int
    review_text: str | None = Field(default="", max_length=2000)


class QuestionRequest(BaseModel):
    course_slug: str = Field(max_length=80)
    question: str = Field(max_length=1000)


class ChatRequest(BaseModel):
    message: str = Field(max_length=1000)
    conversation_id: str | None = Field(default=None, max_length=64)
    course_slug: str | None = Field(default=None, max_length=80)


class CallbackRequest(BaseModel):
    phone: str = Field(max_length=20)
    preferred_time: str | None = Field(default=None, max_length=60)
    note: str | None = Field(default=None, max_length=300)
    course_slug: str | None = Field(default=None, max_length=80)
