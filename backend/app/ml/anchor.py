"""
The anchored update: retrain the lead score on the CRM's own logs without learning the CRM's own outreach.

From the research kit feedback-bench v0.2 (feedbackbench/anchor.py; the method was frozen on 23 Oct 2026 before the
held-out datasets were run). ``threshold_lift``, ``random_lift``, ``combine``, ``design_lift`` and ``shrink`` are the
kit's estimators, unchanged; the rest of this module connects them to this CRM's decision log.

The problem. A score retrained on logged outcomes learns the chance to buy if left alone mixed with the CRM's own
effect. Telling the model what the CRM did (v7.0's retrain) separates the two only when the data can tell the CRM's
step apart from lead quality: when the CRM acts by a rule on its own numbers and little is left to chance, a learner
can hand the step's effect to the features instead (the kit's THEORY.md, R6), and the CRM's own accuracy checks cannot
show it.

The anchored update takes each step's effect from the design instead of the fit:

    logit P(buy | lead, step s) = g(lead) + beta_s          score = expit(g(lead)) ("if we do nothing now")

beta_s comes from what identifies it whatever the learner does:

  the CRM's own cut-off   next-best-action takes a step only when the best step is expected to add profit
                          (net extra profit r > 0, a call net of the price of a call slot). Leads just above and just
                          below r = 0 differ only in whether the CRM acted, and they cannot place themselves on either
                          side: the CRM computes r. The jump in buying at r = 0, over the jump in the share acted on, is
                          the step's lift (a fuzzy regression discontinuity). It needs no randomness at all.
  random leaving-alone    above the cut-off, leads acted on against leads left alone by chance (the untouched control
                          group and the random learning steps); campaigns and A/B tests against their hold-out or
                          control arms.

The estimates are combined by inverse variance, and the live layer of the lead model (app.ml.lead_model) is refitted
on every decision point with beta_s fixed as an offset, so the learner cannot move the CRM's own effect into the
features. The kit has one step; this CRM has six, so the same estimators run once per step (and once for "any step",
the kit's own setting, for comparison). A lead appears at several decision points, so standard errors come from
resampling people rather than rows.

What the CRM uses (learning.METHOD, "anchored_control"). The kit's setting has one
decision per lead. This CRM decides again at every trigger, so a lead it leaves alone now, below the line or by a
random "not now", is usually followed up at its next trigger inside the 14-day outcome window. The line and those
random picks then measure acting now against acting later, not against never (tests/test_anchored_update.py), while
the lead score is checked against leads that are never contacted. So by default each step's lift is the random
contrast with "left alone" meaning the never-contacted control group only (random_control, design_control below);
campaign and A/B hold-outs are left out for the same reason (those leads still get next-best-action's steps). Steps
without such a contrast are learned by the model as in v7.0. The kit's combinations stay available as "anchored" and
"anchored_shrunk"; ml/experiments/anchored_check.py (E8) compares them all on a group nothing learns from.
"""

from __future__ import annotations

import json
import math

import numpy as np

RD_FRAC = 0.40  # share of each side's logged leads used by the threshold estimate (fixed before the held-out data)
RD_MIN_SUPPORT = 3  # at least this many distinct score values on each side (discrete scores)
BOOT = 200  # person-level resamples for the standard errors
STEPS = ["email_info", "email_coupon_10", "email_coupon_20", "call", "whatsapp", "campaign"]
NBA_STEPS = STEPS[:-1]
POOLED = "any"  # "the CRM took some step": the kit's single-action setting


def _clip(p, eps=1e-4):
    return np.clip(np.asarray(p, float), eps, 1 - eps)


def expit(z):
    return 1 / (1 + np.exp(-np.asarray(z, float)))


def logit(p):
    p = _clip(p)
    return np.log(p / (1 - p))


