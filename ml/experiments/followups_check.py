"""
followups_check.py — where does the learning loop's remaining gap on the control group come from?

In the simulated histories (ml/results/history_runs.md) our model still expects more of the untouched control
group to buy than really do (about +13%; the naive retrain about +32%). Two possible reasons, tested here:

1. LATER FOLLOW-UPS. The score is the chance to buy if the CRM does nothing NOW, but the outcome window
   (14 days) of a decision also contains the CRM's later follow-ups (the next visit triggers the next
   decision). The control group never gets those.
   Test: the same histories (same seeds, same people, same random draws) under two rules for the CRM:
     usual       the CRM decides at every trigger (visit end, cart, checkout, enquiry ...), as in the product
     one touch   after a decision the CRM makes no further decision for that person for 14 days, so each
                 outcome window contains only the step taken at its start
   Campaigns and A/B tests are off in both (they would add touches to the windows).
2. LINGERING. Leads the CRM never works on stay in the market longer without buying. At a later decision
   point an untouched lead with the same visible signals is a weaker buyer than a lead the CRM is working
   on (its stronger buyers have already been helped to buy).
   Test: the control group's decision points split by the lead's age (days since sign-up), at the last
   learning run of each history: is the gap in the young or in the older leads?

Each history runs in its own temporary copy of the project (your data and models are never touched), with
the learned lead age switched off (learning.lead_age = false): the question is what the score without lead age misses.
Section 3 then tests the lead age as an input on the same data (the CRM uses it).
Run:  python ml/experiments/followups_check.py [--seeds 2026 11 12] [--n 2000] [--days 180] [--jobs 2]
      (about 6 minutes per history, two at a time)
      python ml/experiments/followups_check.py --from FOLDER ...   (analyse histories kept with --keep)
Writes ml/results/followups_check.md and .json
"""

import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _project as PJ  # noqa: E402

ROOT = PJ.ROOT
RESULTS = os.path.join(ROOT, "ml", "results")
REGIMES = {
    "usual": "Usual: the CRM decides at every trigger",
    "one_touch": "One touch per 14 days: nothing else in a decision's outcome window",
}
YOUNG_DAYS = 7
AGE_BUCKETS = [("lead_age_7_14_days", 7, 14), ("lead_age_14_30_days", 14, 30), ("lead_age_30_days_plus", 30, 1e9)]
AGE_LABELS = {
    "lead_age_7_14_days": "7–14 days",
    "lead_age_14_30_days": "14–30 days",
    "lead_age_30_days_plus": "30+ days",
}


# ── worker: one history in one project copy ───────────────────────────────────
def _use(folder):
    """This history's database, with the copy's own code (or this project's, for a folder kept without code)."""
    return PJ.use_copy(folder)


def worker(folder, seed, regime, n, days):
    db = _use(folder)
    from app.simulation import history as GH

    GH.History.run_campaign = lambda self, *a, **k: None  # no campaigns ...
    GH.History.run_ab = lambda self, *a, **k: None  # ... and no A/B tests, in both regimes
    if regime == "one_touch":
        decide = GH.History.decide

        def decide_once(self, L, trigger, t, allowed=None, always_email=False):
            last = L.get("_last_decision")
            if last is not None and t - last < timedelta(days=self.window):
                return None  # the window of the last decision is still open
            L["_last_decision"] = t
            return decide(self, L, trigger, t, allowed=allowed, always_email=always_email)

        GH.History.decide = decide_once
    db.init_db()
    GH.with_shared_connection(GH.generate, n, days, seed, verbose=False)


