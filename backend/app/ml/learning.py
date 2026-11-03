"""
The automatic learning loop: the CRM learns from its own results without fooling itself.

The problem. A CRM that retrains its lead score on "who bought" learns its own follow-ups as if
they were lead quality: hot leads get emails, coupons and calls, those make them buy, and the
retrained model concludes that people like them are even hotter. The usual check (accuracy on
recent data) then picks that inflated model, because the same follow-ups shaped that data. On
real randomized data (Hillstrom, 64,000 customers) the usual check picked the inflated model in 50 of 50
repeats (E3, ml/experiments/learning_loop.py).

What this loop does, every time enough new outcomes are known:

  1. DATA     every decision point with a known outcome: each moment the CRM decided what to do
              about a lead (a next-best-action decision, or a campaign / A/B test arm) — what the CRM
              knew about the lead then, and whether they bought within the outcome window (14 days).
  2. TOLD WHAT WE DID  each row also says what the CRM did at that moment (nothing, an email, a
              coupon, a call, WhatsApp, a campaign email), how many days had passed since the
              person was last on the website (campaign rows reach people who left weeks ago) and how
              long they had been a lead (days since sign-up).
  3. LEARN    the live layer of the lead model (lead_model.py) is fitted WITH those inputs. The CRM's
              own steps are switched off in the score: it is the chance of buying if we do nothing
              now, so our own emails, coupons and calls are never counted as lead quality. Time away
              and lead age stay in the score (a lead who went quiet, or who has browsed for weeks
              without buying, is less likely to buy); their size is learned, not set by hand.
  4. CHECK    the new model (challenger), the current one (champion) and a naive retrain (the same
              model, not told what the CRM did) are compared on the untouched control group — the
              5% of leads the CRM never contacts (crm_settings.json: global_control). Nobody's
              follow-ups shaped their outcomes. New models are judged only on people they were not
              fitted on (5-fold cross-fitting by person).
  5. SWAP     only if the challenger beats the champion on the control group in at least
              `swap_confidence` (90%) of bootstrap resamples of those people. Otherwise it stays.
  6. RECORD   every run is written to learning_runs with its numbers and the reason.

Why "the step taken right then" and not "every follow-up in the next 14 days": follow-ups keep
coming while a lead has NOT bought, so "got more follow-ups" partly just means "hadn't bought yet"
(reverse causation) — counted that way, our own follow-ups even look harmful.

The next-best-action (uplift) model is retrained in the same run from the decision log (the 15%
random decisions make that honest) and replaced only if the lower end of the 95% interval of its
profit gain on held-out decisions is above zero.

Runs automatically (scheduler.py: every 5 min in demo mode / hourly, when at least
`min_new_outcomes` new outcomes are known), from the dashboard ("Retrain now") and month by month
inside the generated history (app/simulation/history.py).
"""

import datetime as dt
import hashlib
import json
import logging
import os
import shutil
import threading

import joblib
import numpy as np
import pandas as pd

from app import db
from app.core import rules
from app.core.config import get_settings
from app.ml import anchor as AN
from app.ml import features as F
from app.ml import lead_model as LM
from app.ml import nba_core as N

log = logging.getLogger(__name__)


MODEL_DIR = str(get_settings().model_dir)
LEAD_PATH = os.path.join(MODEL_DIR, "lead_model.pkl")
NBA_PATH = os.path.join(MODEL_DIR, "nba_model.pkl")
CARD_PATH = os.path.join(MODEL_DIR, "model_card.json")
NBA_CARD_PATH = os.path.join(MODEL_DIR, "nba_card.json")

CONF = rules.S["learning"]
WINDOW_DAYS = int(rules.S["outcome_window_days"])
# What the CRM did (inputs while learning, switched off for the score), and how long the person has been
# away and has been a lead (learned the same way, kept in the score: lead_model.recency_effect / age_effect).
ACTION_COLS = [a for a in N.ACTION_LIST if a != "none"] + ["campaign"]  # the step taken right then
RECENCY_COLS = ["away_1_7_days", "away_7_14_days", "away_14_30_days", "away_30_days_plus"]
AGE_COLS = [name for name, _, _ in LM.AGE_BUCKETS] if CONF.get("lead_age", True) else []
KEPT_COLS = RECENCY_COLS + AGE_COLS  # time effects: learned next to our actions, kept in the score
NUISANCE_COLS = ACTION_COLS + KEPT_COLS
CONTROL_COL = "control_group"  # in the untouched control group (the honest check, not an input)
RECENCY_IDX = [NUISANCE_COLS.index(c) for c in RECENCY_COLS]
KEPT_IDX = [NUISANCE_COLS.index(c) for c in KEPT_COLS]
LABELS = {
    **{a: N.ACTIONS[a]["label"] for a in N.ACTION_LIST if a != "none"},
    "campaign": "Campaign or A/B email",
    "away_1_7_days": "Last seen 1-7 days ago",
    "away_7_14_days": "Last seen 7-14 days ago",
    "away_14_30_days": "Last seen 14-30 days ago",
    "away_30_days_plus": "Last seen 30+ days ago",
    "age_7_14_days": "Signed up 7-14 days ago",
    "age_14_30_days": "Signed up 14-30 days ago",
    "age_30_days_plus": "Signed up 30+ days ago",
}
MIN_CONTROL_PEOPLE, MIN_SLICE_CLASS = 20, 5  # untouched people needed to judge a model
MIN_NBA_DECISIONS = 100
REAL_WEIGHT_NBA = 5.0
FOLDS = 5
TS = "%Y-%m-%d %H:%M:%S"

_run_lock = threading.Lock()
_prior_cache = {}


# small helpers
def _ts(t):
    return t.strftime(TS) if isinstance(t, dt.datetime | pd.Timestamp) else str(t)


def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.asarray(z, dtype=float)))


def _read(con, sql, params=()):
    return pd.read_sql_query(sql, con, params=params)


def _asof(left, left_time, right, right_time, by="user_id", direction="forward", strictly=True):
    """For each row of `left`: the first `right` time after (direction='forward') or the last before
    (direction='backward') its own time, for the same person. NaT when there is none."""
    if left.empty or right.empty:
        return np.full(len(left), np.datetime64("NaT"), dtype="datetime64[ns]")
    L = pd.DataFrame(
        {
            by: left[by].to_numpy(dtype="int64"),
            "_t": pd.to_datetime(left[left_time]).to_numpy(),
            "_i": np.arange(len(left)),
        }
    ).sort_values("_t")
    R = pd.DataFrame({by: right[by].to_numpy(dtype="int64"), "_r": pd.to_datetime(right[right_time]).to_numpy()})
    R = R.dropna().sort_values("_r")
    R["_hit"] = R["_r"]
    m = pd.merge_asof(L, R, left_on="_t", right_on="_r", by=by, direction=direction, allow_exact_matches=not strictly)
    return m.sort_values("_i")["_hit"].to_numpy()


