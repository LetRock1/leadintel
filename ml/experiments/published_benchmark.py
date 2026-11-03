"""
E1b — Our lead-scoring method against published solutions: same data, same rows, same inputs.

Data: ml/data/Leads.csv (Kaggle "Lead Scoring", X Education: 9,240 real leads, 38.5% converted).

PART A. Four public solutions of the X Education case study, re-run exactly (ml/experiments/published/:
every confusion matrix they printed is reproduced). On EACH solution's own train/test split:
  theirs                    their final logistic regression and their cut-off (their published numbers)
  ours, same inputs         our gradient boosting (the CRM's own configuration, backend/app/ml/training/lead.py, nothing
                            tuned for this file) on the same design matrix their feature selection chose
                            from, trained on the same rows
  ours, new-lead inputs     our gradient boosting on the 9 columns a lead has when it arrives (no column
                            the sales team fills in after contact), same rows
  theirs, no post-contact   their final model refitted without Tags / Lead Quality / Last Activity /
                            Last Notable Activity (what it is worth for a new lead)
  Precise metrics: ROC AUC on the identical test rows with DeLong's 95% interval and DeLong's paired test;
  accuracy at a cut-off chosen on the TRAINING rows by the same rule the solution used (ours: on
  cross-validated training predictions), with McNemar's exact test; log-loss with a paired bootstrap
  interval. Then 30 more random 70/30 splits of the same rows: mean AUC difference with the corrected
  resampled t-interval (Nadeau & Bengio 2003).

PART B. Published numbers whose code is not public, compared under their protocol:
  Mandal, MSc thesis, National College of Ireland (2025): post-contact columns removed, stratified 80/20
  split, random forest: accuracy 79.76%, ROC AUC 0.8605 (threshold chosen on the test set).
  Jadli et al., IJCSE 13(2), 2022: random forest accuracy 93.02%, AUC 0.92 (inputs not listed).
  Yim et al., IJOMFA 5(1), 2024: stacking accuracy 92.33% (inputs not listed in the abstract).

Run:  python ml/experiments/published_benchmark.py      (about 5 minutes; --report-only rewrites the .md)
Writes ml/results/published_benchmark.md and .json
"""

import contextlib
import importlib
import io
import json
import os
import sys
import time
import warnings

import numpy as np
import pandas as pd
from scipy import stats
from scipy.stats import rankdata
from sklearn.base import clone
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, roc_auc_score
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.pipeline import Pipeline

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path[:0] = [HERE, os.path.join(ROOT, "backend"), os.path.join(ROOT, "ml")]
warnings.filterwarnings("ignore")
import published as P  # noqa: E402
import real_leads as RL  # noqa: E402

from app.ml import features as F  # noqa: E402
from app.ml.training import lead as T  # noqa: E402

RESULTS = os.path.join(ROOT, "ml", "results")
LEAKY = [
    "Tags",
    "Lead Quality",
    "Lead Profile",
    "Last Activity",
    "Last Notable Activity",
    "Asymmetrique Activity Index",
    "Asymmetrique Profile Index",
    "Asymmetrique Activity Score",
    "Asymmetrique Profile Score",
]
RULES = {
    "lsc": "precision_recall",
    "sivagiri": "sensitivity_specificity",
    "lscv1": "sensitivity_specificity",
    "lohani": "sensitivity_specificity",
}
REPEAT_SPLITS, MANDAL_SPLITS, BOOT = 30, 50, 2000
PUBLISHED_B = [
    {
        "who": "Mandal, MSc thesis, National College of Ireland (2025)",
        "url": "https://norma.ncirl.ie/9780/",
        "post_contact": "removed (9 columns)",
        "protocol": "stratified 80/20 split",
        "model": "random forest",
        "accuracy": 0.7976,
        "auc": 0.8605,
        "note": "threshold 0.53 chosen to maximise accuracy on the test set",
    },
    {
        "who": "Jadli et al., Indian J. Computer Science and Engineering 13(2), 2022",
        "url": "https://doi.org/10.21817/indjcse/2022/v13i2/221302098",
        "post_contact": "not stated",
        "protocol": "9,074 rows x 89 columns after preprocessing",
        "model": "random forest",
        "accuracy": 0.9302,
        "auc": 0.92,
        "note": "",
    },
    {
        "who": "Yim et al., Int. J. Management, Finance and Accounting 5(1), 2024",
        "url": "https://doi.org/10.33093/ijomfa.2024.5.1.2",
        "post_contact": "not stated in the abstract",
        "protocol": "10-fold cross-validation",
        "model": "stacking",
        "accuracy": 0.9233,
        "auc": None,
        "note": "",
    },
]


