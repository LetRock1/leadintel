"""
E6: learned lead aging vs hand-set decay rules, on simulated histories made by the CRM itself.

The problem. A lead who has not bought after a week or more is a weaker buyer than the same signals say,
even right after a visit (people who browse for weeks without enrolling). ml/experiments/followups_check.py
found that this is where the learning loop's remaining over-prediction of the control group sits. CRMs
handle "stale leads" with decay rules set by hand:
  * HubSpot lead scoring: a score decays over time, e.g. "losing 25% or 50% of the score after one month";
  * Salesforce Account Engagement (Pardot): an automation rule such as "decay scores greater than 50 to 50
    if the last activity is more than 45 days ago" (inactivity).
The CRM instead LEARNS the effect of the lead's age (days since sign-up: 7-14, 14-30, 30+) from outcomes, next to
the CRM's own actions and time away, and the learning loop only adopts it if the untouched control group
confirms it.

The test. New 180-day histories (same seeds as ml/results/history_runs.md; campaigns and A/B tests on, as in
the product), each in its own temporary copy of the project. At the last learning run, on the people the
CRM did nothing for at that moment — the untouched control group and worked-on leads it left alone by a
random pick (the 15% random choices) — out-of-fold predictions of:
  no lead age           told what the CRM did, time away learned; no lead age
  + HubSpot-style decay that score x 0.75 for leads older than 30 days ("lose 25% after one month")
  + 50% decay           that score x 0.50 for leads older than 30 days
  + Pardot-style decay  that score capped at 40 (half of the 80 sales threshold) if the last activity was
                        more than 45 days ago
  ours                  the lead's age learned from outcomes (kept in the score)
  naive retrain         not told what the CRM did (how CRMs retrain)
Metrics: log-loss (a proper scoring rule: rewards ranking and honest probabilities at once), calibration
error by lead age (|expected − actual| in each age group, weighted), and the over-prediction of older leads.
95% intervals by a cluster bootstrap over people (pooled histories, each history resampled separately).

Run:  python ml/experiments/lead_age_check.py [--seeds 2026 11 12] [--jobs 2]    (about 20 minutes)
      python ml/experiments/lead_age_check.py --from FOLDER ...   (histories kept with --keep)
Writes ml/results/lead_age_check.md and .json
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _project as PJ  # noqa: E402

ROOT = PJ.ROOT
RESULTS = os.path.join(ROOT, "ml", "results")
METHODS = ["v64", "hubspot25", "hubspot50", "pardot", "ours", "naive"]
LABELS = {
    "v64": "Score without lead age",
    "hubspot25": "Hand-set decay: −25% after 30 days (HubSpot-style)",
    "hubspot50": "Hand-set decay: −50% after 30 days",
    "pardot": "Inactivity decay: cap at 40 after 45 days away (Pardot-style)",
    "ours": "**Lead age learned (ours)**",
    "naive": "Naive retrain (not told what the CRM did)",
}
AGE_GROUPS = [("< 7 days", 0, 7), ("7–14 days", 7, 14), ("14–30 days", 14, 30), ("30+ days", 30, 1e9)]
BOOT = 1000


# ── per history (runs with the copy's own code) ───────────────────────────────
def analyse(folder):
    db = PJ.use_copy(folder)
    from app.ml import lead_model as LM
    from app.ml import learning as LN

    LN.LEAD_PATH = os.path.join(folder, "backend", "data", "models", "lead_model.pkl")
    bundle = LN._load_lead_bundle()
    con = db.get_conn()
    try:
        as_of = con.execute("SELECT MAX(as_of) FROM learning_runs WHERE simulated=1").fetchone()[0]
        rows = LN.assemble(con, as_of)
        runs = [
            dict(r)
            for r in con.execute("""SELECT as_of, lead_decision, learned_json FROM learning_runs
                                                  WHERE simulated=1 AND status='done' ORDER BY as_of""")
        ]
    finally:
        con.close()
    y = rows["y"].to_numpy(int)
    users = rows["user_id"].to_numpy()
    z, S, _ = LN.arrays(bundle, rows)
    fold = LN.person_folds(users)
    actions = LN.ACTION_COLS
    recency = LN.RECENCY_COLS
    ages = [n for n, _, _ in LM.AGE_BUCKETS]

    def crossfit(cols, keep):
        X = rows[cols].to_numpy(float)
        out = np.full(len(y), np.nan)
        for k in range(LN.FOLDS):
            te, tr = fold == k, fold != k
            if not te.any() or len(np.unique(y[tr])) < 2:
                continue
            live, eff = LN.fit_live(z[tr], S[tr], y[tr], X[tr], cols)
            zz = LN._logit_base(live, z[te], S[te])
            for j, c in enumerate(cols):
                if c in keep:
                    zz = zz + eff[c] * X[te][:, j]
            out[te] = 1 / (1 + np.exp(-zz))
        return out

    age = rows["age_days"].to_numpy(float)
    away = rows["away_days"].to_numpy(float)
    p = {
        "v64": crossfit(actions + recency, recency),
        "ours": crossfit(actions + recency + ages, recency + ages),
        "naive": crossfit(recency + ages, recency + ages),
    }
    p["hubspot25"] = np.where(age >= 30, 0.75 * p["v64"], p["v64"])
    p["hubspot50"] = np.where(age >= 30, 0.50 * p["v64"], p["v64"])
    p["pardot"] = np.where(away > 45, np.minimum(p["v64"], 0.40), p["v64"])
    ctl = rows[LN.CONTROL_COL].to_numpy() > 0
    rnd = (rows["policy"].to_numpy() == "explore") & (rows["action"].to_numpy() == "none")
    keep = (ctl | rnd) & np.all([~np.isnan(p[m]) for m in METHODS], axis=0)
    learned = []
    for r in runs:
        L = json.loads(r["learned_json"] or "{}")
        c = L.get("control") or {}
        pr = c.get("predicted") or {}
        learned.append(
            {
                "as_of": r["as_of"][:10],
                "decision": r["lead_decision"],
                "actual": c.get("actual"),
                "ours": pr.get("challenger"),
                "naive": pr.get("naive"),
                "champion": pr.get("champion"),
                "points": c.get("rows") or 0,
                "age_effects": {
                    e["input"]: e["weight"]
                    for e in (L.get("own_effects") or [])
                    if str(e.get("input", "")).startswith("age_")
                },
            }
        )
    out = {
        "as_of": as_of,
        "rows": int(len(y)),
        "kept": int(keep.sum()),
        "group": np.where(ctl, "control", "random")[keep].tolist(),
        "user": users[keep].astype(int).tolist(),
        "y": y[keep].tolist(),
        "age": age[keep].round(3).tolist(),
        "away": away[keep].round(3).tolist(),
        "p": {m: p[m][keep].round(6).tolist() for m in METHODS},
        "runs": learned,
    }
    print(json.dumps(out))


# ── orchestration ─────────────────────────────────────────────────────────────
def run_history(work, seed, n, days):
    d = PJ.copy_project(os.path.join(work, f"seed{seed}"))
    env = PJ.env_for(d)
    t0 = time.time()
    PJ.run_history(d, n, days, seed)
    res = collect(d, seed, env)
    print(
        f"  history seed {seed}: {res['rows']:,} decision points, {res['kept']} judged "
        f"({(time.time() - t0) / 60:.1f} min)",
        flush=True,
    )
    return res


def collect(folder, seed, env=None):
    r = subprocess.run(
        [sys.executable, os.path.abspath(__file__), "--analyse", folder],
        cwd=folder,
        env=env or dict(os.environ, PYTHONUTF8="1", OMP_NUM_THREADS="1"),
        capture_output=True,
        text=True,
    )
    line = [x for x in r.stdout.splitlines() if x.startswith("{")]
    if r.returncode != 0 or not line:
        raise SystemExit(f"analysis failed for {folder}: {r.stderr[-800:]}")
    out = json.loads(line[-1])
    out["seed"] = seed
    return out


def logloss(y, p):
    p = np.clip(p, 1e-5, 1 - 1e-5)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def calib_by_age(y, p, age):
    """Weighted mean |expected − actual| over the lead-age groups, in percentage points."""
    tot, err = 0, 0.0
    for _, lo, hi in AGE_GROUPS:
        m = (age >= lo) & (age < hi)
        if m.sum():
            tot += m.sum()
            err += m.sum() * abs(p[m].mean() - y[m].mean())
    return 100 * err / max(tot, 1)


def summarise(H, mask_fn):
    """Pooled metrics over histories for the rows mask_fn(h) selects, with a cluster bootstrap over people."""
    parts = []
    for h in H:
        g = np.array(h["group"])
        m = mask_fn(g)
        if not m.any():
            continue
        parts.append(
            {
                "y": np.array(h["y"])[m],
                "age": np.array(h["age"])[m],
                "user": np.array(h["user"])[m],
                "p": {k: np.array(v)[m] for k, v in h["p"].items()},
            }
        )
    if not parts:
        return None
    y = np.concatenate([q["y"] for q in parts])
    age = np.concatenate([q["age"] for q in parts])
    P = {k: np.concatenate([q["p"][k] for q in parts]) for k in METHODS}
    res = {"rows": int(len(y)), "bought": float(y.mean()), "methods": {}}
    old = age >= 7
    for k in METHODS:
        res["methods"][k] = {
            "logloss": float(logloss(y, P[k]).mean()),
            "calib_by_age": calib_by_age(y, P[k], age),
            "expected": float(P[k].mean()),
            "older_over_pct": float(100 * (P[k][old].mean() / y[old].mean() - 1))
            if old.any() and y[old].mean()
            else None,
            "younger_over_pct": float(100 * (P[k][~old].mean() / y[~old].mean() - 1))
            if (~old).any() and y[~old].mean()
            else None,
        }
    # cluster bootstrap: resample people within each history; difference ours − method
    rng = np.random.default_rng(2026)
    diffs = {k: {"logloss": [], "calib": []} for k in METHODS if k != "ours"}
    members = []
    for q in parts:
        _, inv = np.unique(q["user"], return_inverse=True)
        members.append([np.flatnonzero(inv == j) for j in range(inv.max() + 1)])
    for _ in range(BOOT):
        ys, ages, ps = [], [], {k: [] for k in METHODS}
        for q, mem in zip(parts, members):
            pick = rng.integers(0, len(mem), len(mem))
            rows_ = np.concatenate([mem[j] for j in pick])
            ys.append(q["y"][rows_])
            ages.append(q["age"][rows_])
            for k in METHODS:
                ps[k].append(q["p"][k][rows_])
        yb, ab = np.concatenate(ys), np.concatenate(ages)
        pb = {k: np.concatenate(v) for k, v in ps.items()}
        lo_ours, ca_ours = logloss(yb, pb["ours"]).mean(), calib_by_age(yb, pb["ours"], ab)
        for k in diffs:
            diffs[k]["logloss"].append(logloss(yb, pb[k]).mean() - lo_ours)
            diffs[k]["calib"].append(calib_by_age(yb, pb[k], ab) - ca_ours)
    res["ours_better_by"] = {
        k: {
            "logloss": [
                float(np.mean(v["logloss"])),
                float(np.quantile(v["logloss"], 0.025)),
                float(np.quantile(v["logloss"], 0.975)),
            ],
            "calib": [
                float(np.mean(v["calib"])),
                float(np.quantile(v["calib"], 0.025)),
                float(np.quantile(v["calib"], 0.975)),
            ],
        }
        for k, v in diffs.items()
    }
    return res


def report(H, n, days):
    seeds = sorted(h["seed"] for h in H)
    L = [
        "# E6 Learned lead aging vs hand-set decay rules (simulated histories)",
        "",
        f"{len(H)} new histories (seeds {', '.join(map(str, seeds))}; {n:,} learners, {days} days; campaigns and A/B tests on, "
        "as in the product), made by the CRM's own code with lead aging switched on. Judged at the last learning run on "
        "people the CRM did nothing for at that moment, out-of-fold. Log-loss is a proper scoring rule (lower = better "
        "ranking AND more honest probabilities); calibration error by lead age = weighted mean |expected − actual| over "
        "the age groups (<7, 7–14, 14–30, 30+ days). Intervals: 95%, cluster bootstrap over people.",
        "",
    ]
    S = {}
    for key, label, fn in (
        ("control", "Untouched control group (never worked on)", lambda g: g == "control"),
        ("random", "Worked-on leads the CRM left alone by a random pick", lambda g: g == "random"),
        ("both", "Both together", lambda g: np.ones(len(g), bool)),
    ):
        s = summarise(H, fn)
        if not s:
            continue
        S[key] = s
        L += [
            f"## {label} ({s['rows']:,} decision points, {100 * s['bought']:.1f}% bought)",
            "",
            "| Score | Log-loss | Ours better by (log-loss) | Calibration error by age (points) | Ours better by | "
            "Over-predicts leads 7+ days old | Leads < 7 days |",
            "|---|---|---|---|---|---|---|",
        ]
        for k in METHODS:
            m = s["methods"][k]
            b = s["ours_better_by"].get(k)
            fmt_ci = lambda v, d: f"{v[0]:+.{d}f} [{v[1]:+.{d}f}, {v[2]:+.{d}f}]"
            L.append(
                f"| {LABELS[k]} | {m['logloss']:.4f} | {fmt_ci(b['logloss'], 4) if b else '—'} | "
                f"{m['calib_by_age']:.2f} | {fmt_ci(b['calib'], 2) if b else '—'} | "
                f"{m['older_over_pct']:+.0f}% | {m['younger_over_pct']:+.0f}% |"
            )
        L.append("")
    # what the product's own learning runs did
    L += [
        "## Inside the product: the learning runs of these histories",
        "",
        "| History | Run | Control group bought | Ours expects | Naive expects | Decision | Learned lead age (log-odds: 7–14 / 14–30 / 30+) |",
        "|---|---|---|---|---|---|---|",
    ]
    over_o, over_n, w = [], [], []
    for h in sorted(H, key=lambda h: h["seed"]):
        for r in h["runs"]:
            if r["actual"] is None or r["ours"] is None:
                continue
            ae = r["age_effects"]
            L.append(
                f"| seed {h['seed']} | {r['as_of']} | {100 * r['actual']:.1f}% | {100 * r['ours']:.1f}% | "
                f"{100 * (r['naive'] or 0):.1f}% | {r['decision']} | "
                + " / ".join(
                    f"{ae[k]:+.2f}" if k in ae else "—" for k in ("age_7_14_days", "age_14_30_days", "age_30_days_plus")
                )
                + " |"
            )
            over_o.append(r["ours"] / r["actual"] - 1)
            over_n.append((r["naive"] or 0) / r["actual"] - 1)
            w.append(max(r["points"], 1))
    if over_o:
        w = np.array(w, float)
        L += [
            "",
            f"Over all {len(over_o)} learning runs (weighted by control-group decision points): ours over-predicts the "
            f"control group by {100 * np.average(over_o, weights=w):+.1f}%, the naive retrain by "
            f"{100 * np.average(over_n, weights=w):+.1f}%. Swaps: "
            + ", ".join(
                f"seed {h['seed']} {sum(r['decision'] == 'swapped' for r in h['runs'])}"
                for h in sorted(H, key=lambda h: h["seed"])
            )
            + ".",
        ]
    return L, S


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--analyse", default=None)
    ap.add_argument("--from", dest="from_", nargs="+", default=None)
    ap.add_argument("--seeds", type=int, nargs="+", default=[2026, 11, 12])
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--days", type=int, default=180)
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    if args.analyse:
        analyse(args.analyse)
        return
    t0 = time.time()
    work = None
    try:
        if args.from_:
            H = []
            for f in args.from_:
                m = re.search(r"seed(\d+)", os.path.basename(os.path.normpath(f)))
                H.append(collect(os.path.abspath(f), int(m.group(1)) if m else 0))
        else:
            PJ.require_starting_models()
            work = tempfile.mkdtemp(prefix="xedu_leadage_")
            with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as ex:
                H = list(ex.map(lambda s: run_history(work, s, args.n, args.days), args.seeds))
        lines, S = report(H, args.n, args.days)
        os.makedirs(RESULTS, exist_ok=True)
        with open(os.path.join(RESULTS, "lead_age_check.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        with open(os.path.join(RESULTS, "lead_age_check.json"), "w", encoding="utf-8") as f:
            json.dump(
                {
                    "n": args.n,
                    "days": args.days,
                    "seeds": sorted(h["seed"] for h in H),
                    "summary": S,
                    "runs": {h["seed"]: h["runs"] for h in H},
                },
                f,
                indent=1,
            )
        print("\n".join(lines))
        print(f"\n({(time.time() - t0) / 60:.1f} min) Saved ml/results/lead_age_check.md")
    finally:
        if work and not args.keep:
            shutil.rmtree(work, ignore_errors=True)
        elif work:
            print(f"Copies kept in {work}")


if __name__ == "__main__":
    main()