def _outcomes(frame, time_col, purchases, as_of):
    """y (bought within the window, by as_of), matured (outcome known), customer_before."""
    t = pd.to_datetime(frame[time_col]).to_numpy()
    window = np.timedelta64(WINDOW_DAYS, "D")
    cutoff = pd.Timestamp(as_of).to_datetime64()
    first = _asof(frame, time_col, purchases, "purchased_at", direction="forward", strictly=True)
    with np.errstate(invalid="ignore"):
        y = (~pd.isna(first)) & (first <= t + window) & (first <= cutoff)
        matured = y | (t <= cutoff - window)
    before = _asof(frame, time_col, purchases, "purchased_at", direction="backward", strictly=False)
    return y.astype(int), matured, ~pd.isna(before)


def _parse_features(series):
    return [json.loads(s) if isinstance(s, str) and s else {} for s in series]


# 1./2. DATA: decision points, and what the CRM did
def _coupon_pct_at(con, frame, as_of):
    """Discount of a coupon issued to the person within 30 minutes after each row's time (0 if none)."""
    coupons = _read(
        con, "SELECT user_id, created_at AS t, discount_pct FROM coupons_issued WHERE created_at <= ?", (as_of,)
    )
    coupons["t"] = pd.to_datetime(coupons["t"], errors="coerce")
    coupons = coupons.dropna(subset=["t"])
    if coupons.empty or frame.empty:
        return np.zeros(len(frame))
    L = pd.DataFrame(
        {
            "user_id": frame["user_id"].to_numpy(dtype="int64"),
            "t": pd.to_datetime(frame["t"]).to_numpy(),
            "_i": np.arange(len(frame)),
        }
    ).sort_values("t")
    R = pd.DataFrame(
        {
            "user_id": coupons["user_id"].to_numpy(dtype="int64"),
            "t": coupons["t"].to_numpy(),
            "pct": coupons["discount_pct"].to_numpy(dtype=float),
        }
    ).sort_values("t")
    m = pd.merge_asof(L, R, on="t", by="user_id", direction="forward", tolerance=pd.Timedelta(minutes=30)).sort_values(
        "_i"
    )
    return np.nan_to_num(m["pct"].to_numpy(dtype=float), nan=0.0)


POINT_COLS = [
    "user_id",
    "t",
    "action",
    "propensity",
    "policy",
    "features_json",
    "source",
    "options_json",  # next-best-action: every step's numbers at that moment (where the CRM's own cut-off was)
    "model_best",  # next-best-action: the step the model picked
    "exp_key",  # campaigns and A/B tests: which one (each is compared with its own hold-out or control arm)
]


def _decision_points(con, as_of):
    """Every decision the CRM made up to as_of (POINT_COLS)."""
    parts = []
    dec = _read(
        con,
        """SELECT user_id, created_at AS t, action, propensity, COALESCE(policy,'model') AS policy,
                               features_json, options_json, model_best FROM nba_decisions
                        WHERE (propensity > 0 OR policy='holdout') AND features_json IS NOT NULL AND created_at <= ?""",
        (as_of,),
    )
    if not dec.empty:
        dec["source"] = np.where(dec["policy"] == "holdout", "control group", "next-best-action")
        dec["exp_key"] = None
        parts.append(dec)
    asg = _read(
        con,
        """SELECT user_id, assigned_at AS t, experiment_type, experiment_id, arm, probability AS propensity,
                               features_json FROM experiment_assignments
                        WHERE probability > 0 AND features_json IS NOT NULL AND features_json NOT IN ('', '{}')
                          AND experiment_type IN ('ab', 'campaign') AND assigned_at <= ?""",
        (as_of,),
    )
    if not asg.empty:
        sent = ~asg["arm"].isin(["control", "holdout"]).to_numpy()
        pct = _coupon_pct_at(con, asg, as_of)
        asg["action"] = np.where(
            ~sent, "none", np.where(pct >= 15, "email_coupon_20", np.where(pct > 0, "email_coupon_10", "campaign"))
        )
        asg["policy"] = "experiment"
        asg["source"] = np.where(asg["experiment_type"] == "ab", "A/B test", "campaign")
        asg["exp_key"] = asg["experiment_type"].astype(str) + ":" + asg["experiment_id"].astype(str)
        asg["options_json"] = None
        asg["model_best"] = None
        parts.append(asg.drop(columns=["experiment_type", "experiment_id", "arm"]))
    if not parts:
        return pd.DataFrame(columns=POINT_COLS)
    rows = pd.concat(parts, ignore_index=True)
    rows = rows[rows["action"].isin(["none"] + ACTION_COLS)].reset_index(drop=True)
    rows["t"] = pd.to_datetime(rows["t"])
    return rows


def assemble(con, as_of):
    """Decision points with a known outcome, each with what the CRM did (see the module docstring)."""
    purchases = _read(con, "SELECT user_id, purchased_at FROM purchases WHERE purchased_at <= ?", (as_of,))
    every = _decision_points(con, as_of)
    base_cols = POINT_COLS + ["y", CONTROL_COL]
    if every.empty:
        return pd.DataFrame(columns=base_cols + NUISANCE_COLS)
    every["y"], matured, customer = _outcomes(every, "t", purchases, as_of)
    rows = every[(~customer) & matured].reset_index(drop=True)
    if rows.empty:
        return pd.DataFrame(columns=base_cols + NUISANCE_COLS)
    acts = rows["action"].to_numpy()
    for c in ACTION_COLS:
        rows[c] = (acts == c).astype(float)
    rows[CONTROL_COL] = (rows["policy"] == "holdout").astype(float)
    # how long since the person was last on the website (decisions after a visit: ~0 days)
    seen = _read(con, "SELECT user_id, created_at AS t FROM behaviour_events WHERE created_at <= ?", (as_of,))
    last = _asof(rows, "t", seen, "t", direction="backward", strictly=False)
    with np.errstate(invalid="ignore"):
        away = (pd.to_datetime(rows["t"]).to_numpy() - last) / np.timedelta64(1, "D")
    away = np.nan_to_num(np.asarray(away, dtype=float), nan=60.0)
    rows["away_days"] = away
    rows["away_1_7_days"] = ((away > 1) & (away <= 7)).astype(float)
    rows["away_7_14_days"] = ((away > 7) & (away <= 14)).astype(float)
    rows["away_14_30_days"] = ((away > 14) & (away <= 30)).astype(float)
    rows["away_30_days_plus"] = (away > 30).astype(float)
    # how long the person had been a lead at that moment (days since sign-up)
    signed = _read(con, "SELECT id AS user_id, created_at AS signed_up FROM users")
    when = (
        dict(zip(signed["user_id"], pd.to_datetime(signed["signed_up"], errors="coerce"))) if not signed.empty else {}
    )
    age = (rows["t"] - rows["user_id"].map(when)).dt.total_seconds().to_numpy(dtype=float) / 86400.0
    age = np.nan_to_num(age, nan=0.0)
    rows["age_days"] = age
    for name, lo, hi in LM.AGE_BUCKETS:
        if name in AGE_COLS:
            rows[name] = ((age >= lo) & (age < (hi if hi is not None else np.inf))).astype(float)
    rows["t"] = rows["t"].dt.strftime(TS)
    return rows.sort_values("t", kind="mergesort").reset_index(drop=True)