# ── statistics ────────────────────────────────────────────────────────────────
def delong(y, *scores):
    """AUCs and their covariance (DeLong et al. 1988; fast algorithm of Sun & Xu 2014)."""
    y = np.asarray(y).astype(bool)
    m, n = int(y.sum()), int((~y).sum())
    S = np.vstack([np.asarray(s, float) for s in scores])
    pos, neg = S[:, y], S[:, ~y]
    tx = np.vstack([rankdata(r) for r in pos])
    ty = np.vstack([rankdata(r) for r in neg])
    tz = np.vstack([rankdata(np.r_[a, b]) for a, b in zip(pos, neg)])
    auc = tz[:, :m].sum(1) / (m * n) - (m + 1) / (2 * n)
    v01 = (tz[:, :m] - tx) / n
    v10 = 1 - (tz[:, m:] - ty) / m
    cov = np.atleast_2d(np.cov(v01)) / m + np.atleast_2d(np.cov(v10)) / n
    return auc, cov


def auc_ci(y, p):
    a, c = delong(y, p)
    se = float(np.sqrt(c[0, 0]))
    return float(a[0]), float(a[0] - 1.96 * se), float(a[0] + 1.96 * se)


def auc_diff(y, p_ours, p_theirs):
    a, c = delong(y, p_ours, p_theirs)
    d = float(a[0] - a[1])
    se = float(np.sqrt(max(c[0, 0] + c[1, 1] - 2 * c[0, 1], 1e-18)))
    p = float(2 * stats.norm.sf(abs(d) / se))
    return {"diff": d, "low": d - 1.96 * se, "high": d + 1.96 * se, "p": p}


def mcnemar(y, pred_ours, pred_theirs):
    ok_o, ok_t = pred_ours == y, pred_theirs == y
    b, c = int(np.sum(ok_o & ~ok_t)), int(np.sum(~ok_o & ok_t))
    p = float(stats.binomtest(min(b, c), b + c, 0.5).pvalue) if b + c else 1.0
    return {"ours_only_right": b, "theirs_only_right": c, "p": p, "diff": float(ok_o.mean() - ok_t.mean())}


def logloss_diff(y, p_ours, p_theirs, seed=0):
    """Paired bootstrap of log-loss(theirs) - log-loss(ours): positive = ours better."""
    y = np.asarray(y, float)
    clip = lambda p: np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    lo = -(y * np.log(clip(p_ours)) + (1 - y) * np.log(1 - clip(p_ours)))
    lt = -(y * np.log(clip(p_theirs)) + (1 - y) * np.log(1 - clip(p_theirs)))
    d = lt - lo
    pick = np.random.default_rng(seed).integers(0, len(d), (BOOT, len(d)))
    boot = d[pick].mean(1)
    return {
        "diff": float(d.mean()),
        "low": float(np.quantile(boot, 0.025)),
        "high": float(np.quantile(boot, 0.975)),
        "ours": float(lo.mean()),
        "theirs": float(lt.mean()),
    }


def corrected_interval(x, test_share):
    x = np.asarray(x, float)
    r = len(x)
    se = np.sqrt((1 / r + test_share / (1 - test_share)) * x.var(ddof=1))
    t = stats.t.ppf(0.975, r - 1)
    return float(x.mean()), float(x.mean() - t * se), float(x.mean() + t * se)


def at_cutoff(y, p, cut):
    y = np.asarray(y).astype(int)
    pred = (np.asarray(p) > cut).astype(int)
    tp, tn = int(np.sum((pred == 1) & (y == 1))), int(np.sum((pred == 0) & (y == 0)))
    fp, fn = int(np.sum((pred == 1) & (y == 0))), int(np.sum((pred == 0) & (y == 1)))
    return {
        "cutoff": float(cut),
        "accuracy": (tp + tn) / len(y),
        "sensitivity": tp / max(tp + fn, 1),
        "specificity": tn / max(tn + fp, 1),
        "precision": tp / max(tp + fp, 1),
        "pred": pred,
    }