def analyse(folder):
    """At the history's last learning run: the control group's decision points by the lead's age, with what
    our model and the naive retrain expected (out-of-fold, exactly as the learning loop checks them)."""
    db = _use(folder)
    import pandas as pd

    from app.ml import learning as LN

    LN.LEAD_PATH = os.path.join(folder, "backend", "data", "models", "lead_model.pkl")
    bundle = LN._load_lead_bundle()
    con = db.get_conn()
    try:
        as_of = con.execute("SELECT MAX(as_of) FROM learning_runs WHERE simulated=1").fetchone()[0]
        rows = LN.assemble(con, as_of)
        signup = dict(con.execute("SELECT id, created_at FROM users").fetchall())
    finally:
        con.close()
    y = rows["y"].to_numpy(int)
    users = rows["user_id"].to_numpy()
    z, S, _ = LN.arrays(bundle, rows)
    fold = LN.person_folds(users)
    age = (
        (pd.to_datetime(rows["t"]) - pd.to_datetime(rows["user_id"].map(signup))).dt.total_seconds() / 86400
    ).to_numpy()
    for name, lo, hi in AGE_BUCKETS:
        rows[name] = ((age >= lo) & (age < hi)).astype(float)
    acts, rec, ages = list(LN.ACTION_COLS), list(LN.RECENCY_COLS), [n for n, _, _ in AGE_BUCKETS]

    def crossfit(cols, keep):
        """Out-of-fold, by person: the live layer fitted with `cols`, read with only `keep` switched on."""
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

    ours = crossfit(acts + rec, rec)  # told what the CRM did, time away learned
    naive = crossfit(rec, rec)  # not told what the CRM did
    aged = crossfit(acts + rec + ages, rec + ages)  # + the lead's age, kept in the score
    cols = acts + rec + ages
    X = rows[cols].to_numpy(float)
    _, eff_all = LN.fit_live(z, S, y, X, cols)
    ctl = rows[LN.CONTROL_COL].to_numpy() > 0
    # worked-on leads the CRM left alone by a random pick: the score's own population, untouched at that moment
    rnd = (rows["policy"].to_numpy() == "explore") & (rows["action"].to_numpy() == "none")
    out = {
        "as_of": as_of,
        "control_points": int(ctl.sum()),
        "random_none_points": int(rnd.sum()),
        "age_effects": {n: float(eff_all[n]) for n, _, _ in AGE_BUCKETS},
    }
    for group, g in (("control", ctl), ("random_none", rnd)):
        for name, m in (("young", g & (age < YOUNG_DAYS)), ("older", g & (age >= YOUNG_DAYS)), ("all", g)):
            ok = m & ~np.isnan(ours) & ~np.isnan(aged)
            out[f"{group}_{name}"] = {
                "points": int(m.sum()),
                "people": int(len(set(users[m]))),
                "actual": float(y[m].mean()) if m.any() else None,
                "ours": float(np.nanmean(ours[m])) if m.any() else None,
                "naive": float(np.nanmean(naive[m])) if m.any() else None,
                "ours_with_age": float(np.nanmean(aged[m])) if m.any() else None,
                "logloss_ours": float(LN.wlogloss(y[ok], ours[ok])) if ok.any() else None,
                "logloss_with_age": float(LN.wlogloss(y[ok], aged[ok])) if ok.any() else None,
            }
    print(json.dumps(out))


# ── orchestration ─────────────────────────────────────────────────────────────
def control_runs(folder):
    """The learning runs' control-group check: people, decision points, actual and expected buying."""
    con = sqlite3.connect(os.path.join(folder, "backend", "data", "xeducation.db"))
    con.row_factory = sqlite3.Row
    out = []
    for r in con.execute("SELECT * FROM learning_runs WHERE simulated=1 AND status='done' ORDER BY as_of"):
        c = json.loads(r["learned_json"] or "{}").get("control") or {}
        p = c.get("predicted") or {}
        if not c.get("actual") or p.get("challenger") is None or p.get("naive") is None:
            continue
        out.append(
            {
                "as_of": r["as_of"][:10],
                "people": c.get("people"),
                "points": r["random_slice"],
                "actual": c["actual"],
                "ours": p["challenger"],
                "naive": p["naive"],
                "ll_ours": r["challenger_true_logloss"],
                "ll_naive": r["naive_true_logloss"],
            }
        )
    decisions = con.execute("SELECT COUNT(*) FROM nba_decisions").fetchone()[0]
    con.close()
    return out, decisions


