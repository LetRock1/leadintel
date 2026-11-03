"""
The one place that talks to Gemini (Google's ``google-genai`` SDK). Optional: without GEMINI_API_KEY nothing calls it,
and every caller falls back to its templates or rules when a call fails.

Three things keep it safe for a live demo:
  * Google retires model names every few months, so it tries GEMINI_MODEL from backend/.env first, then a few current
    names, and remembers the first one that answers.
  * Every call has a time limit (GEMINI_TIMEOUT seconds, default 12).
  * After a network failure Gemini is skipped for five minutes, so an offline demo does not wait on every email.
"""

from __future__ import annotations

import logging
import os
import time

from app.core.config import get_settings

log = logging.getLogger(__name__)

CANDIDATES = ["gemini-flash-latest", "gemini-2.5-flash", "gemini-2.0-flash"]
PAUSE_AFTER_NETWORK_ERROR = 300
_state: dict = {"model": None, "down_until": 0.0, "disabled": False, "client": None}


def _key() -> str:
    return (get_settings().gemini_api_key or "").strip()


def enabled() -> bool:
    return bool(_key()) and not _state["disabled"] and time.time() >= _state["down_until"]


def disable() -> None:
    """Templates only for the rest of this process (the history generator uses this)."""
    _state["disabled"] = True


def _names() -> list[str]:
    first = (get_settings().gemini_model or "").strip()
    return ([first] if first else []) + [m for m in CANDIDATES if m != first]


def _model_missing(e: Exception) -> bool:
    s = str(e).lower()
    return any(
        k in s for k in ("404", "not found", "not_found", "is not supported", "no longer available", "deprecated")
    )


def _client():
    if _state["client"] is None:
        from google import genai
        from google.genai import types

        timeout_ms = int(float(os.getenv("GEMINI_TIMEOUT", "12")) * 1000)
        _state["client"] = genai.Client(api_key=_key(), http_options=types.HttpOptions(timeout=timeout_ms))
    return _state["client"]


def generate(prompt: str, json_mode: bool = False) -> str:
    """Gemini's answer as text. Raises when it cannot answer (the caller then uses its fallback)."""
    if not _key() or _state["disabled"]:
        raise RuntimeError("Gemini is not configured")
    if time.time() < _state["down_until"]:
        raise RuntimeError("Gemini is paused after a network error")
    from google.genai import types

    config = types.GenerateContentConfig(response_mime_type="application/json") if json_mode else None
    names = [_state["model"]] if _state["model"] else _names()
    last: Exception | None = None
    for name in names:
        try:
            resp = _client().models.generate_content(model=name, contents=prompt, config=config)
            _state["model"] = name
            return resp.text or ""
        except Exception as e:  # noqa: BLE001 - every failure falls back to templates
            last = e
            if _model_missing(e):
                log.warning("Gemini model %s is not available; trying the next one", name)
                if _state["model"] == name:  # the remembered model was retired: try them all again
                    _state["model"] = None
                    return generate(prompt, json_mode)
                continue
            if any(
                k in str(e).lower()
                for k in ("connection", "timed out", "timeout", "proxy", "resolve", "unreachable", "network")
            ):
                _state["down_until"] = time.time() + PAUSE_AFTER_NETWORK_ERROR
                log.warning(
                    "Gemini is unreachable: using templates for the next %d minutes", PAUSE_AFTER_NETWORK_ERROR // 60
                )
            raise
    raise last or RuntimeError("No Gemini model is available")


def model_name() -> str | None:
    """The model that last answered (None before the first successful call)."""
    return _state["model"]