# The kit's estimators (feedbackbench/anchor.py v0.2, unchanged)
def threshold_lift(d, y, p_below, p_above, frac=RD_FRAC, min_support=RD_MIN_SUPPORT, draws=400):
    """Fuzzy regression discontinuity at d = 0 (d = the CRM's score minus its cut-off; d >= 0 targeted): local linear
    fits of the outcome on d on each side over the nearest `frac` of that side's logged leads (widened to at least
    `min_support` distinct score values), heteroskedasticity-robust (HC1) variances. The jump in outcomes over the jump
    in contact share gives the lift at the cut-off; returns (log-odds lift, standard error)."""
    d, y = np.asarray(d, float), np.asarray(y, float)
    ok = np.isfinite(d)
    d, y = d[ok], y[ok]
    if p_above - p_below <= 0.05:
        return np.nan, np.nan
    sides = []
    for mask in (d < 0, d >= 0):
        dd, yy = np.abs(d[mask]), y[mask]
        if len(dd) < 50:
            return np.nan, np.nan
        vals = np.unique(dd)
        bw = max(np.quantile(dd, frac), vals[min(min_support, len(vals)) - 1])
        sel = dd <= bw
        x, t = dd[sel], yy[sel]
        if np.ptp(x) == 0:
            sides.append((t.mean(), t.var(ddof=1) / len(t)))
            continue
        A = np.column_stack([np.ones(len(x)), x])
        coef, *_ = np.linalg.lstsq(A, t, rcond=None)
        e = t - A @ coef
        inv = np.linalg.inv(A.T @ A)
        V = inv @ ((A * (e**2)[:, None]).T @ A) @ inv * len(t) / (len(t) - 2)
        sides.append((coef[0], V[0, 0]))
    (yb, vb), (ya, va) = sides

    def beta_of(ya_, yb_):
        tau = (ya_ - yb_) / (p_above - p_below)
        m0 = yb_ - p_below * tau
        return logit(np.clip(m0 + tau, 1e-4, 1 - 1e-4)) - logit(np.clip(m0, 1e-4, 1 - 1e-4))

    b = float(beta_of(np.array([ya]), np.array([yb]))[0])
    g = np.random.default_rng(0)
    sim = beta_of(ya + np.sqrt(va) * g.standard_normal(draws), yb + np.sqrt(vb) * g.standard_normal(draws))
    return b, float(np.std(sim))


def random_lift(top, a, y, min_rows=20):
    """Contacted vs left-alone leads above the cut-off, where leaving a lead alone is random (control group, random
    choices). Returns (log-odds lift, standard error), or nan when there are too few left-alone leads."""
    a, y = np.asarray(a), np.asarray(y, float)
    m1, m0 = top & (a == 1), top & (a == 0)
    if m0.sum() < min_rows or m1.sum() < min_rows:
        return np.nan, np.nan
    p1, p0 = y[m1].mean(), y[m0].mean()
    if min(p1, p0) <= 0 or max(p1, p0) >= 1:
        return np.nan, np.nan
    return (
        float(np.log(p1 / (1 - p1)) - np.log(p0 / (1 - p0))),
        float(np.sqrt(1 / (m1.sum() * p1 * (1 - p1)) + 1 / (m0.sum() * p0 * (1 - p0)))),
    )


def combine(*ests):
    """Inverse-variance combination of (estimate, standard error) pairs; ignores missing ones."""
    ok = [(b, s) for b, s in ests if np.isfinite(b) and np.isfinite(s) and s > 0]
    if not ok:
        return np.nan, np.nan
    w = np.array([1 / s**2 for _, s in ok])
    return float(np.sum(w * np.array([b for b, _ in ok])) / w.sum()), float(1 / np.sqrt(w.sum()))


def shrink(beta_model, beta_design, se_design):
    """Move the design-based lift toward the model's by how well they agree (plug-in minimum-MSE weight)."""
    if not np.isfinite(beta_design):
        return beta_model
    gap2 = (beta_model - beta_design) ** 2
    w = se_design**2 / (se_design**2 + max(gap2 - se_design**2, 0.0))
    return float(beta_design + w * (beta_model - beta_design))


def design_lift(d, a, y, pi1):
    """The design-based lift from a log: threshold discontinuity plus random leaving-alone above the cut-off.
    d: score minus the round's cut-off per logged lead (nan for leads logged before the CRM acted), a: contacted,
    y: outcome, pi1: the policy's contact probability per lead. Returns a dict of (estimate, se) pairs."""
    d = np.asarray(d, float)
    has = np.isfinite(d)
    below, above = has & (d < 0), has & (d >= 0)
    p_below = float(np.mean(pi1[below])) if below.any() else np.nan
    p_above = float(np.mean(pi1[above])) if above.any() else np.nan
    est = {
        "threshold": threshold_lift(d[has], y[has], p_below, p_above)
        if below.any() and above.any()
        else (np.nan, np.nan),
        "random": random_lift(above, a, y),
    }
    est["design"] = combine(est["threshold"], est["random"])
    return est


