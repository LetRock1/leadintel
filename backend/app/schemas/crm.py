"""Request bodies of the CRM API (``/api/v1/crm``). Responses are plain JSON documents described in docs/api.md."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str = Field(max_length=200)
    password: str = Field(max_length=200)


class OwnPasswordRequest(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(max_length=200)


class ActRequest(BaseModel):
    action: str = Field(max_length=40)


class SendEmailRequest(BaseModel):
    lead_id: int
    subject: str = Field(max_length=300)
    body: str = Field(max_length=20000)


class WhatsAppRequest(BaseModel):
    lead_id: int
    message: str = Field(max_length=4000)


class ImproveRequest(BaseModel):
    draft: str = Field(max_length=20000)
    subject: str | None = Field(default="", max_length=300)
    tier: str = Field(max_length=80)
    course: str | None = Field(default="", max_length=200)
    course_slug: str | None = Field(default=None, max_length=80)
    occupation: str | None = Field(default="", max_length=80)
    name: str | None = Field(default="", max_length=120)


class TaskDone(BaseModel):
    outcome: str = Field(default="reached", max_length=40)  # reached | no_answer | not_interested | sent | skipped
    note: str | None = Field(default=None, max_length=4000)


class CallRequest(BaseModel):
    note: str | None = Field(default=None, max_length=4000)


class CallbackDone(BaseModel):
    note: str | None = Field(default=None, max_length=4000)


class CouponRequest(BaseModel):
    user_id: int
    tier: str = Field(max_length=80)
    discount_pct: int
    expires_hours: int = 72
    # the coupon guard: a coupon that would mostly give money away is refused unless someone confirms it
    override: bool = False


class PlannerSettings(BaseModel):
    # rupees per month; null switches the discount budget off (a coupon goes out whenever it pays for itself)
    monthly_discount_budget: float | None = Field(default=None, ge=0, le=100_000_000)
    counsellor_monthly_cost: float | None = Field(default=None, ge=0, le=10_000_000)


class CampaignRequest(BaseModel):
    name: str = Field(max_length=200)
    tier: str = Field(max_length=80)
    subject: str = Field(max_length=300)
    body: str = Field(max_length=20000)
    scheduled_at: str = Field(max_length=40)
    holdout_share: float | None = None


class Variant(BaseModel):
    label: str | None = Field(default=None, max_length=120)
    subject: str = Field(max_length=300)
    body: str = Field(max_length=20000)
    offer_pct: int | None = 0


class AbTestRequest(BaseModel):
    name: str = Field(max_length=200)
    tier: str = Field(max_length=80)
    hypothesis: str | None = Field(default="", max_length=2000)
    metric: str | None = "purchase"  # purchase | click
    control_share: float | None = None
    mde: float | None = None
    variants: list[Variant]


class ApplyRequest(BaseModel):
    variant: str = Field(max_length=4)
    tier: str | None = Field(default=None, max_length=80)


class StageRequest(BaseModel):
    stage: str = Field(max_length=20)
    note: str | None = Field(default=None, max_length=200)
    reason: str | None = Field(default=None, max_length=120)  # required for 'Lost'


class StatusRequest(BaseModel):
    status: str = Field(max_length=10)  # lost | open
    reason: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=200)


class ConsentRequest(BaseModel):
    channel: str = Field(max_length=20)  # email | call | whatsapp


class OwnerRequest(BaseModel):
    member_id: int | None = None  # None = unassigned


class NoteRequest(BaseModel):
    text: str = Field(max_length=4000)
    kind: str | None = "note"


class AnswerRequest(BaseModel):
    qna_id: int
    answer: str = Field(max_length=4000)


class AskRequest(BaseModel):
    question: str = Field(max_length=500)


class MemberRequest(BaseModel):
    name: str = Field(max_length=80)
    email: str = Field(max_length=120)
    role: str = "counsellor"
    password: str = Field(max_length=200)


class MemberUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    role: str | None = None
    active: bool | None = None
    takes_new_leads: bool | None = None


class PasswordRequest(BaseModel):
    password: str = Field(max_length=200)


class TeamSettingsRequest(BaseModel):
    auto_assign: bool | None = None
    assignment_rule: str | None = None
    task_sla_hours: float | None = None
    callback_sla_hours: float | None = None
    task_expiry_days: float | None = None  # 0 = open tasks never expire


class SimVisitRequest(BaseModel):
    kind: str = "returning"  # returning | signup


class SimSwitchRequest(BaseModel):
    enabled: bool