def person_folds(users):
    """Fixed fold (0..FOLDS-1) per person, from a hash, so one person's rows are never split."""
    return np.array([int(hashlib.sha256(f"fold:{u}".encode()).hexdigest()[:8], 16) % FOLDS for u in users])


# 3. LEARN
def arrays(bundle, rows):
    """(starter logit z, site-signal matrix S, what-the-CRM-did matrix Nm) for assembled rows."""
    frame = F.to_model_frame(_parse_features(rows["features_json"]))
    z = LM.starter_logit(bundle, frame)
    S = LM.live_matrix(frame)
    Nm = rows[NUISANCE_COLS].to_numpy(dtype=float)
    return z, S, Nm


def _penalties(n_extra):
    ridge = float(CONF.get("ridge", 2.0))
    return np.array([0.01, 5.0] + [ridge] * len(LM.LIVE_NAMES) + [0.5] * n_extra)


def fit_live(z, S, y, X=None, cols=None, w=None):
    """Fit the live layer on top of the base model's logit z. X / cols: extra inputs (what the CRM
    did, how cold the lead was) whose effects are learned apart from lead quality."""
    extra = 0 if X is None else X.shape[1]
    parts = [np.ones(len(z)), np.asarray(z, dtype=float), S] + ([X] if extra else [])
    beta = LM.fit_offset_logreg(np.column_stack(parts), y, z, sample_weight=w, l2=_penalties(extra))
    k = len(LM.LIVE_NAMES)
    live = {
        "signals": list(LM.LIVE_NAMES),
        "intercept": float(beta[0]),
        "slope": float(1.0 + beta[1]),
        "weights": [float(b) for b in beta[2 : 2 + k]],
    }
    effects = {c: float(b) for c, b in zip(cols or [], beta[2 + k :])}
    return live, effects


def _logit_base(live, z, S):
    """The score's logit: do nothing now, no recent nudges, just active on the site."""
    w = np.asarray((live or {}).get("weights") or [], dtype=float)
    if len(w) != S.shape[1]:  # live layer from another code version: starter only
        return np.asarray(z, dtype=float)
    return float(live.get("slope", 1.0)) * np.asarray(z, dtype=float) + float(live.get("intercept", 0.0)) + S @ w


def _p(live, z, S, Nm=None, effects=None, keep=None):
    """P(buy within the window). With Nm + effects: as each row really was (what the CRM did included);
    `keep` = column names to keep from Nm (e.g. only how cold the lead was)."""
    zz = _logit_base(live, z, S)
    if Nm is not None and effects:
        for j, c in enumerate(NUISANCE_COLS):
            if c in effects and (keep is None or c in keep):
                zz = zz + effects[c] * Nm[:, j]
    return _sigmoid(zz)


def crossfit(z, S, y, fold, Nm, cols):
    """Out-of-fold predictions: everyone is scored by a model fitted without them.
    Returns (as they really were, only how cold the lead was kept)."""
    X = Nm[:, [NUISANCE_COLS.index(c) for c in cols]]
    actual = np.full(len(y), np.nan)
    score = np.full(len(y), np.nan)
    for k in range(FOLDS):
        te = fold == k
        tr = ~te
        if not te.any() or len(np.unique(y[tr])) < 2:
            continue
        live, eff = fit_live(z[tr], S[tr], y[tr], X[tr], cols)
        actual[te] = _p(live, z[te], S[te], Nm[te], eff)
        score[te] = _p(live, z[te], S[te], Nm[te], eff, keep=KEPT_COLS)
    return actual, score


# The anchored update (v7.1, app.ml.anchor): each step's effect fixed at what the CRM's own design says
STEP_IDX = {c: NUISANCE_COLS.index(c) for c in ACTION_COLS}
METHODS = ("anchored", "anchored_shrunk", "anchored_control", "action_aware")
# the product's method: each step's effect from the never-contacted control group (the others are kept for the research
# comparison in ml/experiments/anchored_check.py, which names them explicitly)
METHOD = "anchored_control"
METHOD_LABEL = {
    "anchored": "Anchored to the CRM's own experiments (v7.1)",
    "anchored_shrunk": "Anchored to the CRM's own experiments, weighed against the model's own estimates (v7.1)",
    "anchored_control": "Each step's effect from the never-contacted control group (v7.1)",
    "action_aware": "Told what the CRM did, effects learned by the model (v7.0)",
}


def fit_anchored(z, S, y, Nm, betas, w=None):
    """The live layer with each step's effect fixed at its design-based lift: logit P = g(lead) + beta_step, fitted
    on every decision point with beta_step as an offset (app.ml.anchor). Steps without a design-based lift (no
    contrast yet) and the effects of time are learned as in fit_live. Returns (live layer, effects): effects holds
    the fixed lifts and the learned effects together, so _p reads both the same way."""
    fixed = {c: float(b) for c, b in (betas or {}).items() if c in STEP_IDX and np.isfinite(b)}
    off = np.asarray(z, dtype=float).copy()
    for c, b in fixed.items():
        off = off + b * Nm[:, STEP_IDX[c]]
    free = [c for c in NUISANCE_COLS if c not in fixed]
    X = Nm[:, [NUISANCE_COLS.index(c) for c in free]]
    parts = [np.ones(len(z)), np.asarray(z, dtype=float), S] + ([X] if free else [])
    beta = LM.fit_offset_logreg(np.column_stack(parts), y, off, sample_weight=w, l2=_penalties(len(free)))
    k = len(LM.LIVE_NAMES)
    live = {
        "signals": list(LM.LIVE_NAMES),
        "intercept": float(beta[0]),
        "slope": float(1.0 + beta[1]),
        "weights": [float(b) for b in beta[2 : 2 + k]],
    }
    effects = {c: float(b) for c, b in zip(free, beta[2 + k :])}
    effects.update(fixed)
    return live, {c: effects[c] for c in NUISANCE_COLS if c in effects}