# This CRM's decision log
def _net(option: dict) -> float:
    """A step's extra profit as next-best-action compares it: a call net of the price of a call slot."""
    v = float(option.get("incremental_profit") or 0.0)
    if option.get("action") == "call" and option.get("slot_price") is not None:
        v -= float(option["slot_price"])
    return v


def geometry(options_json, policy, propensity, action, model_best) -> dict | None:
    """Where one logged next-best-action decision sits relative to the CRM's own cut-off.

    Returns None when the decision cannot be part of the threshold design (doing nothing was not an option, as at an
    enquiry; nothing but doing nothing was possible; a step chosen by hand). Otherwise:
      step      the step the CRM takes if it acts (the best allowed step other than doing nothing)
      r         that step's extra profit in rupees; next-best-action acts exactly when r > 0
      d         r shifted so that the kit's convention holds (targeted when d >= 0; r = 0 counts as not targeted)
      p_step    the logging policy's probability of taking `step` at this decision
      p_none    its probability of doing nothing
    The share of random learning steps is read back from the logged probability, so a change of the setting over
    time is handled."""
    if policy not in ("model", "explore", "holdout") or not options_json:
        return None
    opts = json.loads(options_json) if isinstance(options_json, str) else options_json
    allowed = [o for o in opts if not o.get("blocked")]
    names = [o["action"] for o in allowed]
    if "none" not in names:
        return None
    others = [o for o in allowed if o["action"] != "none"]
    if not others:
        return None
    best = others[0]
    for o in others[1:]:
        if _net(o) > _net(best):
            best = o
    r = _net(best)
    k = len(allowed)
    targeted = r > 0
    if policy == "holdout":
        p_step, p_none = 0.0, 1.0
    else:
        prop = float(propensity or 0.0)
        if action == model_best:
            eps = (1.0 - prop) * k / (k - 1) if k > 1 else 0.0
        else:
            eps = prop * k
        eps = float(min(max(eps, 0.0), 1.0))
        p_step = (1 - eps) * targeted + eps / k
        p_none = (1 - eps) * (not targeted) + eps / k
    d = r if targeted else min(r, 0.0) - 1e-9
    return {"step": best["action"], "r": r, "d": d, "p_step": p_step, "p_none": p_none, "k": k}


def nba_geometry(rows) -> list:
    """geometry() for every assembled decision point (None for campaign and A/B rows and for rows outside the
    threshold design)."""
    out = []
    for r in rows.itertuples(index=False):
        if getattr(r, "source", "") not in ("next-best-action", "control group"):
            out.append(None)
            continue
        out.append(geometry(r.options_json, r.policy, r.propensity, r.action, r.model_best))
    return out


def _boot_se(fn, people, idx_sets, boot=BOOT, seed=7):
    """Standard error of fn(selected row indices) by resampling people (a lead appears at several decision points).
    idx_sets: the row indices fn needs, as a list of arrays (all from the same rows)."""
    people = np.asarray(people)
    ids, inv = np.unique(people, return_inverse=True)
    by_person = [[] for _ in ids]
    for i, p in enumerate(inv):
        by_person[p].append(i)
    by_person = [np.array(v, dtype=int) for v in by_person]
    rng = np.random.default_rng(seed)
    sims = []
    for _ in range(boot):
        pick = rng.integers(0, len(ids), len(ids))
        rows = np.concatenate([by_person[p] for p in pick]) if len(pick) else np.array([], dtype=int)
        v = fn(rows)
        if np.isfinite(v):
            sims.append(v)
    if len(sims) < boot * 0.8:  # the estimate does not exist in too many resamples: treat it as unavailable
        return np.nan
    return float(np.std(sims, ddof=1))


def _threshold_point(d, y, pi):
    """The kit's threshold estimate (point only), with the contact shares on each side from the policy."""
    below, above = d < 0, d >= 0
    if not below.any() or not above.any():
        return np.nan
    return threshold_lift(d, y, float(np.mean(pi[below])), float(np.mean(pi[above])), draws=2)[0]


def _random_point(top, a, y):
    return random_lift(top, a, y)[0]


def _estimate(point_fn, people, n_rows, boot):
    b = point_fn(np.arange(n_rows))
    if not np.isfinite(b):
        return np.nan, np.nan
    se = _boot_se(point_fn, people, None, boot=boot)
    return (float(b), se) if np.isfinite(se) and se > 0 else (np.nan, np.nan)


