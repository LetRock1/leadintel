"""A real learner and a simulated learner who do exactly the same things get exactly the same treatment: the same
score and tier, the same decision receipt, the same money line and stage, the same coupon guard, and both count in
the totals. Only their email domain differs (simulated learners are never emailed, and the team presses Call for them
instead of typing the outcome of a real phone call)."""

from __future__ import annotations

from support import API, CRM

from app.core import rules


def _twin(new_learner, name, domain):
    for _ in range(10):  # outside the control group (5% of people are never contacted, by design)
        learner = new_learner(name, email=f"{name.lower().replace(' ', '.')}.{_}{id(name)}@{domain}")
        if not rules.in_global_control(learner["user"]["id"]):
            return learner
    raise AssertionError("no learner outside the control group in 10 tries")


def test_real_and_simulated_learners_doing_the_same_get_the_same_treatment(client, owner, new_learner):
    from app.services import money

    real = _twin(new_learner, "Twin Real", "example.com")
    sim = _twin(new_learner, "Twin Sim", rules.SIMULATED_DOMAIN)
    profile = {
        "current_occupation": "Working Professional",
        "specialization": "Finance Management",
        "city": "Pune",
        "phone": "+91 98765 43210",
        "lead_source": "Google",
    }
    events = [
        ("page_view", None, 40),
        ("page_view", "finance-banking", 120),
        ("pricing_view", "finance-banking", 20),
        ("video_play", "finance-banking", 30),
        ("brochure_dl", "finance-banking", 0),
    ]
    for who in (real, sim):
        h = who["headers"]
        assert client.post(f"{API}/profile/complete", json=profile, headers=h).status_code == 200
        sid = client.post(f"{API}/session/start", json={"device_type": "Mobile", "lead_source": "Google"}, headers=h)
        sid = sid.json()["session_id"]
        for ev, slug, sec in events:
            r = client.post(
                f"{API}/track",
                json={"session_id": sid, "event_type": ev, "course_slug": slug, "time_spent_sec": sec},
                headers=h,
            )
            assert r.status_code == 200, r.text
        assert client.post(f"{API}/cart", json={"course_slug": "finance-banking"}, headers=h).status_code == 200

    def row(who):
        r = client.get(f"{CRM}/leads", params={"search": who["email"]}, headers=owner["headers"]).json()["leads"][0]
        return r, client.get(f"{CRM}/leads/{r['id']}/now", headers=owner["headers"]).json()

    (rr, rn), (sr, sn) = row(real), row(sim)
    assert (rr["simulated"], sr["simulated"]) == (False, True)  # the one intended difference
    for key in ("lead_score", "conversion_probability", "recommended_action", "persona", "plv", "course_type"):
        assert rr[key] == sr[key], key
    assert rn["recommendation"]["action"] == sn["recommendation"]["action"]
    receipt = lambda n: {o["action"]: (round(o["incremental_profit"]), o.get("blocked")) for o in n["options"]}  # noqa: E731
    assert receipt(rn) == receipt(sn)
    values = money.board_values()
    for key in ("segment", "anyway", "add", "best", "p_anyway"):
        assert values[real["user"]["id"]][key] == values[sim["user"]["id"]][key], key
    guard = [
        client.get(
            f"{CRM}/coupons/check", params={"user_id": w["user"]["id"], "discount_pct": 10}, headers=owner["headers"]
        ).json()
        for w in (real, sim)
    ]
    for key in ("verdict", "p_without", "p_with", "expected_discount", "extra_profit"):
        assert guard[0][key] == guard[1][key], key
    # both buy: both are customers, and the totals count each in its own column
    before = client.get(f"{CRM}/stats", headers=owner["headers"]).json()
    for who in (real, sim):
        assert client.post(f"{API}/checkout", json={"coupon_code": ""}, headers=who["headers"]).status_code == 200
    after = client.get(f"{CRM}/stats", headers=owner["headers"]).json()
    assert after["customers"] - before["customers"] == 2
    assert after["real_customers"] - before["real_customers"] == 1
    assert row(real)[0]["customer"] and row(sim)[0]["customer"]