def pooled_betas(design):
    """The kit's single-action setting: one lift for "the CRM took some step", the same for every step."""
    b = ((design or {}).get(AN.POOLED) or {}).get("design", (np.nan, np.nan))[0]
    return {c: float(b) for c in ACTION_COLS} if b is not None and np.isfinite(b) else {}


def _fit(method, z, S, y, Nm, rows=None, geo=None, boot=AN.BOOT, design=None):
    """One retraining method on these decision points. Returns (live layer, effects, design or None)."""
    if method == "naive":
        live, eff = fit_live(z, S, y, Nm[:, KEPT_IDX], KEPT_COLS)
        return live, eff, None
    if method == "action_aware":
        live, eff = fit_live(z, S, y, Nm, NUISANCE_COLS)
        return live, eff, None
    if design is None:
        design = AN.designs(rows, y, geo, boot)
    if method == "anchored":
        betas = AN.betas_from(design)
    elif method == "anchored_shrunk":  # the kit's variant: each lift weighed against the model's own estimate
        _, own = fit_live(z, S, y, Nm, NUISANCE_COLS)
        betas = AN.shrunk_betas(design, own)
    elif method == "anchored_control":  # "left alone" = never contacted: the control group above the line
        betas = AN.control_betas(design)
    else:
        betas = pooled_betas(design)
    live, eff = fit_anchored(z, S, y, Nm, betas)
    return live, eff, design


def crossfit_methods(methods, z, S, y, fold, Nm, rows, geo, boot=AN.BOOT):
    """Out-of-fold predictions for several methods at once ({method: (as they really were, the score)}). The
    anchored update takes its lifts from the training folds only, so the held-out fold never informs them."""
    out = {m: (np.full(len(y), np.nan), np.full(len(y), np.nan)) for m in methods}
    for k in range(FOLDS):
        te = fold == k
        tr = ~te
        if not te.any() or len(np.unique(y[tr])) < 2:
            continue
        idx = np.where(tr)[0]
        design = None
        if any(m.startswith("anchored") for m in methods):
            design = AN.designs(rows.iloc[idx].reset_index(drop=True), y[tr], [geo[i] for i in idx], boot)
        for m in methods:
            live, eff, _ = _fit(m, z[tr], S[tr], y[tr], Nm[tr], design=design)
            out[m][0][te] = _p(live, z[te], S[te], Nm[te], eff)
            out[m][1][te] = _p(live, z[te], S[te], Nm[te], eff, keep=KEPT_COLS)
    return out


def _weights(d, keys):
    """How much of an inverse-variance combination each source carries (shares that sum to 1)."""
    ws = {k: 1 / d[k][1] ** 2 for k in keys if d.get(k) and np.isfinite(d[k][1] if d[k][1] is not None else np.nan)}
    tot = sum(ws.values())
    return {k: round(v / tot, 3) for k, v in ws.items()} if tot else {}


def design_summary(design, effects_aware=None, effects_used=None, method=None):
    """What the Learning page shows about each step's lift: the contrasts from the CRM's own experiments, their
    combinations, the lift the score actually switches off, and what the v7.0 retrain (the model's own estimate)
    would have used, in log-odds. `basis` names the combination the retraining method in use relies on:
    'design_control' (against never-contacted leads: acted on against the control group above the line) or 'design'
    (the kit's: the line itself, every lead left alone at random, campaign and A/B hold-outs)."""
    method = method or METHOD
    basis = "design_control" if method == "anchored_control" else "design"
    keys = ("random_control",) if basis == "design_control" else ("threshold", "random", "experiments")
    out = []
    for s in AN.STEPS + [AN.POOLED]:
        d = (design or {}).get(s)
        if not d:
            continue
        row = {
            "step": s,
            "label": LABELS.get(s, "Any step") if s != AN.POOLED else "Any step",
            "basis": basis,
            "threshold": list(d["threshold"]),
            "random": list(d["random"]),
            "random_control": list(d.get("random_control", (np.nan, np.nan))),
            "experiments": list(d["experiments"]),
            "experiments_n": d.get("experiments_n", 0),
            "design": list(d["design"]),
            "design_control": list(d.get("design_control", (np.nan, np.nan))),
            "n_below": d.get("n_below", 0),
            "n_above": d.get("n_above", 0),
            "left_alone_above": d.get("left_alone_above", 0),
            "share_below": d.get("share_below"),
            "share_above": d.get("share_above"),
            "model_own": (effects_aware or {}).get(s),
            "used": (effects_used or {}).get(s),
            "weights": _weights(d, keys),
        }
        out.append(row)
    return AN.jsonable(out)


def effect_points(effects, base_prob=0.30):
    """How many points of buying chance each input adds for a typical lead (for display)."""
    z0 = float(LM.logit([base_prob])[0])
    return [
        {
            "input": c,
            "label": LABELS.get(c, c),
            "weight": round(float(b), 3),
            "points": round(float(_sigmoid(z0 + float(b)) - base_prob) * 100, 1),
        }
        for c, b in (effects or {}).items()
    ]


# 4. CHECK
def wlogloss(y, p, w=None):
    y, p = np.asarray(y, float), np.clip(np.asarray(p, float), 1e-5, 1 - 1e-5)
    w = np.ones(len(y)) if w is None else np.asarray(w, float)
    return float(-(w * (y * np.log(p) + (1 - y) * np.log(1 - p))).sum() / w.sum())


def wauc(y, p, w=None):
    """Weighted ROC-AUC (probability a random buyer is ranked above a random non-buyer)."""
    y, p = np.asarray(y, int), np.asarray(p, float)
    w = np.ones(len(y)) if w is None else np.asarray(w, float)
    if len(y) == 0 or y.min() == y.max():
        return None
    order = np.argsort(p, kind="mergesort")
    y, p, w = y[order], p[order], w[order]
    total, neg_below, i, n = 0.0, 0.0, 0, len(p)
    while i < n:  # walk through groups of tied scores
        j = i
        while j + 1 < n and p[j + 1] == p[i]:
            j += 1
        pos_w = float(w[i : j + 1][y[i : j + 1] == 1].sum())
        neg_w = float(w[i : j + 1][y[i : j + 1] == 0].sum())
        total += pos_w * (neg_below + 0.5 * neg_w)
        neg_below += neg_w
        i = j + 1
    pos_total, neg_total = float(w[y == 1].sum()), float(w[y == 0].sum())
    return total / (pos_total * neg_total) if pos_total and neg_total else None