def step_design(rows, y, geo, step, boot=BOOT) -> dict:
    """The design-based lift of one step (or of POOLED, any step) from the assembled decision points.

    rows: the learning loop's assembled frame (app.ml.learning.assemble); y: outcomes; geo: nba_geometry(rows).
    Threshold and random contrasts from next-best-action decisions where `step` was the step it would take, and, for
    the campaign email and the coupons, the random contrasts of campaigns and A/B tests against their own hold-out
    or control arm. Each is a (log-odds lift, standard error) pair; 'design' is their inverse-variance combination."""
    acts = rows["action"].to_numpy()
    users = rows["user_id"].to_numpy()
    never = (rows["policy"].to_numpy() == "holdout") if "policy" in rows.columns else np.zeros(len(rows), bool)
    y = np.asarray(y, float)
    out = {"step": step}
    # next-best-action: the CRM's own cut-off, and random leaving-alone above it
    sel, d, a, pi = [], [], [], []
    for i, g in enumerate(geo):
        if g is None:
            continue
        if step == POOLED:
            sel.append(i)
            d.append(g["d"])
            a.append(1.0 if acts[i] != "none" else 0.0)
            pi.append(1.0 - g["p_none"])
        elif g["step"] == step and acts[i] in (step, "none"):
            sel.append(i)
            d.append(g["d"])
            a.append(1.0 if acts[i] == step else 0.0)
            tot = g["p_step"] + g["p_none"]
            pi.append(g["p_step"] / tot if tot > 0 else 0.0)
    sel = np.array(sel, dtype=int)
    if len(sel):
        D, A, P, Y, U = np.array(d), np.array(a), np.array(pi), y[sel], users[sel]
        below, above = D < 0, D >= 0
        out["threshold"] = _estimate(lambda ix: _threshold_point(D[ix], Y[ix], P[ix]), U, len(sel), boot)
        out["random"] = _estimate(lambda ix: _random_point(D[ix] >= 0, A[ix], Y[ix]), U, len(sel), boot)
        # the same contrast with "left alone" meaning never contacted (the control group) only: a random
        # "not now" pick is usually followed up at the lead's next trigger, inside the outcome window
        NV = never[sel]
        keep = (A == 1) | NV
        out["random_control"] = _estimate(
            lambda ix: _random_point((D[ix] >= 0) & keep[ix], A[ix], Y[ix]), U, len(sel), boot
        )
        out["n_below"], out["n_above"] = int(below.sum()), int(above.sum())
        out["left_alone_above"] = int((above & (A == 0)).sum())
        out["share_below"] = float(P[below].mean()) if below.any() else None
        out["share_above"] = float(P[above].mean()) if above.any() else None
    else:
        out["threshold"] = out["random"] = out["random_control"] = (np.nan, np.nan)
        out["n_below"] = out["n_above"] = out["left_alone_above"] = 0
        out["share_below"] = out["share_above"] = None
    # campaigns and A/B tests: each one's sent arm against its own hold-out or control arm
    exp = []
    if "exp_key" in rows.columns:
        keys = rows["exp_key"].to_numpy()
        for key in sorted({k for k in keys if isinstance(k, str) and k}):
            m = keys == key
            if step == POOLED:
                treated = m & (acts != "none")
            elif step in ("campaign", "email_coupon_10", "email_coupon_20"):
                treated = m & (acts == step)
            else:
                continue
            ctl = m & (acts == "none")
            if treated.sum() < 20 or ctl.sum() < 20:
                continue
            ix = np.where(treated | ctl)[0]
            T, Yk, Uk = treated[ix].astype(float), y[ix], users[ix]
            e = _estimate(lambda j, T=T, Yk=Yk: _random_point(np.ones(len(j), bool), T[j], Yk[j]), Uk, len(ix), boot)
            if np.isfinite(e[0]):
                exp.append(e)
    out["experiments"] = combine(*exp) if exp else (np.nan, np.nan)
    out["experiments_n"] = len(exp)
    out["design"] = combine(out["threshold"], out["random"], out["experiments"])
    # against never-contacted leads only: campaign and A/B hold-outs keep getting next-best-action's steps, so like the
    # line and the random "not now" picks they measure acting now against acting later (tests/test_anchored_update.py)
    out["design_control"] = tuple(out["random_control"])
    return out