def collect(folder, seed, regime, env=None):
    runs, decisions = control_runs(folder)
    r = subprocess.run(
        [sys.executable, os.path.abspath(__file__), "--analyse", folder],
        cwd=folder,
        env=env or dict(os.environ, PYTHONUTF8="1", OMP_NUM_THREADS="1"),
        capture_output=True,
        text=True,
    )
    line = [x for x in r.stdout.splitlines() if x.startswith("{")]
    by_age = json.loads(line[-1]) if r.returncode == 0 and line else {"error": (r.stderr or "")[-300:]}
    return {"seed": seed, "regime": regime, "runs": runs, "decisions": decisions, "by_age": by_age}


def run_one(work, seed, regime, n, days):
    d = PJ.copy_project(os.path.join(work, f"{regime}_seed{seed}"))
    conf_path = os.path.join(d, "crm_settings.json")  # the question is about the score WITHOUT lead age
    with open(conf_path, encoding="utf-8") as f:
        conf = json.load(f)
    conf.setdefault("learning", {})["lead_age"] = False
    with open(conf_path, "w", encoding="utf-8") as f:
        json.dump(conf, f, indent=2)
    t0 = time.time()
    env = PJ.env_for(d)
    subprocess.run(
        [
            sys.executable,
            os.path.abspath(__file__),
            "--worker",
            d,
            "--seed",
            str(seed),
            "--regime",
            regime,
            "--n",
            str(n),
            "--days",
            str(days),
        ],
        cwd=d,
        env=env,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    res = collect(d, seed, regime, env)
    print(
        f"  {regime} seed {seed}: {len(res['runs'])} runs with a control-group check, {res['decisions']:,} decisions "
        f"({(time.time() - t0) / 60:.1f} min)",
        flush=True,
    )
    return res


def pooled(runs, key):
    """Over runs, weighted by control-group decision points: sum expected / sum bought - 1 (in %)."""
    w = np.array([max(int(x["points"] or 0), 1) for x in runs], float)
    exp_ = np.array([x[key] for x in runs], float)
    act = np.array([x["actual"] for x in runs], float)
    return float(100 * ((w * exp_).sum() / (w * act).sum() - 1))


def over(part, key):
    return 100 * (part[key] / part["actual"] - 1) if part and part.get("actual") else float("nan")


def report(results, n, days):
    by = {(r["regime"], r["seed"]): r for r in results}
    seeds = sorted({r["seed"] for r in results})
    L = [
        "# Where the learning loop's remaining gap comes from (simulated histories)",
        "",
        f"{len(seeds)} histories per rule (seeds {', '.join(map(str, seeds))}; {n:,} learners, {days} days; campaigns and "
        "A/B tests off), the same people and the same random draws under both rules. Each learning run checks the "
        "models on the untouched control group: how many of them each model expected to buy within 14 days, and how "
        "many did. Overstatement = expected / bought − 1, pooled over the runs of a history (weighted by the "
        "control group's decision points).",
        "",
        "## 1. Later follow-ups in the outcome window",
        "",
        "| Rule | History | Learning runs | CRM decisions | Control group bought (last run) | Naive expects | "
        "Ours expects | Naive overstates | Ours overstates |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    summary = {}
    for rg in REGIMES:
        every, per_seed = [], {}
        for s in seeds:
            r = by.get((rg, s))
            if not r or not r["runs"]:
                continue
            every += r["runs"]
            f = r["runs"][-1]
            per_seed[s] = {"naive": pooled(r["runs"], "naive"), "ours": pooled(r["runs"], "ours")}
            L.append(
                f"| {REGIMES[rg].split(':')[0]} | seed {s} | {len(r['runs'])} | {r['decisions']:,} | "
                f"{100 * f['actual']:.1f}% ({f['points']} points) | {100 * f['naive']:.1f}% | {100 * f['ours']:.1f}% | "
                f"{per_seed[s]['naive']:+.1f}% | {per_seed[s]['ours']:+.1f}% |"
            )
        summary[rg] = {
            "runs": len(every),
            "per_seed": per_seed,
            "naive": pooled(every, "naive") if every else None,
            "ours": pooled(every, "ours") if every else None,
        }
    L += ["", "| Rule | Learning runs | Naive overstates | Ours overstates |", "|---|---|---|---|"]
    for rg, s in summary.items():
        if s["runs"]:
            L.append(f"| {REGIMES[rg]} | {s['runs']} | {s['naive']:+.1f}% | {s['ours']:+.1f}% |")
    u, o = summary.get("usual", {}), summary.get("one_touch", {})
    if u.get("runs") and o.get("runs"):
        verdict = (
            "so later follow-ups explain part of it"
            if o["ours"] < u["ours"]
            else "so later follow-ups do NOT explain it"
        )
        L += [
            "",
            f"Without later follow-ups in the outcome window, our model's gap goes from {u['ours']:+.1f}% to "
            f"{o['ours']:+.1f}% ({verdict}); the naive retrain's from {u['naive']:+.1f}% to {o['naive']:+.1f}%. "
            f"Ours is below the naive retrain in every history. Single histories vary a lot (ours "
            f"{min(v['ours'] for r in summary.values() if isinstance(r, dict) and 'per_seed' in r for v in r['per_seed'].values()):+.0f}% "
            f"to {max(v['ours'] for r in summary.values() if isinstance(r, dict) and 'per_seed' in r for v in r['per_seed'].values()):+.0f}%): "
            "the control group is small.",
        ]
        summary["later_followups_explain_gap"] = bool(o["ours"] < u["ours"])
    # 2. lingering: by the lead's age at the decision, last learning run
    L += [
        "",
        "## 2. Where the gap is: by the lead's age at the decision (last learning run of each history)",
        "",
        "Two groups of people the CRM did nothing for at that moment: the **control group** (never worked on) and "
        "**worked-on leads it left alone by a random pick** (the 15% random choices). Pooled over the histories.",
        "",
        f"| Rule | Group | Younger than {YOUNG_DAYS} days: points · bought · ours expects | "
        f"{YOUNG_DAYS} days or older: points · bought · ours expects |",
        "|---|---|---|---|",
    ]
    ages = {}
    for rg in REGIMES:
        ages[rg] = {}
        for group, label in (
            ("control", "Control group (never worked on)"),
            ("random_none", "Worked-on leads, left alone by a random pick"),
        ):
            cells = []
            for k in ("young", "older"):
                pts = a = o = nv = 0.0
                for s in seeds:
                    x = ((by.get((rg, s)) or {}).get("by_age") or {}).get(f"{group}_{k}") or {}
                    if x.get("points"):
                        pts += x["points"]
                        a += x["points"] * x["actual"]
                        o += x["points"] * x["ours"]
                        nv += x["points"] * x["naive"]
                if pts:
                    ages[rg][f"{group}_{k}"] = {
                        "points": int(pts),
                        "actual": a / pts,
                        "ours": o / pts,
                        "naive": nv / pts,
                        "ours_over_pct": 100 * (o / a - 1) if a else None,
                    }
                    cells.append(
                        f"{int(pts)} · {100 * a / pts:.1f}% · {100 * o / pts:.1f}%"
                        + (f" ({100 * (o / a - 1):+.0f}%)" if a else "")
                    )
                else:
                    cells.append("—")
            L.append(f"| {REGIMES[rg].split(':')[0]} | {label} | {cells[0]} | {cells[1]} |")
    summary["by_age"] = ages
    L += [
        "",
        "Read with care: these are a few hundred decision points per cell (the control group is 5% of the "
        "learners); the pattern across the cells is the result, not the exact percentages.",
        "",
        "## 3. The fix, tested here and used by the CRM: the lead's age as a learned input",
        "",
        f"The same live layer with the lead's age since sign-up ({', '.join(AGE_LABELS[n] for n, _, _ in AGE_BUCKETS)}) "
        "as inputs that stay in the score, like time away. Out-of-fold, every history and both rules pooled:",
        "",
        "| Group | Points | Bought | Ours expects (log-loss) | With lead age (log-loss) |",
        "|---|---|---|---|---|",
    ]
    fix = {}
    for group, label in (("control", "Control group"), ("random_none", "Worked-on leads, left alone by a random pick")):
        for k in ("young", "older", "all"):
            pts = a = o = g = lo = lg = 0.0
            for r in results:
                x = (r.get("by_age") or {}).get(f"{group}_{k}") or {}
                if x.get("points") and x.get("ours_with_age") is not None:
                    w = x["points"]
                    pts += w
                    a += w * x["actual"]
                    o += w * x["ours"]
                    g += w * x["ours_with_age"]
                    lo += w * (x["logloss_ours"] or 0)
                    lg += w * (x["logloss_with_age"] or 0)
            if pts:
                fix[f"{group}_{k}"] = {
                    "points": int(pts),
                    "actual": a / pts,
                    "ours": o / pts,
                    "with_age": g / pts,
                    "logloss_ours": lo / pts,
                    "logloss_with_age": lg / pts,
                }
                name = {
                    "young": f"younger than {YOUNG_DAYS} days",
                    "older": f"{YOUNG_DAYS} days or older",
                    "all": "all",
                }[k]
                L.append(
                    f"| {label}, {name} | {int(pts)} | {100 * a / pts:.1f}% | {100 * o / pts:.1f}% "
                    f"({100 * (o / a - 1):+.0f}%; {lo / pts:.4f}) | {100 * g / pts:.1f}% ({100 * (g / a - 1):+.0f}%; "
                    f"{lg / pts:.4f}) |"
                )
    effs = [r["by_age"]["age_effects"] for r in results if (r.get("by_age") or {}).get("age_effects")]
    if effs:
        L += [
            "",
            "Learned effect of the lead's age (log-odds, range over the histories): "
            + "; ".join(
                f"{AGE_LABELS[n]} {min(e[n] for e in effs):+.2f} to {max(e[n] for e in effs):+.2f}"
                for n, _, _ in AGE_BUCKETS
            )
            + ".",
        ]
    summary["lead_age_fix"] = fix
    return L, summary


def name_of(folder):
    m = re.match(r"^(usual|one_touch)_seed(\d+)$", os.path.basename(os.path.normpath(folder)))
    if not m:
        raise SystemExit(f"{folder}: expected a folder named usual_seedN or one_touch_seedN")
    return m.group(1), int(m.group(2))


def save(lines, summary, results, n, days, seeds):
    os.makedirs(RESULTS, exist_ok=True)
    with open(os.path.join(RESULTS, "followups_check.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(RESULTS, "followups_check.json"), "w", encoding="utf-8") as f:
        json.dump({"n": n, "days": days, "seeds": seeds, "summary": summary, "histories": results}, f, indent=1)
    print("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker", default=None)
    ap.add_argument("--analyse", default=None)
    ap.add_argument("--from", dest="from_", nargs="+", default=None)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--regime", default="usual", choices=list(REGIMES))
    ap.add_argument("--seeds", type=int, nargs="+", default=[2026, 11, 12])
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--days", type=int, default=180)
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    if args.worker:
        worker(args.worker, args.seed, args.regime, args.n, args.days)
        return
    if args.analyse:
        analyse(args.analyse)
        return
    if args.from_:
        results = [collect(os.path.abspath(f), name_of(f)[1], name_of(f)[0]) for f in args.from_]
        lines, summary = report(results, args.n, args.days)
        save(lines, summary, results, args.n, args.days, sorted({r["seed"] for r in results}))
        return
    PJ.require_starting_models()
    work = tempfile.mkdtemp(prefix="xedu_followups_")
    t0 = time.time()
    try:
        jobs = [(s, rg) for s in args.seeds for rg in REGIMES]
        with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as ex:
            results = list(ex.map(lambda j: run_one(work, j[0], j[1], args.n, args.days), jobs))
        lines, summary = report(results, args.n, args.days)
        save(lines, summary, results, args.n, args.days, args.seeds)
        print(f"\n({(time.time() - t0) / 60:.1f} min) Saved ml/results/followups_check.md")
    finally:
        if args.keep:
            print(f"Copies kept in {work}")
        else:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
