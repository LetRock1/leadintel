"""A business with real learners only: no simulated history, the simulated learners switched off in backend/.env, and
pages that must work from the first day, before there is any decision or outcome."""

from __future__ import annotations

import pandas as pd
from support import CRM


def test_journeys_answer_with_every_key_before_any_decision(monkeypatch):
    from app.ml import journeys

    monkeypatch.setattr(journeys, "steps", lambda *_a, **_k: pd.DataFrame())
    out = journeys.summary()
    for key in ("sankey", "top_paths", "action_effects", "funnel", "dropoffs", "with_outcome", "decisions"):
        assert key in out, key
    assert out["action_effects"] == [] and out["top_paths"] == [] and out["with_outcome"] == 0
    # the funnel needs no decisions: where people stop is shown from the first sign-ups
    if out["funnel"]["stages"] and out["funnel"]["stages"][0]["people"]:
        assert out["dropoffs"]


def test_simulated_learners_switched_off_in_settings_stay_off(client, owner):
    """The tests run with SIMULATION_ENABLED=false, as a real-only business would."""
    s = client.get(f"{CRM}/simulation", headers=owner["headers"])
    assert s.status_code == 200, s.text
    assert s.json()["enabled"] is False and s.json()["switched_off_by_settings"] is True
    r = client.post(f"{CRM}/simulation/enabled", json={"enabled": True}, headers=owner["headers"])
    assert r.status_code == 409 and "SIMULATION_ENABLED=false" in r.json()["detail"]
    r = client.post(f"{CRM}/simulation/visit", json={"kind": "returning"}, headers=owner["headers"])
    assert r.status_code == 409
    assert (
        client.post(f"{CRM}/simulation/enabled", json={"enabled": False}, headers=owner["headers"]).status_code == 200
    )
