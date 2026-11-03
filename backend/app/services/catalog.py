"""
The course catalogue: the single source of truth for titles, prices and course facts.

``app/resources/catalog.json`` is served to the website by ``GET /api/v1/courses`` and used by every part
of the backend (cart, checkout, emails, the chat assistant), so prices always come from the server and
never from the browser.
"""

import json
import os

_RESOURCES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resources")
_PATH = os.path.join(_RESOURCES, "catalog.json")
_FAQ_PATH = os.path.join(_RESOURCES, "faq.json")
_cache = {"mtime": None, "courses": [], "by_slug": {}}


def faq() -> dict:
    """The written answers to common questions (faq.json): the website shows them and the assistant repeats them."""
    try:
        with open(_FAQ_PATH, encoding="utf-8") as f:
            return {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    except (OSError, ValueError):
        return {}


def _load():
    try:
        mtime = os.path.getmtime(_PATH)
    except OSError:
        return _cache
    if mtime != _cache["mtime"]:
        with open(_PATH, encoding="utf-8") as f:
            courses = json.load(f)
        _cache.update(mtime=mtime, courses=courses, by_slug={c["slug"]: c for c in courses})
    return _cache


def all_courses():
    return _load()["courses"]


def get_course(slug):
    return _load()["by_slug"].get(slug) if slug else None


def title_of(slug, default=None):
    c = get_course(slug)
    return c["title"] if c else (default if default is not None else (slug or ""))


def price_of(slug):
    c = get_course(slug)
    return float(c["price"]) if c else None


def average_price():
    courses = all_courses()
    return sum(c["price"] for c in courses) / len(courses) if courses else 40000.0


def slug_for_title(title):
    """Best-effort reverse lookup (older lead rows only stored a title)."""
    if not title:
        return None
    t = title.strip().lower()
    for c in all_courses():
        if c["title"].lower() == t or c["slug"] == t:
            return c["slug"]
    return None


def facts(slug):
    """Short, true facts about a course for emails / chat (no invented numbers)."""
    c = get_course(slug)
    if not c:
        return None
    modules = ", ".join(m["title"] for m in c["curriculum"][:4])
    return {
        "title": c["title"],
        "duration": c["duration"],
        "level": c["level"],
        "price": c["price"],
        "emi": c["emi"],
        "modules": modules,
        "outcomes": c["outcomes"],
        "instructor": c["instructor"]["name"],
        "instructor_role": c["instructor"]["role"],
    }