def prob_better(y, people, p_old, p_new, resamples=300, seed=11):
    """Share of bootstrap resamples (of PEOPLE, keeping each person's rows together) in which the new
    model's log-loss is lower than the old one's."""
    y = np.asarray(y, float)
    loss = lambda p: -(y * np.log(np.clip(p, 1e-5, 1)) + (1 - y) * np.log(np.clip(1 - p, 1e-5, 1)))
    lo, ln = loss(np.asarray(p_old, float)), loss(np.asarray(p_new, float))
    ids, inv = np.unique(np.asarray(people), return_inverse=True)
    per_old = np.bincount(inv, weights=lo, minlength=len(ids))
    per_new = np.bincount(inv, weights=ln, minlength=len(ids))
    rng = np.random.default_rng(seed)
    wins = 0
    for _ in range(int(resamples)):
        pick = rng.integers(0, len(ids), len(ids))
        wins += per_new[pick].sum() < per_old[pick].sum()
    return wins / float(resamples)


def evaluate(bundle, rows, resamples=None, seed=11, method=None, boot=AN.BOOT):
    """Fit the configured retraining method (ours), the other informed method and the naive model on the decision
    points, and check them and the champion on the untouched control group.
    Returns (metrics, our new live layer, its effects)."""
    method = method or METHOD
    other = "action_aware" if method.startswith("anchored") else "anchored_shrunk"
    y = rows["y"].to_numpy(dtype=int)
    users = rows["user_id"].to_numpy()
    z, S, Nm = arrays(bundle, rows)
    fold = person_folds(users)
    champion = bundle.get("live") or LM.empty_live()
    geo = AN.nba_geometry(rows)
    design = AN.designs(rows, y, geo, boot)
    fits = {m: _fit(m, z, S, y, Nm, design=design) for m in (method, other, "naive")}
    ours, effects, _ = fits[method]
    naive = fits["naive"][0]
    cv = crossfit_methods([method, other, "naive"], z, S, y, fold, Nm, rows, geo, boot)
    # rows a fold could not score (tiny data): use the full-data fits
    pred = {}
    for mm, (live_m, eff_m, _) in fits.items():
        a_m, s_m = cv[mm]
        a_m = np.where(np.isnan(a_m), _p(live_m, z, S, Nm, eff_m), a_m)
        s_m = np.where(np.isnan(s_m), _p(live_m, z, S, Nm, eff_m, keep=KEPT_COLS), s_m)
        pred[mm] = (a_m, s_m)
    a_ours, s_ours = pred[method]
    a_other, s_other = pred[other]
    a_naive = pred["naive"][0]
    a_champ = _p(champion, z, S, Nm, champion.get("own_effects") or {})
    m = {
        "retrain_method": method,
        "decision_points": int(len(rows)),
        "acted_on_share": float((Nm[:, : len(ACTION_COLS)].sum(1) > 0).mean()),
        "effects": effect_points(effects),
        "fixed_steps": sorted(
            (AN.control_betas(design) if method == "anchored_control" else AN.betas_from(design))
            if method.startswith("anchored")
            else []
        ),
        # what each signal is worth in each fit: the naive one also credits the signals with
        # the effect of the CRM's own emails/calls, ours has them as separate terms
        "points_ours": LM.learned_points({"live": ours}),
        "points_naive": LM.learned_points({"live": naive}),
        "design": design_summary(
            design, fits["action_aware"][1], effects if method.startswith("anchored") else None, method
        ),
        "chart": AN.jsonable(AN.chart(rows, y, geo)),
    }
    # what an ordinary dashboard sees: the score against all outcomes (shaped by our own actions)
    m.update(
        champion_live_auc=wauc(y, _p(champion, z, S)),
        challenger_live_auc=wauc(y, s_ours),
        naive_live_auc=wauc(y, a_naive),
        challenger_live_logloss=wlogloss(y, s_ours),
        naive_live_logloss=wlogloss(y, a_naive),
    )
    m[f"{_short(other)}_live_logloss"] = wlogloss(y, s_other)
    m[f"{_short(method)}_live_logloss"] = m["challenger_live_logloss"]
    m["naive_would_pick"] = int(m["naive_live_logloss"] < m["challenger_live_logloss"])
    # how much of acted-on leads' buying chance came from our own action
    did = Nm[:, : len(ACTION_COLS)].sum(1) > 0
    if did.any():
        pw = _p(ours, z, S, Nm, effects)[did]
        pn = _p(ours, z, S, Nm, effects, keep=KEPT_COLS)[did]
        m["own_effect_share"] = float(np.mean((pw - pn) / pw))
    else:
        m["own_effect_share"] = None
    # the honest check: the untouched control group
    ctl = rows[CONTROL_COL].to_numpy() > 0
    cy, cu = y[ctl], users[ctl]
    m["control_rows"], m["control_people"], m["control_buyers"] = int(ctl.sum()), int(len(set(cu))), int(cy.sum())
    m["ok_slice"] = bool(
        m["control_people"] >= MIN_CONTROL_PEOPLE
        and cy.sum() >= MIN_SLICE_CLASS
        and (len(cy) - cy.sum()) >= MIN_SLICE_CLASS
    )
    if ctl.any():
        m.update(
            champion_true_logloss=wlogloss(cy, a_champ[ctl]),
            challenger_true_logloss=wlogloss(cy, a_ours[ctl]),
            naive_true_logloss=wlogloss(cy, a_naive[ctl]),
            champion_true_auc=wauc(cy, a_champ[ctl]),
            challenger_true_auc=wauc(cy, a_ours[ctl]),
            naive_true_auc=wauc(cy, a_naive[ctl]),
        )
        m[f"{_short(method)}_true_logloss"] = m["challenger_true_logloss"]
        m[f"{_short(method)}_true_auc"] = m["challenger_true_auc"]
        m[f"{_short(other)}_true_logloss"] = wlogloss(cy, a_other[ctl])
        m[f"{_short(other)}_true_auc"] = wauc(cy, a_other[ctl])
        m["control_rate"] = float(cy.mean())
        m["control_predicted"] = {
            "champion": float(a_champ[ctl].mean()),
            "challenger": float(a_ours[ctl].mean()),
            "naive": float(a_naive[ctl].mean()),
            _short(method): float(a_ours[ctl].mean()),
            _short(other): float(a_other[ctl].mean()),
        }
        if m["ok_slice"]:
            r = resamples or CONF.get("bootstrap_resamples", 300)
            m["lead_prob_better"] = prob_better(cy, cu, a_champ[ctl], a_ours[ctl], r, seed)
            m["naive_prob_better"] = prob_better(cy, cu, a_naive[ctl], a_ours[ctl], r, seed + 1)
            m["other_prob_better"] = prob_better(cy, cu, a_other[ctl], a_ours[ctl], r, seed + 2)
    return m, ours, effects


