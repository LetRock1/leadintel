"""
The documented behaviour of the simulated learners, shared by the six-month starting history
(``app.simulation.history``) and the live simulation (``app.simulation.live``), so the live learners behave exactly
like the people of the history:

    who they are     names, a reserved email domain that is never emailed, profile and hidden traits
    on the website   the chance of each first-time step per visit (EVENTS)
    buying           the population's buying formula, shifted to this business (BASE_SHIFT, WORLD_DRIFT)
    the history      six campaigns and six A/B tests with known true effects
"""

from __future__ import annotations

import os

import numpy as np

from app.core import rules
from app.ml import features as F
from app.ml import nba_core as N
from app.simulation import effects, population

DEMO_DOMAIN = rules.SIMULATED_DOMAIN
TS = "%Y-%m-%d %H:%M:%S"
FIRST = [
    "Aarav",
    "Vivaan",
    "Aditya",
    "Arjun",
    "Rohan",
    "Karan",
    "Ishaan",
    "Kabir",
    "Rahul",
    "Siddharth",
    "Ananya",
    "Diya",
    "Isha",
    "Kavya",
    "Meera",
    "Nisha",
    "Pooja",
    "Riya",
    "Sneha",
    "Tanvi",
    "Aditi",
    "Harsh",
    "Nikhil",
    "Pranav",
    "Varun",
    "Neha",
    "Shreya",
    "Divya",
    "Simran",
    "Zoya",
    "Amit",
    "Deepak",
    "Gaurav",
    "Manish",
    "Rajat",
    "Sahil",
    "Tarun",
    "Vikram",
    "Yash",
    "Abhishek",
    "Bhavna",
    "Charu",
    "Gauri",
    "Jaya",
    "Komal",
    "Lavanya",
    "Mansi",
    "Payal",
    "Ritika",
    "Swati",
    "Akash",
    "Dev",
    "Kunal",
    "Mohit",
    "Naveen",
    "Om",
    "Parth",
    "Sameer",
    "Uday",
    "Vivek",
]
LAST = [
    "Sharma",
    "Verma",
    "Patel",
    "Iyer",
    "Nair",
    "Reddy",
    "Gupta",
    "Mehta",
    "Joshi",
    "Kulkarni",
    "Desai",
    "Rao",
    "Singh",
    "Chopra",
    "Bose",
    "Menon",
    "Pillai",
    "Shah",
    "Kapoor",
    "Agarwal",
    "Banerjee",
    "Chatterjee",
    "Das",
    "Dutta",
    "Ghosh",
    "Jain",
    "Khanna",
    "Malhotra",
    "Mishra",
    "Pandey",
    "Saxena",
    "Sinha",
    "Srivastava",
    "Tiwari",
    "Trivedi",
    "Bhatt",
    "Chauhan",
    "Dubey",
    "Hegde",
    "Kamath",
    "Naidu",
    "Prasad",
    "Shetty",
    "Thakur",
    "Yadav",
]  # 60 x 45 = 2,700 different names


# documented behaviour of the simulated learners (per visit, log-odds)
EVENTS = [  # flag, event_type, base, intent slope
    ("video", "video_play", -1.4, 0.9),
    ("pricing", "pricing_view", -1.3, 0.9),
    ("testimonial", "testimonial_view", -2.0, 0.6),
    ("brochure", "brochure_dl", -2.3, 1.0),
    ("chat", "chat", -3.1, 0.7),
    ("webinar", "webinar_register", -3.6, 0.9),
    ("wishlist", "wishlist_add", -2.8, 0.8),
    ("cart", "cart_add", -3.0, 1.1),
    ("enquiry", "enquiry_submit", -3.4, 0.9),
]
# calibrated so about 39% of learners buy within the six months (the real X Education data: 38.5%)
BASE_SHIFT = float(os.getenv("HISTORY_BASE_SHIFT", "-2.0"))
# How THIS simulated business differs from the data the base lead model was trained on (log-odds of
# buying). A real business never matches its training data exactly; these three documented
# differences give the learning loop something real to discover (ml/experiments/history_check.py
# compares what it learned with these values). HISTORY_DRIFT=0 switches them off (for comparison runs).
WORLD_DRIFT = {"WhatsAppOptIn": 0.6, "MobileDevice": -0.5, "WebinarAttended": 0.7}
if os.getenv("HISTORY_DRIFT", "1") == "0":
    WORLD_DRIFT = {k: 0.0 for k in WORLD_DRIFT}