def designs(rows, y, geo=None, boot=BOOT) -> dict:
    """step_design for every step and for POOLED."""
    geo = nba_geometry(rows) if geo is None else geo
    return {s: step_design(rows, y, geo, s, boot) for s in STEPS + [POOLED]}


def betas_from(designs_: dict, steps=STEPS) -> dict:
    """{step: design-based log-odds lift} for the steps that have one."""
    out = {}
    for s in steps:
        b = (designs_.get(s) or {}).get("design", (np.nan, np.nan))[0]
        if b is not None and np.isfinite(b):
            out[s] = float(b)
    return out


def control_betas(designs_: dict, steps=STEPS) -> dict:
    """{step: lift against never-contacted leads} (acted on against the control group above the cut-off) for the
    steps that have one. With no control group there is none, and the model learns every step as in v7.0."""
    out = {}
    for s in steps:
        b = (designs_.get(s) or {}).get("design_control", (np.nan, np.nan))[0]
        if b is not None and np.isfinite(b):
            out[s] = float(b)
    return out


def shrunk_betas(designs_: dict, model_own: dict, steps=STEPS) -> dict:
    """The kit's shrunk variant, step by step: each design-based lift moved toward the model's own estimate of that
    step (v7.0's retrain on the same data) by how well they agree, given the design's standard error. A design
    estimate from a handful of leads (a large standard error) hardly moves the model's estimate; a precise one that
    disagrees with the model replaces it. Steps without a design-based lift are left out (the model learns them)."""
    out = {}
    for s in steps:
        b, se = (designs_.get(s) or {}).get("design", (np.nan, np.nan))
        m = (model_own or {}).get(s)
        if m is None or b is None or se is None or not (np.isfinite(b) and np.isfinite(se)):
            continue
        out[s] = shrink(float(m), float(b), float(se))
    return out


def chart(rows, y, geo, bins_per_side=6) -> dict | None:
    """The threshold check card: buying and the share acted on around the CRM's own cut-off (any step), in bins of
    equal size on each side within the kit's window, with the local linear fit on each side."""
    sel = [i for i, g in enumerate(geo) if g is not None]
    if len(sel) < 100:
        return None
    acts = rows["action"].to_numpy()
    r = np.array([geo[i]["r"] for i in sel])
    d = np.array([geo[i]["d"] for i in sel])
    a = np.array([1.0 if acts[i] != "none" else 0.0 for i in sel])
    yy = np.asarray(y, float)[sel]
    out = {"bins": [], "fits": []}
    for side, mask in (("below", d < 0), ("above", d >= 0)):
        if mask.sum() < 50:
            return None
        dd = np.abs(d[mask])
        vals = np.unique(dd)
        bw = max(np.quantile(dd, RD_FRAC), vals[min(RD_MIN_SUPPORT, len(vals)) - 1])
        win = mask & (np.abs(d) <= bw)
        rr, yw, aw = r[win], yy[win], a[win]
        order = np.argsort(rr)
        for chunk in np.array_split(order, min(bins_per_side, max(1, len(order) // 15))):
            if len(chunk) == 0:
                continue
            out["bins"].append(
                {
                    "side": side,
                    "r": float(np.mean(rr[chunk])),
                    "r_lo": float(np.min(rr[chunk])),
                    "r_hi": float(np.max(rr[chunk])),
                    "n": int(len(chunk)),
                    "bought": float(np.mean(yw[chunk])),
                    "acted": float(np.mean(aw[chunk])),
                }
            )
        x = np.abs(d[win])
        A = np.column_stack([np.ones(len(x)), x])
        coef, *_ = np.linalg.lstsq(A, yy[win], rcond=None)
        sign = -1.0 if side == "below" else 1.0
        out["fits"].append(
            {
                "side": side,
                "at_cutoff": float(coef[0]),
                "slope_per_rupee": float(sign * coef[1]),
                "window": float(sign * bw),
                "n": int(win.sum()),
            }
        )
    out["bins"].sort(key=lambda b: b["r"])
    return out


def jsonable(x):
    """nan and infinities become None (JSON has no nan); tuples become lists."""
    if isinstance(x, dict):
        return {k: jsonable(v) for k, v in x.items()}
    if isinstance(x, list | tuple):
        return [jsonable(v) for v in x]
    if isinstance(x, float | np.floating):
        v = float(x)
        return None if math.isnan(v) or math.isinf(v) else v
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x