def _short(method):
    """Column-name stem of a method: anchored (either anchored variant) | aware."""
    return "anchored" if method.startswith("anchored") else "aware"


# next-best-action retraining (decision log, inverse-propensity weights)
def _ml_modules():
    from app.ml.training import uplift as U
    from app.simulation import effects as S
    from app.simulation import population as G

    return G, S, U


def _prior():
    """Simulated randomized campaign used as the prior next to the logged decisions (cached)."""
    if "prior" not in _prior_cache:
        G, S, _ = _ml_modules()
        raw = G.generate(60000, seed=2024, return_truth=True)
        pf, pa, _, py, _ = S.simulate_randomized_campaign(raw, seed=11)
        _prior_cache["prior"] = (pf, pa, py)
    return _prior_cache["prior"]


def _decision_log(con, as_of):
    purchases = _read(con, "SELECT user_id, purchased_at FROM purchases WHERE purchased_at <= ?", (as_of,))
    # only the logging policy's own decisions (model or random): hand-made steps ("Do it now" on the lead
    # page, policy='manual') were not drawn from it, so they would bias the inverse-propensity weights
    d = _read(
        con,
        """SELECT id, user_id, action, propensity, base_probability, price, features_json,
                             created_at AS t FROM nba_decisions WHERE propensity > 0
                         AND COALESCE(policy,'') NOT IN ('holdout', 'manual') AND created_at <= ?""",
        (as_of,),
    )
    if d.empty:
        return d
    d["y"], d["matured"], d["customer"] = _outcomes(d, "t", purchases, as_of)
    return d[(~d["customer"]) & d["matured"]].reset_index(drop=True)


def _snips_terms(model, frame, base_p, actions, props, y, price):
    """Per-decision (weight, weighted profit) of the model's greedy policy (self-normalised IPS)."""
    _, _, U = _ml_modules()
    pred = U.predict_all(model, frame, base_p)
    greedy = U.greedy_policy(pred, price, U.blocked_matrix(frame), capacity=1.0)
    w = (greedy == actions) / np.clip(props, 1e-3, None)
    disc = np.array([N.ACTIONS[a]["discount"] for a in actions])
    cost = np.array([N.ACTIONS[a]["cost_inr"] for a in actions])
    profit = y * price * (1 - disc) - cost
    return w, w * profit