LEARN_DAYS = (30, 60, 90, 120, 150)
CAMPAIGNS = [  # day, name, audience, subject, body
    (
        20,
        "October cohort announcement",
        "All leads",
        "New {course} batch starts soon, {first_name}",
        "Hi {first_name},\n\nA new batch of {course} starts soon. Have a look at the curriculum and the "
        "instructor, and reserve a seat if it fits your plans.",
    ),
    (
        50,
        "EMI options explained",
        "Nurture via Email/WhatsApp",
        "Pay for {course} from ₹2,200 a month",
        "Hi {first_name},\n\nMany learners spread the fee for {course} over monthly EMIs. Here is how it works.",
    ),
    (
        80,
        "Free career webinar",
        "Marketing Campaign",
        "Free live session this Saturday, {first_name}",
        "Hi {first_name},\n\nJoin our free live session with instructors this Saturday and ask anything "
        "about {course}.",
    ),
    (
        110,
        "Learner stories",
        "All leads",
        "How learners like you finished {course}",
        "Hi {first_name},\n\nThree short stories from learners who balanced {course} with work or studies.",
    ),
    (
        140,
        "Curriculum update",
        "Target Immediately",
        "What's new in {course} this term",
        "Hi {first_name},\n\nWe refreshed two modules of {course}. Here is what changed.",
    ),
    (
        170,
        "Last seats reminder",
        "All leads",
        "A few seats left in {course}",
        "Hi {first_name},\n\nA few seats are left in the next {course} batch.",
    ),
]
# Six A/B tests with known true effects (log-odds; "click" moves clicks, "buy" moves buying once the learner is back
# on the site; 'coupon10' / 'coupon20' use the simulator's coupon effects, bigger for price-sensitive learners;
# callables depend on the learner). They are designed so the history shows every kind of verdict:
#   day  40  too small to tell (the plan warns about it)      day 100  a click winner (urgency subject)
#   day  70  a true null (neither email does anything)        day 130  a winner only on mobile phones
#   day 160  a clear purchase winner (personalised course)    day 175  still running at the end
AB_TESTS = [
    {
        "day": 40,
        "name": "10% vs 20% coupon",
        "audience": "All leads",
        "metric": "purchase",
        "hypothesis": "A 20% coupon converts more learners than 10%, but may not pay for the extra discount.",
        "variants": [
            {
                "key": "A",
                "label": "10% coupon",
                "offer_pct": 10,
                "click": 0.2,
                "buy": "coupon10",
                "subject": "10% off {course} for the next 72 hours",
                "body": "Hi {first_name},\n\nHere is 10% off {course}, valid for 72 hours.",
            },
            {
                "key": "B",
                "label": "20% coupon",
                "offer_pct": 20,
                "click": 0.35,
                "buy": "coupon20",
                "subject": "20% off {course} for the next 72 hours",
                "body": "Hi {first_name},\n\nHere is 20% off {course}, valid for 72 hours.",
            },
        ],
    },
    {
        "day": 70,
        "name": "Webinar invite vs brochure",
        "audience": "Low Priority",
        "metric": "purchase",
        "hypothesis": "Cold leads respond better to a live webinar than to a brochure.",
        "variants": [
            {
                "key": "A",
                "label": "Free webinar invite",
                "offer_pct": 0,
                "click": 0.0,
                "buy": 0.0,
                "subject": "Free live session on {course}",
                "body": "Hi {first_name},\n\nJoin a free live session on {course} this Saturday.",
            },
            {
                "key": "B",
                "label": "Course brochure",
                "offer_pct": 0,
                "click": 0.0,
                "buy": 0.0,
                "subject": "The {course} brochure",
                "body": "Hi {first_name},\n\nCurriculum, fees and instructor of {course} on one page.",
            },
        ],
    },
    {
        "day": 100,
        "name": "Subject line: benefit vs urgency",
        "audience": "All leads",
        "metric": "click",
        "hypothesis": "An urgency subject line gets more people to click than a benefit-led one.",
        "variants": [
            {
                "key": "A",
                "label": "Benefit-led subject",
                "offer_pct": 0,
                "click": 0.0,
                "buy": 0.10,
                "subject": "{first_name}, your next career step: {course}",
                "body": "Hi {first_name},\n\nSee how {course} fits your goals: curriculum, instructor and outcomes.",
            },
            {
                "key": "B",
                "label": "Urgency subject",
                "offer_pct": 0,
                "click": 0.80,
                "buy": 0.10,
                "subject": "Last seats in the {course} batch",
                "body": "Hi {first_name},\n\nThe next {course} batch is filling up. Reserve your seat this week.",
            },
        ],
    },
    {
        "day": 130,
        "name": "Short mobile email vs long email",
        "audience": "All leads",
        "metric": "purchase",
        "hypothesis": "A short email works better on phones; a long one on desktop.",
        "variants": [
            {
                "key": "A",
                "label": "Long email",
                "offer_pct": 0,
                "click": 0.0,
                "buy": lambda L: 0.40 if L["device"] != "Mobile" else 0.0,
                "subject": "Everything about {course} in one email",
                "body": "Hi {first_name},\n\nModules, projects, instructor, fees, EMI and outcomes of "
                "{course} in detail.",
            },
            {
                "key": "B",
                "label": "Short mobile-first email",
                "offer_pct": 0,
                "click": lambda L: 0.9 if L["device"] == "Mobile" else 0.0,
                "buy": lambda L: 1.4 if L["device"] == "Mobile" else 0.0,
                "subject": "{course} in 30 seconds",
                "body": "Hi {first_name},\n\n{course}: 3 reasons, 1 link.",
            },
        ],
    },
    {
        "day": 160,
        "name": "Personalised course pick vs generic newsletter",
        "audience": "All leads",
        "metric": "purchase",
        "hypothesis": "A course picked for the learner's background converts better than a generic newsletter.",
        "variants": [
            {
                "key": "A",
                "label": "Generic newsletter",
                "offer_pct": 0,
                "click": 0.0,
                "buy": 0.0,
                "subject": "This month at X Education",
                "body": "Hi {first_name},\n\nNews, new batches and learner stories from X Education.",
            },
            {
                "key": "B",
                "label": "Personalised course pick",
                "offer_pct": 0,
                "click": 1.0,
                "buy": 1.2,
                "subject": "{first_name}, {course} fits your background",
                "body": "Hi {first_name},\n\nBased on what you looked at, {course} is the best next step for you.",
            },
        ],
    },
    {
        "day": 175,
        "name": "EMI message vs refund guarantee",
        "audience": "All leads",
        "metric": "purchase",
        "hypothesis": "A refund guarantee removes more doubt than an EMI message.",
        "variants": [
            {
                "key": "A",
                "label": "EMI from \u20b92,200 a month",
                "offer_pct": 0,
                "click": 0.1,
                "buy": 0.20,
                "subject": "{course} from \u20b92,200 a month",
                "body": "Hi {first_name},\n\nSpread the fee of {course} over easy monthly EMIs.",
            },
            {
                "key": "B",
                "label": "7-day refund guarantee",
                "offer_pct": 0,
                "click": 0.15,
                "buy": 0.25,
                "subject": "Try {course} risk-free for 7 days",
                "body": "Hi {first_name},\n\nStart {course}; if it isn't for you, get a full refund within 7 days.",
            },
        ],
    },
]


