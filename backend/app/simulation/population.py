"""
The simulated population: who the simulated learners are, and the documented buying formula.

Each simulated lead gets a profile (the website's own vocabulary, including "Unknown" for people who skip their
profile), a hidden intent, behaviour that follows from that intent (people who want a course visit more, stay longer,
watch the video, add it to the cart ...), and an outcome drawn from ``true_logit``: the simulator's ground truth for
how likely a person is to buy, given their intent, profile and behaviour, plus personal luck.

Used to train the starting lead model (60,000 leads, ``app.ml.training.lead``), the uplift model's simulated
randomised campaign (``app.ml.training.uplift``), the six-month starting history (``app.simulation.history``) and the
live simulation (``app.simulation.live``). The realistic error is deliberate: a perfect model on this data reaches an
ROC-AUC of about 0.88, not 0.99, so a model that scores much better is learning the generator, not customers.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.ml import features as F


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


OCC_EFFECT = {
    "Working Professional": 0.55,
    "Businessman": 0.35,
    "Student": -0.15,
    "Unemployed": -0.45,
    "Housewife": -0.55,
    "Other": 0.0,
    "Unknown": -0.2,
}


def true_logit(b, intent, luck):
    """The simulator's ground truth: log-odds that a lead buys, from their hidden intent, profile
    and behaviour. Used by generate() and, step by step, by the history generator
    (app.simulation.history). Keys of b: occ, visits, time_on_site, video, pricing, testimonial,
    brochure, chat, webinar, wishlist, cart, checkout, enquiry, opens, whatsapp, dne, dnc."""
    occ_effect = pd.Series(np.atleast_1d(b["occ"])).map(OCC_EFFECT).fillna(0.0).to_numpy()
    return (
        -2.70
        + 0.95 * np.asarray(intent)  # the part behaviour only hints at
        + occ_effect
        + 0.25 * np.log(np.asarray(b["visits"], dtype=float))
        + 0.18 * np.log1p(np.asarray(b["time_on_site"], dtype=float) / 60)
        + 0.30 * np.asarray(b["video"])
        + 0.35 * np.asarray(b["pricing"])
        + 0.20 * np.asarray(b["testimonial"])
        + 0.45 * np.asarray(b["brochure"])
        + 0.40 * np.asarray(b["chat"])
        + 0.60 * np.asarray(b["webinar"])
        + 0.30 * np.asarray(b["wishlist"])
        + 0.75 * np.asarray(b["cart"])
        + 0.95 * np.asarray(b["checkout"])
        + 0.85 * np.asarray(b["enquiry"])
        + 0.10 * np.minimum(np.asarray(b["opens"]), 4)
        + 0.25 * np.asarray(b["whatsapp"])
        - 0.45 * np.asarray(b["dne"])
        - 0.25 * np.asarray(b["dnc"])
        + np.asarray(luck)
    )


def generate(n: int, seed: int = 42, return_truth: bool = False) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    # profile (form fields)
    occ = rng.choice(
        ["Working Professional", "Student", "Unemployed", "Businessman", "Housewife", "Other"],
        n,
        p=[0.34, 0.24, 0.24, 0.08, 0.05, 0.05],
    )
    spec = rng.choice(F.SPECIALIZATIONS[:-1], n)
    city = rng.choice(F.CITIES[:-2] + ["Other"], n)
    age = rng.choice(F.AGE_BRACKETS[:-1], n, p=[0.20, 0.33, 0.22, 0.17, 0.08])
    heard = rng.choice(F.HOW_HEARD[:-1], n)

    # 15% skip Complete Profile entirely; optional fields skipped individually
    skipped = rng.random(n) < 0.15
    occ = np.where(skipped, "Unknown", occ)
    spec = np.where(skipped, "Unknown", spec)
    city = np.where(skipped | (rng.random(n) < 0.06), "Unknown", city)
    age = np.where(skipped | (rng.random(n) < 0.10), "Unknown", age)
    heard = np.where(skipped | (rng.random(n) < 0.06), "Unknown", heard)

    country = rng.choice(F.COUNTRIES, n, p=[0.82, 0.05, 0.04, 0.03, 0.02, 0.01, 0.02, 0.01])
    course = rng.choice(F.COURSE_TYPES[:-1] + ["Unknown"], n, p=[0.16, 0.15, 0.13, 0.09, 0.09, 0.12, 0.08, 0.08, 0.10])

    source = rng.choice(F.LEAD_SOURCES, n, p=[0.20, 0.20, 0.12, 0.08, 0.07, 0.11, 0.07, 0.05, 0.06, 0.04])
    origin = rng.choice(F.LEAD_ORIGINS, n, p=[0.62, 0.20, 0.08, 0.06, 0.04])
    device = rng.choice(F.DEVICE_TYPES, n, p=[0.55, 0.38, 0.07])

    dne = (rng.random(n) < 0.08).astype(int)  # Do Not Email
    dnc = (rng.random(n) < 0.12).astype(int)  # Do Not Call

    # hidden intent (what the model must infer from behaviour)
    occ_shift = (
        pd.Series(occ)
        .map(
            {
                "Working Professional": 0.45,
                "Businessman": 0.30,
                "Student": 0.05,
                "Unemployed": -0.25,
                "Housewife": -0.35,
                "Other": 0.0,
                "Unknown": -0.15,
            }
        )
        .to_numpy()
    )
    src_shift = (
        pd.Series(source)
        .map(
            {
                "Reference": 0.45,
                "Webinar": 0.45,
                "Google": 0.15,
                "Organic Search": 0.15,
                "LinkedIn": 0.20,
                "Email Campaign": 0.10,
                "Direct Traffic": 0.05,
                "Olark Chat": 0.0,
                "YouTube": -0.10,
                "Social Media": -0.25,
            }
        )
        .to_numpy()
    )
    intent = rng.normal(0, 1, n) + occ_shift + src_shift

    # behaviour, driven by intent (tracked by the website)
    visits = 1 + rng.poisson(np.exp(-0.2 + 0.55 * intent).clip(0.05, 12))
    visits = visits.clip(1, 30)
    per_visit = rng.lognormal(mean=np.log(150) + 0.35 * intent, sigma=0.7)
    time_on_site = (visits * per_visit).clip(0, 6000)
    bounce = rng.random(n) < sigmoid(-3.0 - 0.9 * intent)  # low-intent visitors bounce
    visits = np.where(bounce, 1, visits)
    time_on_site = np.where(bounce, rng.integers(0, 25, n), time_on_site).round()
    pages = (1 + rng.poisson(np.exp(0.5 + 0.3 * intent).clip(0.1, 10))).clip(1, 20)
    pages = np.where(bounce, 1, pages).astype(float)

    def event(a, b):
        return (rng.random(n) < sigmoid(a + b * intent)).astype(int) * (~bounce)

    video = event(-0.7, 0.9)
    pricing = event(-0.6, 0.9)  # dwell >= 4s on the pricing block
    testimonial = event(-1.1, 0.6)
    brochure = event(-1.6, 1.0)
    chat = event(-2.0, 0.7)
    webinar = event(-2.6, 0.9)
    wishlist = event(-2.0, 0.8)
    cart = event(-1.9, 1.1)
    checkout = cart * (rng.random(n) < sigmoid(-0.3 + 0.9 * intent)).astype(int)
    enquiry = event(-2.2, 0.9)
    whatsapp = (rng.random(n) < sigmoid(-0.9 + 0.4 * intent)).astype(int)
    opens = rng.poisson(np.exp(-0.4 + 0.45 * intent).clip(0.05, 6)) * (1 - dne)
    opens = opens.clip(0, 10)

    # outcome
    luck = rng.normal(0, 0.45, n)  # timing, budget, mood of the call
    logit = true_logit(
        dict(
            occ=occ,
            visits=visits,
            time_on_site=time_on_site,
            video=video,
            pricing=pricing,
            testimonial=testimonial,
            brochure=brochure,
            chat=chat,
            webinar=webinar,
            wishlist=wishlist,
            cart=cart,
            checkout=checkout,
            enquiry=enquiry,
            opens=opens,
            whatsapp=whatsapp,
            dne=dne,
            dnc=dnc,
        ),
        intent,
        luck,
    )
    p_true = sigmoid(logit)
    converted = (rng.random(n) < p_true).astype(int)

    df = pd.DataFrame(
        {
            "LeadOrigin": origin,
            "LeadSource": source,
            "DeviceType": device,
            "CurrentOccupation": occ,
            "Specialization": spec,
            "CourseType": course,
            "City": city,
            "Country": country,
            "AgeBracket": age,
            "HowDidYouHear": heard,
            "TotalVisits": visits.astype(int),
            "TotalTimeOnWebsite": time_on_site.astype(int),
            "PageViewsPerVisit": pages,
            "EmailOpenedCount": opens.astype(int),
            "VideoWatched": video,
            "BrochureDownloaded": brochure,
            "ChatInitiated": chat,
            "PricingPageVisited": pricing,
            "TestimonialVisited": testimonial,
            "WebinarAttended": webinar,
            "AddedToWishlist": wishlist,
            "AddedToCart": cart,
            "CheckoutStarted": checkout,
            "EnquirySubmitted": enquiry,
            "WhatsAppOptIn": whatsapp,
            "DoNotEmail": dne,
            "DoNotCall": dnc,
            "Converted": converted,
        }
    )[F.RAW_FEATURES + [F.TARGET]]
    if return_truth:
        # ground truth for simulation studies only (never available in real data):
        # each lead's true no-contact purchase probability, including hidden intent
        df["_p_true"] = p_true
        df["_intent"] = intent  # hidden intent (used by the robustness study)
    return df
