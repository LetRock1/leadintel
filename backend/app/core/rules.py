"""
Business rules of the CRM, read from ``crm_settings.json`` at the repository root: tiers, the steps the
CRM can take and what they cost, timings, the learning loop, A/B testing defaults, the team.

The backend and the ML scripts read the same file, so a rule is changed in exactly one place. Missing
keys fall back to the defaults below, so an older or partial file still works.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging

from app.core.config import get_settings

log = logging.getLogger(__name__)

PATH = str(get_settings().rules_path)

DEFAULTS = {
    "business": {"name": "X Education", "crm_name": "X Education CRM", "currency": "INR", "currency_symbol": "₹"},
    "tiers": [
        {"min_score": 80, "name": "Target Immediately"},
        {"min_score": 60, "name": "Nurture via Email/WhatsApp"},
        {"min_score": 40, "name": "Marketing Campaign"},
        {"min_score": 0, "name": "Low Priority"},
    ],
    "actions": {
        "none": {"label": "Do nothing for now", "channel": None, "discount": 0.00, "cost": 0},
        "email_info": {"label": "Send an information email", "channel": "email", "discount": 0.00, "cost": 2},
        "email_coupon_10": {"label": "Send email with 10% coupon", "channel": "email", "discount": 0.10, "cost": 2},
        "email_coupon_20": {"label": "Send email with 20% coupon", "channel": "email", "discount": 0.20, "cost": 2},
        "call": {"label": "Counsellor phone call", "channel": "call", "discount": 0.00, "cost": 150},
        "whatsapp": {"label": "WhatsApp message", "channel": "whatsapp", "discount": 0.00, "cost": 5},
    },
    "daily_call_capacity": 20,
    # capacity-aware next-best-action (app/ml/capacity.py): "fcfs" = first come, first served; "priced" = a call
    # is chosen only when it adds more than the price of a call slot, learned from the CRM's own recent decisions.
    "call_capacity": {"policy": "priced", "lookback_days": 7, "min_decisions": 50},
    # the monthly discount budget (app/ml/budget.py): set by the owner on the Planner page (off by default); while
    # it is set, a rupee of expected discount has a price learned from the CRM's own recent decisions
    "discount_budget": {"lookback_days": 7, "min_decisions": 30},
    # the owner's planner (app/services/planner.py): one more counsellor adds this many call slots a day
    "planner": {"counsellor_daily_calls": 8, "counsellor_monthly_cost": 35000},
    "exploration_rate": 0.15,
    "outcome_window_days": 14,
    "coupon_valid_hours": 72,
    # at most one coupon per person in this many days, used or not (and never two open at once)
    "coupon_gap_days": 7,
    "automation_minutes": {
        "demo": {"job_every": 1, "visit_ended": 1, "cart_abandoned": 1, "checkout_abandoned": 1, "wishlist": 1},
        "live": {"job_every": 5, "visit_ended": 15, "cart_abandoned": 60, "checkout_abandoned": 30, "wishlist": 30},
    },
    "cooldown_hours": {"visit": 6, "cart": 12, "checkout": 12, "wishlist": 24, "manual_repeat": 24},
    "score_refresh_minutes": {"demo": 5, "live": 60},
    "learning": {
        "check_every_minutes": {"demo": 5, "live": 60},
        "min_new_outcomes": 30,
        "swap_confidence": 0.90,
        "ridge": 2.0,
        "bootstrap_resamples": 300,
        "lead_age": True,
    },
    "ab_testing": {
        "control_share": 0.20,
        "alpha": 0.05,
        "power": 0.80,
        "min_detectable_effect": 0.05,
        "outcome_window_days": 14,
        "max_variants": 3,
        "min_per_segment_arm": 30,
        "auto_adopt": True,
        "adoption_check_share": 0.10,
    },
    "campaigns": {"holdout_share": 0.10},
    "global_control": {"share": 0.05},
    "starting_history": {"create_on_first_start": True, "learners": 2000, "days": 180},
    "live_simulation": {"enabled": True, "new_signups_per_day": 13, "tick_seconds": 10},
    "team": {
        "auto_assign": True,
        "assignment_rule": "round_robin",
        "task_sla_hours": 24,
        "callback_sla_hours": 4,
        "task_expiry_days": 7,
        "lost_reasons": [
            "Not interested any more",
            "Too expensive",
            "Chose another institute",
            "Not eligible",
            "Wrong or invalid contact details",
            "Asked not to be contacted",
            "Duplicate lead",
            "Other",
        ],
        "login_lockout": {"max_failures": 5, "minutes": 15},
    },
}

# Simulated learners (the starting history and the live simulation) have addresses on this reserved
# domain: they are never emailed, and the dashboard tags them "simulated". Everything else treats them
# exactly like people who signed up themselves (only the learners are simulated; the team is real).
SIMULATED_DOMAIN = "demo.xeducation.test"


def is_simulated_email(email: str | None) -> bool:
    return (email or "").strip().lower().endswith("@" + SIMULATED_DOMAIN)


def _merge(base: dict, extra: dict | None) -> dict:
    out = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        if k.startswith("_"):
            continue
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load(path: str = PATH) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return _merge(DEFAULTS, json.load(f))
    except FileNotFoundError:
        return copy.deepcopy(DEFAULTS)
    except ValueError as e:
        log.error("%s is not valid JSON (%s); using the built-in defaults", path, e)
        return copy.deepcopy(DEFAULTS)


S = load()
DEMO_MODE = get_settings().demo_mode
MODE = "demo" if DEMO_MODE else "live"


def by_mode(section: str):
    """A value that differs between demo mode and live mode, e.g. ``by_mode('score_refresh_minutes')``."""
    v = S[section]
    return v[MODE] if isinstance(v, dict) and MODE in v else v


def tiers() -> list[tuple[float, str]]:
    """[(min_score, name), ...] from the highest tier down."""
    return sorted(((float(t["min_score"]), t["name"]) for t in S["tiers"]), reverse=True)


def tier_names() -> list[str]:
    return [name for _, name in tiers()]


def in_global_control(user_id) -> bool:
    """True for the fixed random share of people (global_control.share, default 5%) whom the CRM never
    contacts automatically: no next-best-action steps, campaigns or A/B emails. Comparing them with
    everyone else measures the CRM's total impact, and their outcomes are the learning loop's honest
    check (nobody's follow-ups shaped them). Decided by a hash of the person, so it never changes."""
    share = float((S.get("global_control") or {}).get("share", 0) or 0)
    if share <= 0 or user_id is None:
        return False
    h = hashlib.sha256(f"global-control:{user_id}".encode()).hexdigest()
    return int(h[:15], 16) / float(16**15) < share
