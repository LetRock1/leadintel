"""
Personalised email, WhatsApp and call-script text for a lead.

The text depends on:
  * the lead's tier (how ready they are) and why the CRM is writing now (cart, checkout, wishlist, enquiry, a visit
    that ended, a campaign)
  * true facts about the course from the catalogue (duration, level, modules, instructor, EMI): no invented salary
    figures, placement rates, scholarships or deadlines. Every claim in these messages can be checked on the course
    page.
  * the offer chosen for this lead (a discount or none). Next-best-action decides the offer; without a decision a
    tier default is used.

With GEMINI_API_KEY set in backend/.env, Gemini writes the copy from the same facts (and is told not to invent any);
on any error the templates below are used.

Who speaks: emails the CRM sends by itself are signed by the admissions team (no invented person). Call scripts and
WhatsApp messages are said by whoever on the team does the task: they contain the placeholder {my_name}, which the
dashboard fills with the name of the person signed in (Today's actions, the lead page, the WhatsApp link).
"""

from __future__ import annotations

import json as _json
import logging
import secrets

from app.services import catalog, gemini

log = logging.getLogger(__name__)

COUPON_VALID_HOURS = 72

TRIGGER_CONTEXT = {
    "cart_abandon": "they added a course to their cart but did not complete checkout",
    "checkout_abandon": "they reached checkout and stopped one step short of paying",
    "wishlist": "they added a course to their wishlist",
    "session_end": "they browsed the website and then left",
    "enquiry": "they sent an enquiry form asking for more information",
    "email_click": "they clicked through a previous marketing email",
    "campaign": "they are part of a scheduled campaign",
    "manual_edit": "a member of the admissions team is drafting this email by hand",
    "chat_callback": "they asked for a call-back in the website's help assistant",
    "manual": "someone in the admissions team chose to follow up with them personally",
}

# Default offer per tier, used only when no next-best-action decision is passed in.
DEFAULT_OFFER_PCT = {
    "Target Immediately": 0,  # very likely to buy anyway: a discount mostly gives money away
    "Nurture via Email/WhatsApp": 15,
    "Marketing Campaign": 10,
    "Low Priority": 0,
}

# how an occupation reads in a sentence ("as a working professional")
OCCUPATION_PHRASE = {
    "Working Professional": "a working professional",
    "Student": "a student",
    "Businessman": "a business owner",
    "Unemployed": "someone looking for their next role",
    "Housewife": "someone returning to learning",
    "Other": "a learner",
}

MY_NAME = "{my_name}"  # filled in by the dashboard with the team member's own name
TEAM_SIGNATURE = "The X Education admissions team"


CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I, so a code can be read out on the phone


def coupon_code_for(pct, returning=False):
    """A personal code: a readable name for the discount level and five random characters (SMARTSTART20-K7Q2M), so
    every copy is unique to the one learner it is issued to in coupons_issued."""
    if not pct:
        return ""
    if returning:
        name = f"LOYAL{int(pct)}"
    else:
        name = {10: "EARLYBIRD10", 15: "FUTUREREADY15", 20: "SMARTSTART20", 25: "VIP25", 30: "LASTCHANCE30"}.get(
            int(pct), f"XEDU{int(pct)}"
        )
    return f"{name}-{personal_suffix()}"


def personal_suffix() -> str:
    """Five random characters that make a coupon code personal (about 33 million combinations)."""
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(5))


def _facts(course, course_slug):
    slug = course_slug or catalog.slug_for_title(course)
    f = catalog.facts(slug) if slug else None
    if f:
        return f
    return {
        "title": course or "our programme",
        "duration": None,
        "level": None,
        "price": None,
        "emi": None,
        "modules": None,
        "outcomes": [],
        "instructor": None,
        "instructor_role": None,
    }


def _course_block(f):
    lines = []
    if f["duration"]:
        lines.append(f"- Duration: {f['duration']}, level: {f['level']}")
    if f["modules"]:
        lines.append(f"- Modules include: {f['modules']}")
    if f["outcomes"]:
        lines.append(f"- What you will be able to do: {', '.join(f['outcomes'][:3])}")
    if f["instructor"]:
        lines.append(f"- Taught by {f['instructor']} ({f['instructor_role']})")
    if f["price"]:
        emi = f", or EMI from ₹{f['emi']:,} a month" if f["emi"] else ""
        lines.append(f"- Fee: ₹{f['price']:,}{emi}")
    return "\n".join(lines)