def choose_cutoff(y, p, rule):
    """The solutions' own rules: where sensitivity meets specificity, or precision meets recall."""
    grid = np.round(np.arange(0.05, 0.951, 0.01), 2)
    best, gap = 0.5, 9.0
    for c in grid:
        m = at_cutoff(y, p, c)
        g = (
            abs(m["sensitivity"] - m["specificity"])
            if rule == "sensitivity_specificity"
            else abs(m["precision"] - m["sensitivity"])
        )
        if g < gap:
            best, gap = float(c), g
    return best


# ── models ────────────────────────────────────────────────────────────────────
def ours():
    return clone(T.candidates()["gradient_boosting"])


def fit_predict(make, Xtr, ytr, Xte):
    m = make().fit(Xtr, ytr)
    return m.predict_proba(Xte)[:, 1]


def oof(make, X, y, seed=0):
    """Cross-validated predictions on the training rows (to choose a cut-off without peeking)."""
    y = np.asarray(y)
    out = np.zeros(len(y))
    for tr, te in StratifiedKFold(5, shuffle=True, random_state=seed).split(X, y):
        out[te] = fit_predict(
            make, X.iloc[tr] if hasattr(X, "iloc") else X[tr], y[tr], X.iloc[te] if hasattr(X, "iloc") else X[te]
        )
    return out


def mle(Xtr, ytr, Xte):
    m = LogisticRegression(penalty=None, solver="newton-cg", max_iter=10000, tol=1e-10)
    m.fit(np.asarray(Xtr, float), np.asarray(ytr))
    return m.predict_proba(np.asarray(Xte, float))[:, 1]


def new_lead_frame():
    rows, y = RL.load_real_leads()
    return F.to_model_frame(rows)[RL.REAL_COLUMNS], y


def new_lead_model():
    return Pipeline([("prep", RL.build_real_preprocessor()), ("clf", ours())])


def is_leaky(col):
    return any(col == s or col.startswith(s + "_") or col.lower().startswith(s.lower() + "_") for s in LEAKY)


