"""
The anchored update (v7.1), checked against known truth.

The CRM takes a step only when the best step is expected to add profit, so leads just above and just below that line
differ only in whether the CRM acted. These tests build decision logs whose true left-alone chance and true lift are
known, in the CRM's own log format, and check that:
  * the paper's estimators (app.ml.anchor, ported unchanged) recover the lift, with nothing random at all and with
    random leaving-alone;
  * a logged decision is placed correctly relative to the cut-off, with the share of random steps read back from its
    logged probability;
  * when the CRM acts by a rule on one of the score's own signals and nothing is left to chance, v7.0's retrain cannot
    tell its step apart from that signal, and the anchored live layer can;
  * the learning loop's evaluation runs all three retraining methods end to end on real website features.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from app.ml import anchor as AN
from app.ml import features as F
from app.ml import lead_model as LM
from app.ml import learning as L

BETA = 0.6


def _opts(r, slot=None):
    """Logged options of a decision whose only possible steps are doing nothing and an information email worth r."""
    return json.dumps(
        [
            {"action": "none", "blocked": None, "incremental_profit": 0.0},
            {"action": "email_info", "blocked": None, "incremental_profit": float(r)},
            {"action": "call", "blocked": "no phone number", "incremental_profit": 0.0},
        ]
    )


def decision_log(n=60_000, eps=0.0, control=0.0, beta=BETA, seed=3, later=0.0):
    """next-best-action decisions in the CRM's log format: r is the step's extra profit (the running variable), the
    CRM acts when r > 0, takes eps of its decisions at random and never contacts the control group. The left-alone
    chance is smooth in r (continuity), the email adds `beta` log-odds."""
    rng = np.random.default_rng(seed)
    r = rng.uniform(-2000, 3000, n)
    g = -1.2 + 0.0003 * r
    hold = rng.random(n) < control
    best = np.where(r > 0, "email_info", "none")
    explore = (rng.random(n) < eps) & ~hold
    pick = np.where(rng.random(n) < 0.5, "email_info", "none")
    action = np.where(hold, "none", np.where(explore, pick, best))
    prop = np.where(action == best, 1 - eps + eps / 2, eps / 2)
    policy = np.where(hold, "holdout", np.where(explore, "explore", "model"))
    # a lead the CRM leaves alone now is followed up at a later trigger inside the outcome window with probability
    # `later` (the same email, the same effect: effects do not add up); the control group never is
    followed = (action == "none") & ~hold & (rng.random(n) < later)
    y = (rng.random(n) < AN.expit(g + beta * ((action == "email_info") | followed))).astype(int)
    rows = pd.DataFrame(
        {
            "user_id": np.arange(1, n + 1),
            "action": action,
            "policy": policy,
            "propensity": np.where(hold, 1.0, prop),
            "options_json": [_opts(v) for v in r],
            "model_best": best,
            "source": np.where(hold, "control group", "next-best-action"),
            "exp_key": None,
        }
    )
    return rows, y, AN.expit(g)


def test_a_decision_is_placed_relative_to_the_crms_own_cut_off():
    opts = json.dumps(
        [
            {"action": "none", "blocked": None, "incremental_profit": 0.0},
            {"action": "email_info", "blocked": None, "incremental_profit": 120.0},
            {"action": "call", "blocked": None, "incremental_profit": 700.0, "slot_price": 650.0},
            {"action": "whatsapp", "blocked": "not opted in to WhatsApp", "incremental_profit": 900.0},
        ]
    )
    # the call is worth 700 but only 50 after the price of a call slot: the email is the step the CRM would take
    g = AN.geometry(opts, "model", 1 - 0.15 + 0.15 / 3, "email_info", "email_info")
    assert g["step"] == "email_info" and g["r"] == pytest.approx(120.0) and g["d"] > 0
    assert g["k"] == 3
    assert g["p_step"] == pytest.approx(0.85 + 0.05) and g["p_none"] == pytest.approx(0.05)
    # a random learning step that took another step: the share of random steps is read back from its probability
    g = AN.geometry(opts, "explore", 0.05, "call", "email_info")
    assert g["p_none"] == pytest.approx(0.05)
    # below the cut-off nothing pays: the model does nothing
    low = opts.replace("120.0", "-30.0").replace('"incremental_profit": 700.0', '"incremental_profit": 600.0')
    g = AN.geometry(low, "model", 0.85 + 0.05, "none", "none")
    assert g["r"] == pytest.approx(-30.0) and g["d"] < 0 and g["p_none"] == pytest.approx(0.9)
    # the control group is never contacted
    g = AN.geometry(opts, "holdout", 1.0, "none", "email_info")
    assert g["p_step"] == 0.0 and g["p_none"] == 1.0
    # outside the design: doing nothing was not an option (an enquiry), or a step chosen by hand
    no_none = json.dumps([{"action": "none", "blocked": "not used for an enquiry"}, {"action": "email_info"}])
    assert AN.geometry(no_none, "model", 1.0, "email_info", "email_info") is None
    assert AN.geometry(opts, "manual", 1.0, "call", "email_info") is None


def test_the_crms_own_cut_off_gives_the_lift_with_nothing_left_to_chance():
    rows, y, _ = decision_log(eps=0.0, control=0.0)
    d = AN.designs(rows, y, boot=60)
    b, se = d["email_info"]["threshold"]
    assert np.isnan(d["email_info"]["random"][0])  # nobody above the cut-off was left alone: no random contrast
    assert abs(b - BETA) < 3 * se + 0.05, (b, se)
    assert 0.01 < se < 0.4
    assert d["email_info"]["design"][0] == pytest.approx(b)
    assert abs(d[AN.POOLED]["design"][0] - BETA) < 3 * d[AN.POOLED]["design"][1] + 0.05


def test_random_leaving_alone_gives_the_lift_too_and_the_two_are_combined():
    rows, y, _ = decision_log(eps=0.15, control=0.05)
    d = AN.designs(rows, y, boot=60)["email_info"]
    br, sr = d["random"]
    assert abs(br - BETA) < 3 * sr, (br, sr)
    b, se = d["design"]
    assert se < min(sr, d["threshold"][1])  # the combination is more precise than either part
    assert abs(b - BETA) < 3 * se + 0.03


def test_in_a_crm_that_follows_up_later_only_never_contacted_leads_give_the_lift_against_never():
    """Leads the CRM leaves alone now (below the line, or a random 'not now') are usually followed up at their next
    trigger. The line and the random 'not now' picks then measure acting now against acting later; the effect
    against never contacting a lead needs the never-contacted control group."""
    rows, y, _ = decision_log(eps=0.15, control=0.10, later=0.7, n=80_000)
    d = AN.designs(rows, y, boot=60)["email_info"]
    b_now, se_now = d["random"]  # the kit's left-alone: control group and random 'not now' picks
    b_never, se_never = d["random_control"]  # left alone = never contacted
    assert abs(b_never - BETA) < 3 * se_never + 0.03, (b_never, se_never)
    assert b_now < BETA - 0.15  # biased towards 'now against later'
    assert d["threshold"][0] < BETA - 0.2  # the line too: below it, leads are followed up later
    assert abs(AN.control_betas({"email_info": d})["email_info"] - d["design_control"][0]) < 1e-12


def _signal_log(n=40_000, seed=11):
    """The CRM sends an email exactly to the leads who looked at the pricing page (one of the score's own signals),
    nothing random, no control group: the email and that signal cannot be told apart in the log."""
    rng = np.random.default_rng(seed)
    z = rng.normal(-1.0, 0.8, n)
    S = (rng.random((n, len(LM.LIVE_NAMES))) < 0.3).astype(float)
    j = LM.LIVE_NAMES.index("PricingPageVisited")
    w = np.zeros(len(LM.LIVE_NAMES))
    w[j] = 0.3  # what pricing truly adds on top of the base model
    a = S[:, j]
    g = z + S @ w
    y = (rng.random(n) < AN.expit(g + BETA * a)).astype(int)
    Nm = np.zeros((n, len(L.NUISANCE_COLS)))
    Nm[:, L.NUISANCE_COLS.index("email_info")] = a
    return z, S, Nm, y, AN.expit(g), a == 1


def test_the_anchored_live_layer_separates_a_step_that_v70_cannot(monkeypatch):
    z, S, Nm, y, truth, targeted = _signal_log()

    def bias_of(live):
        return float((L._p(live, z, S)[targeted] - truth[targeted]).mean())

    naive, _ = L.fit_live(z, S, y, Nm[:, L.KEPT_IDX], L.KEPT_COLS)
    assert bias_of(naive) > 0.08  # the CRM's own email learned as lead quality
    aware, anchored, own = {}, {}, {}
    for ridge in (0.5, 8.0):  # the penalty on the score's own signals (crm_settings.json learning.ridge)
        monkeypatch.setitem(L.CONF, "ridge", ridge)
        live, eff = L.fit_live(z, S, y, Nm, L.NUISANCE_COLS)
        aware[ridge], own[ridge] = bias_of(live), eff["email_info"]
        live, eff_a = L.fit_anchored(z, S, y, Nm, {"email_info": BETA})
        anchored[ridge] = bias_of(live)
        assert eff_a["email_info"] == pytest.approx(BETA)  # the fixed lift is what the score switches off
    # v7.0: the log cannot tell the email from the pricing page, so the penalty decides how the joint effect is
    # split, and the score is wrong in a direction set by a setting, not by the data (THEORY.md R6 ii)
    assert aware[0.5] > 0.015 and aware[8.0] < -0.015
    assert abs(own[0.5] - own[8.0]) > 0.2
    # the anchored live layer takes the email's effect from the design: right, whatever the penalty
    for ridge in (0.5, 8.0):
        assert abs(anchored[ridge]) < 0.1 * bias_of(naive)


def test_with_a_wrong_lift_the_error_follows_the_first_order_rule():
    z, S, Nm, y, truth, targeted = _signal_log(seed=12)
    delta = 0.2
    live, _ = L.fit_anchored(z, S, y, Nm, {"email_info": BETA + delta})
    err = float((L._p(live, z, S)[targeted] - truth[targeted]).mean())
    v0 = float((truth[targeted] * (1 - truth[targeted])).mean())
    assert abs(err - (-delta * v0)) < 0.35 * delta * v0


def _website_rows(n=4000, seed=5, control=0.20):
    """Decision points on real website features (the simulator's population): the CRM acts when the base model
    gives at least a 25% chance (the cut-off), takes 15% of decisions at random and never contacts a control group
    (larger than the product's 5% so that a few thousand rows measure the step well)."""
    from app.simulation import population

    raw = population.generate(n, seed=seed, return_truth=True)
    records = raw.to_dict("records")
    feats = [F.normalize_raw({k: v for k, v in r.items() if not str(k).startswith("_")}) for r in records]
    bundle = L._load_lead_bundle()
    z = LM.starter_logit(bundle, F.to_model_frame(feats))
    # a stream of its own: the population was drawn from default_rng(seed), and reusing it would tie the "random"
    # control group and random steps to the very features the score is made of
    rng = np.random.default_rng([seed, 1])
    r = 4000 * (AN.expit(z) - 0.25)
    hold = rng.random(n) < control
    eps = 0.15
    best = np.where(r > 0, "email_info", "none")
    explore = (rng.random(n) < eps) & ~hold
    pick = np.where(rng.random(n) < 0.5, "email_info", "none")
    action = np.where(hold, "none", np.where(explore, pick, best))
    prop = np.where(action == best, 1 - eps + eps / 2, eps / 2)
    truth = AN.expit(z)  # the starting model is right about this population
    y = (rng.random(n) < AN.expit(z + BETA * (action == "email_info"))).astype(int)
    rows = pd.DataFrame(
        {
            "user_id": np.arange(1, n + 1),
            "t": "2026-01-01 10:00:00",
            "action": action,
            "propensity": np.where(hold, 1.0, prop),
            "policy": np.where(hold, "holdout", np.where(explore, "explore", "model")),
            "features_json": [json.dumps(f) for f in feats],
            "source": np.where(hold, "control group", "next-best-action"),
            "options_json": [_opts(v) for v in r],
            "model_best": best,
            "exp_key": None,
            "y": y,
            L.CONTROL_COL: hold.astype(float),
        }
    )
    for c in L.NUISANCE_COLS:
        rows[c] = (rows["action"] == c).astype(float) if c in L.ACTION_COLS else 0.0
    return bundle, rows, truth


def test_the_learning_loop_evaluates_all_three_retraining_methods(starting_models):
    bundle, rows, truth = _website_rows()
    m, ours, effects = L.evaluate(bundle, rows, resamples=50, boot=40)
    # the default: each step's effect from leads acted on against the never-contacted control group
    assert m["retrain_method"] == L.METHOD == "anchored_control"
    assert "email_info" in m["fixed_steps"]
    steps = {d["step"]: d for d in m["design"]}
    assert steps["email_info"]["basis"] == "design_control"
    assert effects["email_info"] == pytest.approx(steps["email_info"]["design_control"][0])
    assert steps["email_info"]["weights"] == {"random_control": 1.0}
    for k in ("anchored_true_logloss", "aware_true_logloss", "naive_true_logloss", "anchored_live_logloss"):
        assert np.isfinite(m[k]), k
    for basis in ("design", "design_control"):  # no later follow-ups here: the kit's combination is right too
        b, se = steps["email_info"][basis]
        assert abs(b - BETA) < 3 * se + 0.1, (basis, b, se)
    assert m["chart"] and {b["side"] for b in m["chart"]["bins"]} == {"below", "above"}
    # the research kit's estimator stays available to the research comparison (ml/experiments/anchored_check.py)
    m_kit, _, effects_kit = L.evaluate(bundle, rows, resamples=20, boot=40, method="anchored")
    assert m_kit["retrain_method"] == "anchored"
    kit = {d["step"]: d for d in m_kit["design"]}["email_info"]
    assert kit["basis"] == "design" and effects_kit["email_info"] == pytest.approx(kit["design"][0])
    # the score (actions switched off) is close to the truth where the CRM acts; the naive retrain is not
    z, S, Nm = L.arrays(bundle, rows)
    naive, _ = L.fit_live(z, S, rows["y"].to_numpy(), Nm[:, L.KEPT_IDX], L.KEPT_COLS)
    top = rows["model_best"].to_numpy() == "email_info"
    ours_bias = float((L._p(ours, z, S)[top] - truth[top]).mean())
    naive_bias = float((L._p(naive, z, S)[top] - truth[top]).mean())
    assert naive_bias > 0.03
    assert abs(ours_bias) < 0.4 * naive_bias


def test_ask_answers_what_the_steps_add_from_the_model_in_use(client, owner):
    """Ask reads what the team's work adds after each step from the lead model in use (the effects the learning loop
    fixed or learned), in points of buying chance for a lead with a 30% chance on their own; the Learning page shows
    no research comparison."""
    from support import CRM

    from app.services import analytics

    question = {"question": "What do our emails and calls add?"}
    out = client.post(f"{CRM}/copilot", json=question, headers=owner["headers"])
    assert out.status_code == 200, out.text
    out = out.json()
    assert out["intent"] == "outreach"
    card = analytics.card("model_card.json") or {}
    steps = {e["input"]: round(e["points"], 1) for e in card.get("own_effects") or [] if e["input"] in L.ACTION_COLS}
    if steps:
        assert out["tools"][0]["data"] == steps
        assert "Measured against leads the CRM never contacts" in out["answer"]
    else:
        assert out["answer"].startswith("Not learned yet")
    page = client.get(f"{CRM}/learning/overview", headers=owner["headers"])
    assert page.status_code == 200, page.text
    page = page.json()
    assert "threshold" not in page and "retrain_method" not in page["settings"]
    assert page["settings"]["exploration_rate"] == 0.15
    assert all("design_json" not in r for r in page["runs"])