def _offer_line(code, pct):
    if not code:
        return ""
    return (
        f"\n\nUse the code {code} at checkout for {pct}% off. It is linked to your account and valid for "
        f"{COUPON_VALID_HOURS} hours."
    )


def _trigger_line(trigger, title):
    return {
        "cart_abandon": f"You left {title} in your cart. It is still there whenever you are ready.",
        "checkout_abandon": (
            f"You were one step away from enrolling in {title}. If something went wrong at checkout, "
            f"reply to this email and we will help."
        ),
        "wishlist": f"You saved {title} to your wishlist, so here is a short summary to help you decide.",
        "enquiry": f"Thank you for your enquiry about {title}. Here are the key details.",
        "session_end": f"Thank you for looking at {title} on our website.",
        "chat_callback": f"Thank you for asking for a call about {title}. "
        "One of our counsellors will call you shortly.",
        "manual": f"I am following up personally about {title}, which you looked at on our website.",
    }.get(trigger, f"Here is a short overview of {title}.")


def _templates(first, occupation, specialization, f, action, trigger, code, pct, past_purchases):
    title = f["title"]
    block = _course_block(f)
    offer = _offer_line(code, pct)
    opener = _trigger_line(trigger, title)
    who = OCCUPATION_PHRASE.get(occupation, "a learner")
    field = f" with a background in {specialization}" if specialization else ""

    if past_purchases > 0:
        subject = f"{first}, a next step after your first course: {title}"
        body = (
            f"Hi {first},\n\nIt is good to have you learning with X Education. {opener}\n\n{block}"
            f"{offer}\n\nReply to this email if you would like help planning your next course.\n\n{TEAM_SIGNATURE}"
        )
        wa = (
            f"Hi {first}, thinking about {title} next? It is a {f['duration'] or 'short'} programme. "
            f"Reply YES for the details."
        )
        return subject, body, wa, ""

    if action == "Target Immediately":
        subject = f"{first}, your questions about {title}"
        body = (
            f"Hi {first},\n\n{opener}\n\nFor {who}{field}, this is what {title} covers:\n\n{block}{offer}\n\n"
            f"Would a 10-minute call help? Reply with a good time and one of our counsellors will call you.\n\n"
            f"{TEAM_SIGNATURE}"
        )
        wa = (
            f"Hi {first}, this is {MY_NAME} from X Education. {opener} I am happy to answer any questions about "
            f"{title}: reply here or tell me a good time to call."
        )
        script = (
            f"Hi {first}, this is {MY_NAME} from X Education. {opener} I would like to understand what you are "
            f"hoping to get from {title} and answer any questions about the curriculum, schedule or fees"
            + (f"; the programme runs for {f['duration']}" if f["duration"] else "")
            + ". "
            "What would make this the right time for you?"
        )
        return subject, body, wa, script

    if action == "Nurture via Email/WhatsApp":
        subject = f"{first}, is {title} right for you? A short guide"
        body = (
            f"Hi {first},\n\n{opener}\n\n{block}\n\nIt suits {who}{field} who wants hands-on, project-based "
            f"learning.{offer}\n\nQuestions? Reply to this email: a person on our team reads every one.\n\n"
            f"{TEAM_SIGNATURE}"
        )
        wa = (
            f"Hi {first}, {opener} {title} runs for {f['duration'] or 'a few months'}"
            + (f", and the code {code} gives {pct}% off for {COUPON_VALID_HOURS} hours" if code else "")
            + ". Reply for the syllabus."
        )
        return subject, body, wa, ""

    if action == "Marketing Campaign":
        subject = f"Free live session: getting started with {title}"
        body = (
            f"Hi {first},\n\n{opener}\n\nWe run a free live session every Saturday at 11 AM IST where instructors "
            f"walk through the {title} curriculum and answer questions, with no obligation.\n\n{block}{offer}\n\n"
            f"You can reserve a seat on the home page of our website.\n\n{TEAM_SIGNATURE}"
        )
        wa = (
            f"Hi {first}, there is a free live introduction to {title} this Saturday at 11 AM IST. "
            "Reply WEBINAR to join."
        )
        return subject, body, wa, ""

    subject = f"{title}: what you would learn, in two minutes"
    body = (
        f"Hi {first},\n\n{opener}\n\nHere is a short summary you can come back to later:\n\n{block}{offer}\n\n"
        f"When you are ready, the full curriculum is on the course page.\n\n{TEAM_SIGNATURE}"
    )
    wa = f"Hi {first}, here is a two-minute summary of {title} whenever you are ready. Reply INFO to get it."
    return subject, body, wa, ""