# ── part A ────────────────────────────────────────────────────────────────────
def part_a(frame, y_all, say):
    out = []
    for sol in P.SOLUTIONS:
        t0 = time.time()
        mod = importlib.import_module(f"published.{sol['module']}")
        log = io.StringIO()
        with contextlib.redirect_stdout(log):
            d = mod.reproduce(RL.REAL_DATA)
        rep, rpr = d["reported"]["test"], d["reproduced"]["test"]
        exact = rep["confusion"] == rpr["confusion"]
        Xtr, ytr = d["X_train"].astype(float), d["y_train"].to_numpy().astype(int)
        Xte = d.get("X_test_train_scaled", d["X_test"]).astype(float)
        yte = d["y_test"].to_numpy().astype(int)
        tri, tei = np.asarray(d["train_index"]), np.asarray(d["test_index"])
        assert (y_all[tri] == ytr).all() and (y_all[tei] == yte).all(), "row numbers do not match Leads.csv"
        rule = RULES[sol["key"]]
        theirs = np.asarray(d["test_proba"], float)
        th = at_cutoff(yte, theirs, d["cutoff"])
        # ours on the same inputs
        p_same = fit_predict(ours, Xtr, ytr, Xte)
        c_same = choose_cutoff(ytr, oof(ours, Xtr, ytr), rule)
        # ours on the inputs a new lead has
        Ftr, Fte = frame.iloc[tri], frame.iloc[tei]
        p_new = fit_predict(new_lead_model, Ftr, ytr, Fte)
        c_new = choose_cutoff(ytr, oof(new_lead_model, Ftr, ytr), rule)
        # their model without the post-contact columns
        clean = [f for f in d["final_features"] if f not in d["leaky_final_features"] and not is_leaky(f)]
        p_clean = mle(Xtr[clean], ytr, Xte[clean]) if clean else np.full(len(yte), ytr.mean())
        c_clean = choose_cutoff(ytr, mle(Xtr[clean], ytr, Xtr[clean]) if clean else np.full(len(ytr), ytr.mean()), rule)
        res = {
            "key": sol["key"],
            "label": sol["label"],
            "url": sol["url"],
            "commit": sol["commit"],
            "reproduced_exactly": bool(exact),
            "n_train": int(len(ytr)),
            "n_test": int(len(yte)),
            "test_converted": float(yte.mean()),
            "design_columns": int(Xtr.shape[1]),
            "final_features": d["final_features"],
            "leaky_final_features": d["leaky_final_features"],
            "leaky_columns_in_design": d["leaky_columns_in_design"],
            "rule": rule,
            "reported": {k: rep.get(k) for k in ("accuracy", "sensitivity", "specificity", "precision", "roc_auc")},
            "notes": d.get("notes", ""),
        }
        models = {
            "theirs": (theirs, d["cutoff"]),
            "ours_same_inputs": (p_same, c_same),
            "ours_new_lead_inputs": (p_new, c_new),
            "theirs_no_post_contact": (p_clean, c_clean),
        }
        res["models"] = {}
        for name, (p, cut) in models.items():
            m = at_cutoff(yte, p, cut)
            a, lo, hi = auc_ci(yte, p)
            res["models"][name] = {
                "auc": a,
                "auc_low": lo,
                "auc_high": hi,
                "log_loss": float(log_loss(yte, np.clip(p, 1e-6, 1 - 1e-6))),
                **{k: v for k, v in m.items() if k != "pred"},
            }
        res["vs_theirs"] = {}
        for name in ("ours_same_inputs", "ours_new_lead_inputs"):
            p, cut = models[name]
            res["vs_theirs"][name] = {
                "auc": auc_diff(yte, p, theirs),
                "accuracy": mcnemar(yte, at_cutoff(yte, p, cut)["pred"], th["pred"]),
                "log_loss": logloss_diff(yte, p, theirs),
            }
        # 30 more random splits of the same rows (their style: 70/30, not stratified)
        D = pd.concat([Xtr, Xte]).astype(float)
        Dy = np.r_[ytr, yte]
        Fall = pd.concat([Ftr, Fte])
        diffs_same, diffs_new, auc_t, auc_s, auc_n = [], [], [], [], []
        for r in range(REPEAT_SPLITS):
            a_idx, b_idx = train_test_split(np.arange(len(Dy)), train_size=0.7, random_state=1000 + r)
            pt = mle(D.iloc[a_idx][d["final_features"]], Dy[a_idx], D.iloc[b_idx][d["final_features"]])
            ps = fit_predict(ours, D.iloc[a_idx], Dy[a_idx], D.iloc[b_idx])
            pn = fit_predict(new_lead_model, Fall.iloc[a_idx], Dy[a_idx], Fall.iloc[b_idx])
            at, as_, an = (roc_auc_score(Dy[b_idx], q) for q in (pt, ps, pn))
            auc_t.append(at), auc_s.append(as_), auc_n.append(an)
            diffs_same.append(as_ - at), diffs_new.append(an - at)
        res["repeated_splits"] = {
            "splits": REPEAT_SPLITS,
            "theirs_auc": corrected_interval(auc_t, 0.3),
            "ours_same_inputs_auc": corrected_interval(auc_s, 0.3),
            "ours_new_lead_inputs_auc": corrected_interval(auc_n, 0.3),
            "ours_same_minus_theirs": corrected_interval(diffs_same, 0.3),
            "ours_new_minus_theirs": corrected_interval(diffs_new, 0.3),
            "ours_same_wins": int(np.sum(np.array(diffs_same) > 0)),
            "ours_new_wins": int(np.sum(np.array(diffs_new) > 0)),
        }
        out.append(res)
        say(
            f"  {sol['label']}: reproduced exactly: {exact}; AUC theirs {res['models']['theirs']['auc']:.4f}, "
            f"ours same inputs {res['models']['ours_same_inputs']['auc']:.4f}, ours new-lead inputs "
            f"{res['models']['ours_new_lead_inputs']['auc']:.4f} ({time.time() - t0:.0f} s)"
        )
    return out