def history_test(name):
    """The documented A/B test of the history with this name (its true effects), or None."""
    return next((t for t in AB_TESTS if t["name"] == (name or "").strip()), None)


def course_slugs():
    """The website's courses grouped by the course type the generator draws (same order every time)."""
    from app.services import catalog

    by_type = {}
    for slug, ctype in F.COURSE_TYPE_BY_SLUG.items():
        if catalog.get_course(slug):
            by_type.setdefault(ctype, []).append(slug)
    return by_type, [s for v in by_type.values() for s in v]


def learner_traits(n, days, seed, rng, slugs_by_type, all_slugs):
    """Who the simulated learners are: profile, hidden intent and luck, how each one responds to each CRM
    step (noise), course of interest, phone, sign-up day. The history generator and the live simulation both use
    this, so the live learners are exactly the people of the history.
    rng must be a fresh np.random.default_rng(seed): the draws happen in a fixed order."""
    raw = population.generate(n, seed=seed, return_truth=True)
    day_ix = np.arange(days)
    p = 1 + 0.6 * day_ix / days  # the site grows: more sign-ups recently
    signup_days = np.sort(rng.choice(day_ix, size=n, p=p / p.sum()))
    pairs = [(first, last) for first in FIRST for last in LAST]  # every learner gets a different name
    order = rng.permutation(len(pairs))
    out = []
    for i, r in enumerate(raw.to_dict("records")):
        first, last = pairs[int(order[i % len(pairs)])]
        hour = float(rng.uniform(8, 22))
        slug = str(rng.choice(slugs_by_type.get(r["CourseType"]) or all_slugs))
        luck = float(rng.normal(0, 0.45))
        noise = {a: float(rng.normal(0, effects.EFFECT_NOISE_SD)) for a in N.ACTION_LIST}
        phone = f"+91 00000 {i + 1:05d}" if rng.random() < 0.85 else None
        out.append(
            {
                "i": i,
                "name": f"{first} {last}",
                "email": f"{first}.{last}.{i + 1}@{DEMO_DOMAIN}".lower(),
                "occ": r["CurrentOccupation"],
                "spec": r["Specialization"],
                "intent": float(r["_intent"]),
                "luck": luck,
                "dne": int(r["DoNotEmail"]),
                "dnc": int(r["DoNotCall"]),
                "wa": int(r["WhatsAppOptIn"]),
                "device": r["DeviceType"],
                "source": r["LeadSource"],
                "slug": slug,
                "signup_day": int(signup_days[i]),
                "signup_hour": hour,
                "noise": noise,
                "phone": phone,
                "raw": r,
            }
        )
    return out