def retrain_nba(con, as_of, lead_bundle, dry_run=False):
    """Retrain the uplift model from the decision log; swap only on a clear (95%) gain."""
    _, _, U = _ml_modules()
    log = _decision_log(con, as_of)
    out = {"decisions_with_outcome": int(len(log))}
    if len(log) < MIN_NBA_DECISIONS:
        out.update(
            decision="not_enough_data",
            note=f"{len(log)} decisions with a known outcome; at least {MIN_NBA_DECISIONS} needed.",
        )
        return out
    pf, pa, py = _prior()
    pb = LM.predict_proba(lead_bundle, pf)
    rf = F.to_model_frame(_parse_features(log["features_json"]))
    rb = log["base_probability"].to_numpy(dtype=float)
    ra, ry = log["action"].to_numpy(), log["y"].to_numpy()
    rp, rprice = log["propensity"].to_numpy(dtype=float), log["price"].to_numpy(dtype=float)
    users = log["user_id"].unique()
    rng = np.random.default_rng(3)
    test_users = set(rng.choice(users, size=max(1, len(users) // 3), replace=False))
    t = log["user_id"].isin(test_users).to_numpy()
    X_frame = pd.concat([pf, rf[~t]], ignore_index=True)
    X_base = np.concatenate([pb, rb[~t]])
    X_act = np.concatenate([pa, ra[~t]])
    y = np.concatenate([py, ry[~t]])
    w = np.concatenate([np.ones(len(py)), REAL_WEIGHT_NBA * np.clip(1 / rp[~t], 1, 20)])
    challengers = {
        "interpretable S-learner": U.fit_uplift(X_frame, X_base, X_act, y, weights=w),
        "flexible S-learner (GBM)": U.fit_flexible(X_frame, X_act, y, weights=w),
    }
    old = joblib.load(NBA_PATH) if os.path.exists(NBA_PATH) else {}
    champion = old.get("model")
    held = (rf[t].reset_index(drop=True), rb[t], ra[t], rp[t], ry[t], rprice[t])
    if champion is None:
        cw, cv = np.ones(int(t.sum())), np.zeros(int(t.sum()))
    else:
        cw, cv = _snips_terms(champion, *held)
    scores, gains = {}, {}
    brng = np.random.default_rng(17)
    n = int(t.sum())
    for name, m in challengers.items():
        hw, hv = _snips_terms(m, *held)
        scores[name] = float(hv.sum() / hw.sum()) if hw.sum() else float("-inf")
        diffs = []
        for _ in range(int(CONF.get("bootstrap_resamples", 300))):
            idx = brng.integers(0, n, n)
            a, b = hw[idx].sum(), cw[idx].sum()
            if a > 0 and b > 0:
                diffs.append(hv[idx].sum() / a - cv[idx].sum() / b)
        gains[name] = (float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))) if diffs else (None, None)
    champ_score = float(cv.sum() / cw.sum()) if champion is not None and cw.sum() else None
    best = max(scores, key=scores.get)
    lo, hi = gains[best]
    swap = champion is None or (lo is not None and lo > 0)
    out.update(
        champion=N.model_label(champion) if champion is not None else None,
        champion_profit_per_lead=champ_score,
        challenger_profit_per_lead=scores,
        best_challenger=best,
        gain_ci95=[lo, hi],
        held_out_decisions=n,
        decision="swapped" if swap else "kept",
        note=(
            f"{best} chooses better steps than the current model on decisions it has not seen (in 95% of "
            "resamples), so it replaces it."
            if swap and lo is not None
            else f"No new model chooses clearly better steps on decisions it has not seen (best: {best}), so the "
            "current one stays."
            if lo is not None
            else "Too few matching held-out decisions to compare."
        ),
    )
    if swap and not dry_run:
        if os.path.exists(NBA_PATH):
            shutil.copy2(NBA_PATH, NBA_PATH.replace(".pkl", ".previous.pkl"))
        model = challengers[best]
        version = dt.datetime.now().strftime("nba-%Y%m%d-%H%M%S")
        bundle = {
            **{k: v for k, v in old.items() if k != "model"},
            "model": model,
            "kind": N.model_kind(model),
            "version": version,
            "trained_at": _ts(dt.datetime.now()),
            "learned_as_of": as_of,
            "trained_on": {"simulated_rows": int(len(py)), "real_rows": int((~t).sum())},
            "offpolicy_profit_per_lead": {"champion": champ_score, **scores},
        }
        tmp = NBA_PATH + ".tmp"
        joblib.dump(bundle, tmp)
        os.replace(tmp, NBA_PATH)
        try:
            card = {k: v for k, v in bundle.items() if k != "model"}
            with open(NBA_CARD_PATH, "w", encoding="utf-8") as f:
                json.dump(card, f, indent=2, default=str)
        except OSError:
            pass
        out["version_after"] = version
    return out


# 5./6. one run of the loop
def _load_lead_bundle():
    if not os.path.exists(LEAD_PATH):
        raise RuntimeError("No lead model yet: the first start trains it (python -m app.cli bootstrap).")
    b = joblib.load(LEAD_PATH)
    if "starter" not in b:
        raise RuntimeError("The lead model is from an older version: delete backend/data/models and restart.")
    return b


def _save_lead_bundle(bundle, live, effects, n_outcomes, run_id, as_of, method=None, fixed_steps=None):
    if os.path.exists(LEAD_PATH):
        shutil.copy2(LEAD_PATH, LEAD_PATH.replace(".pkl", ".previous.pkl"))
    new = dict(bundle)
    new["live"] = {
        **LM.empty_live(),
        **live,
        "own_effects": dict(effects or {}),
        "method": method or METHOD,
        "fixed_steps": list(fixed_steps or []),
        "outcomes_used": int(n_outcomes),
        "trained_at": _ts(dt.datetime.now()),
        "learned_as_of": as_of,
        "learning_run": run_id,
    }
    new["version"] = f"v7.1-live-{as_of[:10].replace('-', '')}-run{run_id}"
    new["trained_on"] = {**bundle.get("trained_on", {}), "history_outcomes": int(n_outcomes)}
    tmp = LEAD_PATH + ".tmp"
    joblib.dump(new, tmp)
    os.replace(tmp, LEAD_PATH)
    try:
        card = {k: v for k, v in new.items() if k not in ("starter",)}
        card["learned_signals"] = LM.learned_points(new)
        card["own_effects"] = effect_points(new["live"].get("own_effects"))
        with open(CARD_PATH, "w", encoding="utf-8") as f:
            json.dump(card, f, indent=2, default=str)
    except OSError:
        pass
    try:
        from app.ml import predict

        predict.reload()
    except Exception:  # noqa: BLE001 - the new model file is picked up on the next request anyway
        log.warning("The new lead model is saved but could not be loaded at once", exc_info=True)
    return new["version"]


def last_run():
    return db.fetchone("SELECT * FROM learning_runs WHERE status='done' ORDER BY id DESC LIMIT 1")


def count_outcomes(as_of=None):
    """How many decision points have a known outcome now (cheap enough to check every few minutes)."""
    as_of = as_of or _ts(dt.datetime.now())
    con = db.get_conn()
    try:
        return int(len(assemble(con, as_of)))
    finally:
        con.close()


def due(as_of=None):
    """Enough new outcomes since the last run?"""
    n = count_outcomes(as_of)
    last = last_run()
    new = n - int(last["outcomes_known"] or 0) if last else n
    return new >= int(CONF.get("min_new_outcomes", 30)), n, new


def run(as_of=None, reason="manual", force=True, dry_run=False, simulated=False, with_nba=True, verbose=True):
    """One pass of the learning loop. Returns a summary dict (also stored in learning_runs)."""
    say = log.info if verbose else (lambda *a, **k: None)
    if not _run_lock.acquire(blocking=False):
        return {"status": "busy", "message": "A learning run is already in progress."}
    try:
        as_of = as_of or _ts(dt.datetime.now())
        con = db.get_conn()
        try:
            rows = assemble(con, as_of)
            n_known = int(len(rows))
            last = last_run()
            new = n_known - int(last["outcomes_known"] or 0) if last else n_known
            if not force and new < int(CONF.get("min_new_outcomes", 30)):
                return {
                    "status": "skipped",
                    "outcomes_known": n_known,
                    "new_outcomes": new,
                    "message": f"{new} new outcome(s) since the last run; waiting for "
                    f"{CONF.get('min_new_outcomes', 30)}.",
                }
            if last and new <= 0 and not dry_run and not simulated:
                # pressing "Retrain now" again with nothing new would only repeat the last run
                return {
                    "status": "nothing_new",
                    "outcomes_known": n_known,
                    "new_outcomes": 0,
                    "last_run_id": last["id"],
                    "last_run_at": last.get("finished_at"),
                    "message": f"Nothing new since run {last['id']}: no new outcomes are known yet, so the result "
                    f"would be the same. The loop runs by itself when "
                    f"{CONF.get('min_new_outcomes', 30)} new outcomes are known.",
                }
            bundle = _load_lead_bundle()
            try:
                nba_before = joblib.load(NBA_PATH).get("version") if os.path.exists(NBA_PATH) else None
            except Exception:  # noqa: BLE001 - an unreadable file counts as no model before
                nba_before = None
            res = {
                "as_of": as_of,
                "reason": reason,
                "outcomes_known": n_known,
                "new_outcomes": new,
                "control_rows": 0,
                "control_buyers": 0,
                "lead_version_before": bundle.get("version"),
            }
            new_live = effects = None
            if n_known < 20 or rows["y"].nunique() < 2:
                res.update(
                    lead_decision="not_enough_data",
                    note=f"Only {n_known} decision(s) with a known outcome so far: nothing to learn from yet.",
                )
            else:
                m, new_live, effects = evaluate(bundle, rows)
                res.update(m)
                need = float(CONF.get("swap_confidence", 0.9))
                if not m["ok_slice"]:
                    res.update(
                        lead_decision="not_enough_data",
                        note=f"Only {m['control_people']} people of the untouched control group have a known "
                        f"outcome (need {MIN_CONTROL_PEOPLE}, with {MIN_SLICE_CLASS}+ buyers and non-buyers)"
                        f"; keeping the current model.",
                    )
                elif m["lead_prob_better"] >= need:
                    res.update(
                        lead_decision="swapped",
                        note=f"The new model predicts the untouched control group better in "
                        f"{m['lead_prob_better']:.0%} of resamples (needed {need:.0%}): swapped.",
                    )
                else:
                    res.update(
                        lead_decision="kept",
                        note=f"The new model is better on the control group in only "
                        f"{m['lead_prob_better']:.0%} of resamples (needs {need:.0%}): keeping the current model.",
                    )
            # next-best-action model
            if with_nba:
                try:
                    lead_for_nba = bundle
                    if res.get("lead_decision") == "swapped":
                        lead_for_nba = {**bundle, "live": {**LM.empty_live(), **new_live}}
                    res["nba"] = retrain_nba(con, as_of, lead_for_nba, dry_run=dry_run)
                except Exception as e:  # noqa: BLE001 - the uplift part must never break the loop
                    res["nba"] = {"decision": "error", "note": str(e)}
            else:
                res["nba"] = {"decision": "skipped"}
        finally:
            con.close()

        if dry_run:
            res["status"] = "dry_run"
            return res

        run_id = db.execute(
            """INSERT INTO learning_runs (started_at, as_of, reason, status, simulated)
                               VALUES (?,?,?,?,?)""",
            (as_of if simulated else _ts(dt.datetime.now()), as_of, reason, "running", int(simulated)),
        )
        lead_after = res.get("lead_version_before")
        if res.get("lead_decision") == "swapped" and new_live is not None:
            lead_after = _save_lead_bundle(
                bundle, new_live, effects, n_known, run_id, as_of, res.get("retrain_method"), res.get("fixed_steps")
            )
        cur = _load_lead_bundle()
        learned = {
            "points": LM.learned_points(cur),
            "slope": round(float(cur["live"].get("slope", 1.0)), 3),
            "intercept": round(float(cur["live"].get("intercept", 0.0)), 3),
            "outcomes_used": int(cur["live"].get("outcomes_used", 0)),
            "own_effects": effect_points(cur["live"].get("own_effects")),
            "control": {
                "rows": res.get("control_rows"),
                "people": res.get("control_people"),
                "buyers": res.get("control_buyers"),
                "actual": res.get("control_rate"),
                "predicted": res.get("control_predicted"),
                "naive_prob_better": res.get("naive_prob_better"),
                "other_prob_better": res.get("other_prob_better"),
            },
            "retrain_method": res.get("retrain_method"),
            "method_in_use": cur["live"].get("method"),
            "fixed_steps": res.get("fixed_steps"),
            "acted_on_share": res.get("acted_on_share"),
            "challenger_points": res.get("points_ours"),
            "naive_points": res.get("points_naive"),
        }
        nba = res.get("nba") or {}
        db.execute(
            """UPDATE learning_runs SET finished_at=?, status='done', outcomes_known=?, new_outcomes=?,
                      random_slice=?, random_slice_buyers=?, lead_decision=?, lead_prob_better=?,
                      champion_true_logloss=?, challenger_true_logloss=?, naive_true_logloss=?,
                      champion_true_auc=?, challenger_true_auc=?, naive_true_auc=?,
                      champion_live_auc=?, challenger_live_auc=?, naive_live_auc=?,
                      challenger_live_logloss=?, naive_live_logloss=?, naive_would_pick=?, own_effect_share=?,
                      learned_json=?, nba_decision=?, nba_detail_json=?, lead_version_before=?, lead_version_after=?,
                      nba_version_before=?, nba_version_after=?, note=?, retrain_method=?,
                      anchored_true_logloss=?, anchored_true_auc=?, anchored_live_logloss=?,
                      aware_true_logloss=?, aware_true_auc=?, aware_live_logloss=?, design_json=? WHERE id=?""",
            (
                as_of if simulated else _ts(dt.datetime.now()),
                n_known,
                res["new_outcomes"],
                res.get("control_rows", 0),
                res.get("control_buyers", 0),
                res.get("lead_decision"),
                res.get("lead_prob_better"),
                res.get("champion_true_logloss"),
                res.get("challenger_true_logloss"),
                res.get("naive_true_logloss"),
                res.get("champion_true_auc"),
                res.get("challenger_true_auc"),
                res.get("naive_true_auc"),
                res.get("champion_live_auc"),
                res.get("challenger_live_auc"),
                res.get("naive_live_auc"),
                res.get("challenger_live_logloss"),
                res.get("naive_live_logloss"),
                res.get("naive_would_pick"),
                res.get("own_effect_share"),
                json.dumps(learned, default=str),
                nba.get("decision"),
                json.dumps(nba, default=str),
                res.get("lead_version_before"),
                lead_after,
                nba_before,
                nba.get("version_after") or nba_before,
                res.get("note"),
                res.get("retrain_method"),
                res.get("anchored_true_logloss"),
                res.get("anchored_true_auc"),
                res.get("anchored_live_logloss"),
                res.get("aware_true_logloss"),
                res.get("aware_true_auc"),
                res.get("aware_live_logloss"),
                json.dumps({"steps": res.get("design"), "chart": res.get("chart")}, default=str)
                if res.get("design") is not None
                else None,
                run_id,
            ),
        )
        res.update(status="done", run_id=run_id, lead_version_after=lead_after, learned=learned)
        if res.get("lead_decision") == "swapped" and not simulated:
            try:  # every lead's stored score now comes from the new model
                from app.services import scoring

                res["rescored"] = scoring.refresh_scores("model_update")
            except Exception as e:  # noqa: BLE001 - the scheduled refresh rescores everyone soon anyway
                log.warning("Score refresh after the model switch failed: %s", e)
        say(
            "Learning run %s as of %s: %s decisions with an outcome (%s new), %s untouched control people; "
            "lead model %s; next-best-action %s",
            run_id,
            as_of,
            n_known,
            res["new_outcomes"],
            res.get("control_people", 0),
            res.get("lead_decision"),
            nba.get("decision"),
        )
        return res
    finally:
        _run_lock.release()


def scheduled_job():
    """Called by the scheduler: run the loop only when enough new outcomes are known."""
    try:
        ok, n, new = due()
        if ok:
            run(reason="scheduled", force=True)
    except Exception as e:
        log.exception("Scheduled learning run failed: %s", e)
