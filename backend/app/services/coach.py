"""
The email coach ("Improve email") for the team.

With GEMINI_API_KEY set, Gemini rewrites the draft (told to keep every fact
and invent none). Without it, a rule-based email coach checks the draft for
the problems that hurt deliverability and trust, applies the safe fixes
automatically and lists the rest as suggestions. (The old button just
pasted a canned template above the draft.)
"""

import json
import logging
import re

from app.services import catalog, gemini

log = logging.getLogger(__name__)

UNVERIFIABLE = [
    (
        r"\b\d+\s?%\s?(salary|hike|increase|more|higher)",
        "Salary or pay-rise percentages cannot be backed up: remove them or cite a source.",
    ),
    (r"\b\d+\s?[-–]?\s?\d*\s?LPA\b", "Salary figures (LPA) are a claim you would have to prove: remove them."),
    (r"\bguarantee(d)?\b", "Avoid 'guaranteed': placement or results cannot be guaranteed."),
    (
        r"\bonly \d+ seats?\b|\bseats? (left|remaining)\b",
        "Seat-count urgency should only be used if it's literally true.",
    ),
    (
        r"\bexpires? in \d+ ?(hours?|hrs?|minutes?)\b",
        "Make sure any deadline matches the real coupon expiry (72 hours).",
    ),
    (
        r"\b(board|management) has (authori[sz]ed|approved)\b",
        "Invented authority ('the Board has approved') reads as manipulative.",
    ),
    (r"\b\d+ out of \d+\b", "Statistics like '3 out of 4' need a source: remove the claim or cite it."),
]
SPAMMY = r"\b(act now|100% free|winner|risk[- ]free|click here|urgent|limited time only|!!!+)\b"
CTA = r"\b(reply|enrol|enroll|book|view|join|reserve|start|apply|download|call|visit)\b"


def _first(name):
    return (name or "there").split()[0]


def rule_based(subject, body, name, tier, course_slug=None):
    suggestions, fixed_subject, fixed_body = [], (subject or "").strip(), (body or "").strip()
    first = _first(name)
    low = fixed_body.lower()

    if not re.match(rf"^(hi|hello|dear|hey)\b.*{re.escape(first.lower())}", low[:60]):
        fixed_body = f"Hi {first},\n\n" + re.sub(r"^(hi|hello|dear|hey)[^\n]*\n+", "", fixed_body, flags=re.I)
        suggestions.append("Added a personal greeting with the lead's first name.")
    if len(fixed_subject) > 60:
        suggestions.append(
            f"The subject has {len(fixed_subject)} characters; under 60 avoids it being cut off on phones."
        )
    if len(fixed_subject) < 15:
        suggestions.append("The subject is very short: say what the email is about (the course name helps).")
    if fixed_subject.isupper() or sum(1 for w in fixed_subject.split() if w.isupper() and len(w) > 3) >= 2:
        fixed_subject = fixed_subject.title()
        suggestions.append("Removed ALL-CAPS from the subject (a common spam-filter trigger).")
    if re.search(r"!{2,}", fixed_body + fixed_subject):
        fixed_body = re.sub(r"!{2,}", "!", fixed_body)
        fixed_subject = re.sub(r"!{2,}", "!", fixed_subject)
        suggestions.append("Replaced repeated exclamation marks.")
    if re.search(SPAMMY, low):
        suggestions.append(
            "Phrases that trigger spam filters were found (for example 'act now', 'click here', 'urgent'): "
            "rephrase them."
        )
    for pattern, advice in UNVERIFIABLE:
        if re.search(pattern, fixed_body, flags=re.I) or re.search(pattern, fixed_subject, flags=re.I):
            suggestions.append(advice)
    words = len(fixed_body.split())
    if words > 250:
        suggestions.append(f"The message has {words} words; 120 to 200 words get read on a phone.")
    if not re.search(CTA, low):
        fixed_body += "\n\nReply to this email if you have any questions: a person on our team reads every reply."
        suggestions.append("Added a clear call to action at the end.")
    f = catalog.facts(course_slug) if course_slug else None
    if f and f["duration"] and f["duration"].lower() not in low:
        fixed_body += (
            f"\n\nQuick facts: {f['title']} takes {f['duration']} ({f['level']} level). The fee is "
            f"₹{f['price']:,}, or EMI from ₹{f['emi']:,} a month."
        )
        suggestions.append("Added the course's real duration and fee from the catalogue.")
    if tier == "Low Priority" and re.search(r"\b(coupon|discount|% off)\b", low):
        suggestions.append("This lead is Low Priority: consider useful content instead of a discount.")
    if not suggestions:
        suggestions.append("Looks good: no issues found.")
    return fixed_subject, fixed_body, suggestions


def improve(subject, body, name, tier, course_slug=None, occupation=None):
    if gemini.enabled():
        try:
            f = catalog.facts(course_slug) if course_slug else None
            prompt = f"""Improve this marketing email for clarity, warmth and a clear call to action.
Recipient: {_first(name)}, {occupation or 'a learner'}; lead tier: {tier}.
Allowed course facts: {json.dumps(f, ensure_ascii=False) if f else 'none'}.
Rules: keep the sender's intent and any coupon code exactly; do NOT add statistics, salaries,
guarantees, seat counts or deadlines that aren't in the draft or the facts; under 180 words.
Draft subject: {subject}
Draft body:
{body}
Reply with ONLY JSON: {{"subject":"...","body":"...","notes":["what you changed", "..."]}}"""
            out = json.loads(gemini.generate(prompt, json_mode=True))
            _, _, checks = rule_based(out["subject"], out["body"], name, tier, course_slug)
            notes = list(out.get("notes") or []) + [c for c in checks if not c.startswith("Looks good")]
            return {
                "improved_subject": out["subject"],
                "improved_body": out["body"],
                "suggestions": notes or ["Rewritten by Gemini."],
                "engine": "gemini",
            }
        except Exception as e:  # noqa: BLE001 - any Gemini failure falls back to the rule-based coach
            log.warning("Gemini failed, using the rule-based coach: %s", e)
    s, b, sug = rule_based(subject, body, name, tier, course_slug)
    return {"improved_subject": s, "improved_body": b, "suggestions": sug, "engine": "rules"}