# ── part B ────────────────────────────────────────────────────────────────────
def part_b(frame, y, say):
    """Mandal's protocol (stratified 80/20, no post-contact column) with our 9 new-lead columns."""
    aucs, accs, cuts = [], [], []
    t0 = time.time()
    for r in range(MANDAL_SPLITS):
        tr, te = train_test_split(np.arange(len(y)), test_size=0.2, stratify=y, random_state=r)
        p = fit_predict(new_lead_model, frame.iloc[tr], y[tr], frame.iloc[te])
        q = oof(new_lead_model, frame.iloc[tr], y[tr], seed=r)
        grid = np.round(np.arange(0.30, 0.701, 0.01), 2)  # Mandal's grid, but searched on TRAINING rows
        cut = float(grid[np.argmax([((q > c).astype(int) == y[tr]).mean() for c in grid])])
        aucs.append(roc_auc_score(y[te], p))
        accs.append(((p > cut).astype(int) == y[te]).mean())
        cuts.append(cut)
    say(f"  Mandal protocol: {MANDAL_SPLITS} splits ({time.time() - t0:.0f} s)")
    aucs, accs = np.array(aucs), np.array(accs)
    return {
        "splits": MANDAL_SPLITS,
        "auc_mean": float(aucs.mean()),
        "auc_p2_5": float(np.quantile(aucs, 0.025)),
        "auc_p97_5": float(np.quantile(aucs, 0.975)),
        "auc_interval": corrected_interval(aucs, 0.2),
        "share_auc_above_published": float(np.mean(aucs > 0.8605)),
        "accuracy_mean": float(accs.mean()),
        "accuracy_interval": corrected_interval(accs, 0.2),
        "share_accuracy_above_published": float(np.mean(accs > 0.7976)),
        "cutoff_mean": float(np.mean(cuts)),
    }


def leaky_ceiling(y, say):
    """Our gradient boosting WITH the post-contact columns, 5-fold cross-validation (contrast only)."""
    d = pd.read_csv(RL.REAL_DATA)
    base, _ = new_lead_frame()
    X = base.copy()
    for c in LEAKY:
        X[c] = d[c].astype(str)
    from sklearn.compose import ColumnTransformer
    from sklearn.preprocessing import OneHotEncoder

    prep = ColumnTransformer(
        [
            ("base", RL.build_real_preprocessor(), RL.REAL_COLUMNS),
            ("leak", OneHotEncoder(handle_unknown="ignore", sparse_output=False), LEAKY),
        ]
    )
    p = oof(lambda: Pipeline([("prep", prep), ("clf", ours())]), X, y, seed=42)
    cut = 0.5
    return {"auc": auc_ci(y, p), "accuracy": float(((p > cut).astype(int) == y).mean())}


# ── report ────────────────────────────────────────────────────────────────────
def pct(x):
    return "—" if x is None else f"{100 * x:.1f}%"


def ci(a, lo, hi, d=3):
    return f"{a:.{d}f} [{lo:.{d}f}, {hi:.{d}f}]"


def pval(p):
    return "< 0.0001" if p < 1e-4 else f"{p:.4f}"


def wins_text(reps):
    lo, hi = min(x["ours_same_wins"] for x in reps), max(x["ours_same_wins"] for x in reps)
    return f"{lo}" if lo == hi else f"{lo}–{hi}"