def speaker(text, name):
    """A call script or WhatsApp message as said by this person on the team ({my_name})."""
    if not text:
        return text
    return text.replace(MY_NAME, name or "the X Education team")


def generate_content(
    name: str,
    occupation: str | None,
    specialization: str | None,
    course: str,
    action: str,
    trigger: str = "session_end",
    past_purchases: int = 0,
    lead_score: float = 0,
    course_slug: str | None = None,
    offer_pct: int | None = None,
) -> dict:
    """{email_subject, email_body, whatsapp_message, coupon_code, offer_pct, call_script}.
    offer_pct: the discount next-best-action decided (None = tier default, 0 = no offer)."""
    first = (name or "there").split()[0]
    f = _facts(course, course_slug)
    pct = DEFAULT_OFFER_PCT.get(action, 0) if offer_pct is None else int(offer_pct)
    if past_purchases > 0 and offer_pct is None:
        pct = 20
    code = coupon_code_for(pct, returning=past_purchases > 0)

    if gemini.enabled():
        try:
            return generate_content_ai(
                first, occupation, specialization, f, action, trigger, lead_score, past_purchases, code, pct
            )
        except Exception as e:  # noqa: BLE001 - the templates always work
            log.warning("Gemini could not write the message (%s); using the template", e)

    subject, body, wa, script = _templates(
        first, occupation, specialization, f, action, trigger, code, pct, past_purchases
    )
    return {
        "email_subject": subject,
        "email_body": body,
        "whatsapp_message": wa,
        "coupon_code": code,
        "offer_pct": pct,
        "call_script": script,
    }


def generate_content_ai(
    first, occupation, specialization, f, action, trigger, lead_score, past_purchases, code, pct
) -> dict:
    """Gemini writes the copy from the catalogue facts only. Raises on any failure."""
    facts = _course_block(f) or f["title"]
    offer = (
        f"Include the coupon code {code} ({pct}% off, valid {COUPON_VALID_HOURS} hours) once."
        if code
        else "Do not offer any discount."
    )
    who = OCCUPATION_PHRASE.get(occupation or "", "a learner")
    prompt = f"""You write short, honest follow-up messages for X Education, an Indian online-education company.

Lead: {first}, {who}{f" in {specialization}" if specialization else ""}. Tier: {action}. Lead score: {lead_score}/100.
Why we are writing now: {TRIGGER_CONTEXT.get(trigger, 'they showed interest on the website')}.
{"Returning customer with " + str(past_purchases) + " past purchase(s)." if past_purchases else ""}
Course facts (the ONLY facts you may state):
{facts}

Rules:
- Do NOT invent statistics, salaries, placement guarantees, scholarships, seat limits or deadlines.
- Do NOT invent names of people. Sign the email "{TEAM_SIGNATURE}". In the WhatsApp message and the call script
  the counsellor introduces themselves as {MY_NAME} (write exactly {MY_NAME}; it is replaced by their name).
- {offer}
- Warm, specific, plain text, no emoji, under 160 words. Mention the course by name and why we are writing now.

Reply with ONLY JSON: {{"email_subject":"...","email_body":"...","whatsapp_message":"...","call_script":"..."}}"""
    content = _json.loads(gemini.generate(prompt, json_mode=True))
    for key in ("email_subject", "email_body", "whatsapp_message"):
        if not content.get(key):
            raise ValueError(f"Gemini response missing {key}")
    content.setdefault("call_script", "")
    content["coupon_code"] = code
    content["offer_pct"] = pct
    return content