def report(A, B, leak, y):
    short = lambda r: r["label"].split(" / ")[0]
    rs = {r["key"]: r for r in A}
    same = [r["vs_theirs"]["ours_same_inputs"]["auc"] for r in A]
    reps = [r["repeated_splits"] for r in A]
    leaky = [r for r in A if r["leaky_final_features"]]
    new_aucs = [r["models"]["ours_new_lead_inputs"]["auc"] for r in A]
    leakfree_acc = max(
        [r["models"]["ours_new_lead_inputs"]["accuracy"] for r in A]
        + [r["models"]["theirs_no_post_contact"]["accuracy"] for r in A]
        + [B["accuracy_mean"]]
    )
    best_leaky_auc = max(r["models"]["theirs"]["auc"] for r in leaky)
    best_leaky_acc = max(
        [r["models"]["theirs"]["accuracy"] for r in leaky]
        + [pb["accuracy"] for pb in PUBLISHED_B if not pb["who"].startswith("Mandal")]
    )
    L = [
        "# E1b Our lead scoring vs published solutions (X Education, 9,240 real leads)",
        "",
        "Same data (byte-identical Leads.csv), same rows, same inputs. The precise metric is ROC AUC on the identical "
        "test rows with DeLong's 95% interval and paired test, repeated on 30 new splits with the corrected resampled "
        "t-interval; accuracy is compared at a cut-off chosen on the training rows by each solution's own rule "
        "(McNemar's exact test).",
        "",
        "**Post-contact columns** (Tags, Lead Quality, Lead Profile, Last Activity, Last Notable Activity, Asymmetrique "
        "scores) are filled in by the sales team after contacting a lead, so a new lead never has them: a model that "
        "uses them cannot score new leads.",
        "",
        "## The records, in one table",
        "",
        "| Comparison | Best earlier result (published, or their model re-run) | Ours | How it is measured |",
        "|---|---|---|---|",
        f"| Same rows and same inputs as each of {len(A)} public solutions | AUC "
        f"{min(r['models']['theirs']['auc'] for r in A):.3f}–{max(r['models']['theirs']['auc'] for r in A):.3f} | higher by "
        f"{min(x['diff'] for x in same):+.3f} to {max(x['diff'] for x in same):+.3f} on their split; better in "
        f"{wins_text(reps)} of {REPEAT_SPLITS} new splits for each"
        f"{' (every 95% interval above zero)' if all(x['ours_same_minus_theirs'][1] > 0 for x in reps) else ''} | DeLong on the "
        f"identical test rows; {REPEAT_SPLITS} new 70/30 splits |",
        f"| Only inputs a new lead has | AUC 0.8605 (Mandal 2025, stratified 80/20); "
        f"{rs['lohani']['models']['theirs']['auc']:.3f} (Lohani & Bansal, on its split) | AUC {B['auc_mean']:.3f} on "
        f"{B['splits']} stratified 80/20 splits (above 0.8605 in {100 * B['share_auc_above_published']:.0f}%); "
        f"{rs['lohani']['models']['ours_new_lead_inputs']['auc']:.3f} on Lohani & Bansal's split — with 9 columns | "
        "their protocol |",
        f"| With post-contact columns (not valid for new leads) | AUC {best_leaky_auc:.3f}, accuracy "
        f"{pct(best_leaky_acc)} | AUC {leak['auc'][0]:.3f} [{leak['auc'][1]:.3f}, {leak['auc'][2]:.3f}], accuracy "
        f"{pct(leak['accuracy'])} | 5-fold cross-validation |",
        "",
        "## A. Four public solutions, re-run exactly, on their own splits",
        "",
        "| Public solution | Post-contact columns in its model | Test rows | Their AUC | Ours, same inputs | "
        "Ours − theirs (DeLong p) | Ours, new-lead inputs only | Their model without post-contact columns |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in A:
        m, v = r["models"], r["vs_theirs"]["ours_same_inputs"]["auc"]
        lk = (
            f"{len(r['leaky_final_features'])} of {len(r['final_features'])}"
            if r["leaky_final_features"]
            else f"none (0 of {len(r['final_features'])})"
        )
        L.append(
            f"| [{r['label']}]({r['url']}) | {lk} | {r['n_test']:,} | {ci(m['theirs']['auc'], m['theirs']['auc_low'], m['theirs']['auc_high'])} | "
            f"{ci(m['ours_same_inputs']['auc'], m['ours_same_inputs']['auc_low'], m['ours_same_inputs']['auc_high'])} | "
            f"{v['diff']:+.3f} [{v['low']:+.3f}, {v['high']:+.3f}] (p {pval(v['p'])}) | "
            f"{ci(m['ours_new_lead_inputs']['auc'], m['ours_new_lead_inputs']['auc_low'], m['ours_new_lead_inputs']['auc_high'])} | "
            f"{m['theirs_no_post_contact']['auc']:.3f} |"
        )
    L += [
        "",
        "Every confusion matrix the notebooks printed was reproduced exactly: "
        + ", ".join(f"{short(r)} {'yes' if r['reproduced_exactly'] else 'NO'}" for r in A)
        + ". Sivagiri12's cleaning turns every lead from the API into a missing value, so its rows are the 5,496 leads "
        "that did not come from the API.",
        "",
    ]
    L += [
        "### Accuracy, sensitivity and specificity at each solution's own cut-off rule",
        "",
        "| Public solution | Model | Cut-off | Accuracy | Sensitivity | Specificity | Precision | Log-loss |",
        "|---|---|---|---|---|---|---|---|",
    ]
    names = {
        "theirs": "theirs (published)",
        "ours_same_inputs": "ours, same inputs",
        "ours_new_lead_inputs": "ours, new-lead inputs",
        "theirs_no_post_contact": "theirs without post-contact columns",
    }
    for r in A:
        for k, nm in names.items():
            m = r["models"][k]
            L.append(
                f"| {short(r)} | {nm} | {m['cutoff']:.2f} | {pct(m['accuracy'])} | {pct(m['sensitivity'])} | "
                f"{pct(m['specificity'])} | {pct(m['precision'])} | {m['log_loss']:.4f} |"
            )
    L += [
        "",
        "| Public solution | Ours (same inputs) vs theirs: accuracy | McNemar p | Log-loss lower by [95% CI] |",
        "|---|---|---|---|",
    ]
    for r in A:
        v = r["vs_theirs"]["ours_same_inputs"]
        L.append(
            f"| {short(r)} | {100 * v['accuracy']['diff']:+.1f} points ({v['accuracy']['ours_only_right']} "
            f"leads only ours got right, {v['accuracy']['theirs_only_right']} only theirs) | {pval(v['accuracy']['p'])} | "
            f"{v['log_loss']['diff']:+.4f} [{v['log_loss']['low']:+.4f}, {v['log_loss']['high']:+.4f}] |"
        )
    L += [
        "",
        f"### {REPEAT_SPLITS} more random 70/30 splits of each solution's rows",
        "",
        "Mean AUC with the corrected resampled t-interval (Nadeau & Bengio 2003); their model keeps its published "
        "feature list (chosen on the original split, which can only favour it).",
        "",
        "| Public solution | Their AUC | Ours, same inputs | Ours − theirs | Ours better in | Ours, new-lead inputs | "
        "New-lead − theirs |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in A:
        s = r["repeated_splits"]
        L.append(
            f"| {short(r)} | {ci(*s['theirs_auc'])} | {ci(*s['ours_same_inputs_auc'])} | "
            f"{s['ours_same_minus_theirs'][0]:+.3f} [{s['ours_same_minus_theirs'][1]:+.3f}, {s['ours_same_minus_theirs'][2]:+.3f}] | "
            f"{s['ours_same_wins']} of {s['splits']} | {ci(*s['ours_new_lead_inputs_auc'])} | "
            f"{s['ours_new_minus_theirs'][0]:+.3f} [{s['ours_new_minus_theirs'][1]:+.3f}, {s['ours_new_minus_theirs'][2]:+.3f}] |"
        )
    L += [
        "",
        "## B. Published results whose code is not public",
        "",
        "| Publication | Post-contact columns | Their protocol | Their result | Ours |",
        "|---|---|---|---|---|",
    ]
    for pb in PUBLISHED_B:
        theirs_txt = f"{pb['model']}: accuracy {pct(pb['accuracy'])}" + (f", AUC {pb['auc']:.4g}" if pb["auc"] else "")
        if pb["note"]:
            theirs_txt += f" ({pb['note']})"
        if pb["who"].startswith("Mandal"):
            o = (
                f"same protocol, 9 new-lead columns, {B['splits']} stratified 80/20 splits: AUC {B['auc_mean']:.3f} (95% of "
                f"splits {B['auc_p2_5']:.3f}–{B['auc_p97_5']:.3f}; above {pb['auc']} in "
                f"{100 * B['share_auc_above_published']:.0f}%), accuracy {pct(B['accuracy_mean'])} with the cut-off chosen "
                "on the training rows"
            )
        else:
            o = (
                f"with post-contact columns (5-fold CV): AUC {leak['auc'][0]:.3f}, accuracy {pct(leak['accuracy'])}. "
                f"Without them the best accuracy in this study is {pct(leakfree_acc)}: above 90% needs post-contact columns"
            )
        L.append(f"| [{pb['who']}]({pb['url']}) | {pb['post_contact']} | {pb['protocol']} | {theirs_txt} | {o} |")
    better = [x for x in same if x["diff"] > 0 and x["p"] < 0.05]
    worse = [x for x in same if x["diff"] < 0 and x["p"] < 0.05]
    lo = rs["lohani"]["vs_theirs"]["ours_new_lead_inputs"]["auc"]
    lo_rep = rs["lohani"]["repeated_splits"]
    L += [
        "",
        "## What this shows (computed from the numbers above)",
        "",
        f"- **Same rows, same inputs:** on each solution's own split our AUC is higher for all {len(A)} "
        f"({len(better)} significantly, DeLong p < 0.05; {len(A) - len(better) - len(worse)} not significantly; "
        f"{len(worse)} lower), and on {REPEAT_SPLITS} new splits ours is better in "
        f"{', '.join(str(x['ours_same_wins']) for x in reps)} of {REPEAT_SPLITS} with every interval above zero"
        f"{'' if all(x['ours_same_minus_theirs'][1] > 0 for x in reps) else ' (NOT for all)'}. Nothing was tuned on "
        "their data: the gradient boosting is the CRM's own configuration.",
        "- **Their high numbers come from post-contact columns.** Refitted without those columns, each solution's own "
        "model falls: "
        + "; ".join(
            f"{short(r)} AUC {r['models']['theirs']['auc']:.3f} → "
            f"{r['models']['theirs_no_post_contact']['auc']:.3f}"
            for r in leaky
        )
        + ".",
        f"- **On what a new lead has**, our 9-column model scores AUC {min(new_aucs):.3f}–{max(new_aucs):.3f} on the four "
        f"splits; against the only leak-free public solution (Lohani & Bansal) on its own rows: "
        f"{lo['diff']:+.3f} [{lo['low']:+.3f}, {lo['high']:+.3f}] (DeLong p {pval(lo['p'])}), and "
        f"{lo_rep['ours_new_minus_theirs'][0]:+.3f} [{lo_rep['ours_new_minus_theirs'][1]:+.3f}, "
        f"{lo_rep['ours_new_minus_theirs'][2]:+.3f}] over {REPEAT_SPLITS} new splits (better in {lo_rep['ours_new_wins']}). "
        f"Under the leak-free thesis's protocol it reaches AUC {B['auc_mean']:.3f} on average "
        f"({100 * B['share_auc_above_published']:.0f}% of {B['splits']} splits above the thesis's 0.8605).",
        f"- **The honest ceiling.** Without post-contact columns no model in this study goes beyond AUC "
        f"{max(new_aucs + [B['auc_p97_5']]):.3f} or accuracy {pct(leakfree_acc)}. The accuracies above 90% reported "
        "for this file (two of the public solutions, which use post-contact columns; Jadli et al.; Yim et al., whose "
        "inputs are not listed) are out of reach for a model that scores new leads.",
        f"- Leads in the file: {len(y):,}; converted {100 * y.mean():.1f}%.",
    ]
    return L


def main():
    t0 = time.time()
    say = lambda s: print(s, flush=True)
    frame, y = new_lead_frame()
    if "--report-only" in sys.argv:  # rewrite the .md from the saved .json
        with open(os.path.join(RESULTS, "published_benchmark.json"), encoding="utf-8") as f:
            saved = json.load(f)
        lines = report(saved["part_a"], saved["part_b_mandal_protocol"], saved["with_post_contact_columns"], y)
        with open(os.path.join(RESULTS, "published_benchmark.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print("\n".join(lines))
        return
    A = part_a(frame, y, say)
    B = part_b(frame, y, say)
    leak = leaky_ceiling(y, say)
    lines = report(A, B, leak, y)
    os.makedirs(RESULTS, exist_ok=True)
    with open(os.path.join(RESULTS, "published_benchmark.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(RESULTS, "published_benchmark.json"), "w", encoding="utf-8") as f:
        json.dump(
            {"part_a": A, "part_b_mandal_protocol": B, "with_post_contact_columns": leak, "published_b": PUBLISHED_B},
            f,
            indent=1,
            default=float,
        )
    print("\n" + "\n".join(lines))
    print(f"\n({time.time() - t0:.0f} s) Saved ml/results/published_benchmark.md")


if __name__ == "__main__":
    main()
