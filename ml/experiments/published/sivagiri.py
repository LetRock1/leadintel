"""Faithful re-implementation of Lead-Scoring-Case-Study---Sivagiri,
"Lead Scoring Case Study -  Sivagiri.ipynb".

usage: python ml/experiments/published/sivagiri.py <path to Leads.csv> [<output .pkl path>]

Notebook cell numbers are given as [n] (0-based cell index of the .ipynb).
Only pandas / numpy / scikit-learn are used. The notebook's statsmodels GLM(Binomial) fit is
reproduced with an unpenalised sklearn LogisticRegression (same maximum-likelihood solution).
"""
import pickle
import sys
import warnings

import numpy as np
import pandas as pd
from sklearn.feature_selection import RFE
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MinMaxScaler

warnings.filterwarnings("ignore")

NAME = "sivagiri"
REPO = "Lead-Scoring-Case-Study---Sivagiri (Lead Scoring Case Study -  Sivagiri.ipynb)"
LEAKY_SOURCES = ["Tags", "Lead Quality", "Lead Profile", "Last Activity", "Last Notable Activity",
                 "Asymmetrique Activity Index", "Asymmetrique Profile Index",
                 "Asymmetrique Activity Score", "Asymmetrique Profile Score"]

# ---- what the notebook printed ---------------------------------------------------------------
RFE_RANKING_REPORTED = {  # [61] list(zip(X_train.columns, rfe.support_, rfe.ranking_))
    "TotalVisits": 1, "Total Time Spent on Website": 1, "Page Views Per Visit": 25, "Lead Origin_lead add form": 1, "Lead Origin_lead import": 1, "Specialization_business administration": 45, "Specialization_e-business": 17, "Specialization_e-commerce": 44, "Specialization_finance management": 48, "Specialization_healthcare management": 41, "Specialization_hospitality management": 8, "Specialization_human resource management": 57, "Specialization_international business": 58, "Specialization_it projects management": 47, "Specialization_marketing management": 32, "Specialization_media and advertising": 24, "Specialization_operations management": 37, "Specialization_retail management": 18, "Specialization_rural and agribusiness": 46, "Specialization_select": 1, "Specialization_services excellence": 61, "Specialization_supply chain management": 31, "Specialization_travel and tourism": 19, "Lead Source_blog": 28, "Lead Source_click2call": 16, "Lead Source_direct traffic": 11, "Lead Source_facebook": 39, "Lead Source_google": 13, "Lead Source_live chat": 26, "Lead Source_nc_edm": 14, "Lead Source_olark chat": 9, "Lead Source_organic search": 12, "Lead Source_pay per click ads": 34, "Lead Source_press_release": 40, "Lead Source_reference": 1, "Lead Source_referral sites": 54, "Lead Source_social media": 50, "Lead Source_testone": 27, "Lead Source_welearn": 36, "Lead Source_welearnblog_home": 33, "Lead Source_welingak website": 1, "Lead Source_youtubechannel": 42, "Do Not Email_yes": 1, "Last Activity_converted to lead": 23, "Last Activity_email bounced": 20, "Last Activity_email link clicked": 49, "Last Activity_email marked spam": 15, "Last Activity_email opened": 1, "Last Activity_email received": 63, "Last Activity_form submitted on website": 29, "Last Activity_had a phone conversation": 1, "Last Activity_olark chat conversation": 30, "Last Activity_page visited on website": 35, "Last Activity_sms sent": 2, "Last Activity_unreachable": 38, "Last Activity_unsubscribed": 59, "Last Activity_view in browser link clicked": 56, "Last Activity_visited booth in tradeshow": 51, "What is your current occupation_housewife": 1, "What is your current occupation_other": 4, "What is your current occupation_student": 3, "What is your current occupation_unemployed": 6, "What is your current occupation_working professional": 1, "A free copy of Mastering The Interview_yes": 55, "Last Notable Activity_email bounced": 43, "Last Notable Activity_email link clicked": 21, "Last Notable Activity_email marked spam": 10, "Last Notable Activity_email opened": 1, "Last Notable Activity_email received": 62, "Last Notable Activity_form submitted on website": 53, "Last Notable Activity_had a phone conversation": 7, "Last Notable Activity_modified": 1, "Last Notable Activity_olark chat conversation": 60, "Last Notable Activity_page visited on website": 22, "Last Notable Activity_sms sent": 52, "Last Notable Activity_unreachable": 1, "Last Notable Activity_unsubscribed": 5}
# [70] dropped by p-value: 'What is your current occupation_housewife'  -> final model logm3 [71]
FINAL_FEATURES = [
    "TotalVisits", "Total Time Spent on Website", "Lead Origin_lead add form",
    "Lead Origin_lead import", "Specialization_select", "Lead Source_reference",
    "Lead Source_welingak website", "Do Not Email_yes", "Last Activity_email opened",
    "Last Activity_had a phone conversation", "What is your current occupation_working professional",
    "Last Notable Activity_email opened", "Last Notable Activity_modified",
    "Last Notable Activity_unreachable"]
COEF_REPORTED = {  # [71] logm3 summary
    "const": -1.3784, "TotalVisits": 3.9113, "Total Time Spent on Website": 4.6112,
    "Lead Origin_lead add form": 3.2680, "Lead Origin_lead import": 2.0829,
    "Specialization_select": -1.4446, "Lead Source_reference": 1.7958,
    "Lead Source_welingak website": 4.3360, "Do Not Email_yes": -1.9162,
    "Last Activity_email opened": 0.6957, "Last Activity_had a phone conversation": 1.1403,
    "What is your current occupation_working professional": 2.8509,
    "Last Notable Activity_email opened": -1.6287, "Last Notable Activity_modified": -1.4555,
    "Last Notable Activity_unreachable": 1.4428}
CUTOFF = 0.35  # [93] from the accuracy/sensitivity/specificity curve; applied to test in [104];
#               the summary PDF names 0.35 as the operating cut-off. [118]/[126] re-check with 0.41
#               from the precision-recall curve (kept below as an alternative).
CUTOFF_ALT = 0.41
REPORTED = {
    "train": {  # [94] [95] [97] [98]
        "cutoff": 0.35, "n": 3847, "confusion": [[1706, 472], [269, 1400]],
        "accuracy": 0.807382375877307, "sensitivity": 0.8388256440982624,
        "specificity": 0.783287419651056, "precision": None, "npv": None, "fpr": None,
        "f1": None, "roc_auc": None},
    "test": {  # [105] [106] [108] [109]
        "cutoff": 0.35, "n": 1649, "confusion": [[787, 211], [111, 540]],
        "accuracy": 0.8047301394784718, "sensitivity": 0.8294930875576036,
        "specificity": 0.7885771543086172, "precision": None, "npv": None, "fpr": None,
        "f1": None, "roc_auc": None},
    "extra": {
        "train_at_0.5": {"confusion": [[1894, 284], [427, 1242]], "accuracy": 0.815180660254744,
                         "sensitivity": 0.74415817855003, "specificity": 0.869605142332415,
                         "precision": 0.8138925294888598},                       # [80]-[85] [111]-[113]
        "train_at_0.41": {"confusion": [[1797, 381], [327, 1342]], "accuracy": 0.8159604886924876,
                          "precision": 0.7788740568775392, "sensitivity": 0.8040742959856201},  # [119]-[123]
        "test_at_0.41": {"confusion": [[834, 164], [129, 522]], "accuracy": 0.8223165554881746,
                         "precision": 0.760932944606414, "sensitivity": 0.8018433179723502},    # [127]-[131]
        "roc_auc": "not printed as text (only inside the ROC plot image)"},
    "source": "printed outputs of cells [80]-[85] [94]-[98] [105]-[109] [111]-[113] [119]-[131]",
}
SPLIT_HEAD = {"train": [7700, 3521, 934, 6247, 900], "test": [5279, 7398, 8404, 4960, 6352]}


def metrics_at(y, p, cutoff):
    y = np.asarray(y).astype(int)
    p = np.asarray(p, dtype=float)
    pred = (p > cutoff).astype(int)  # notebooks: 1 if x > cutoff else 0
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    n = len(y)
    return {"cutoff": float(cutoff), "n": int(n),
            "confusion": [[int(tn), int(fp)], [int(fn), int(tp)]],
            "accuracy": (tp + tn) / n, "sensitivity": tp / (tp + fn),
            "specificity": tn / (tn + fp), "precision": tp / (tp + fp) if tp + fp else float("nan"),
            "npv": tn / (tn + fn) if tn + fn else float("nan"), "fpr": fp / (tn + fp),
            "f1": 2 * tp / (2 * tp + fp + fn), "roc_auc": float(roc_auc_score(y, p))}


def run_rfe(X, y, reported_ranking, n_select, notes):
    """RFE(LogisticRegression(), n) as in the notebook, run two ways.

    The installed scikit-learn (1.6.1) minimises the MEAN log-loss with lbfgs and stops at
    gtol=tol, while the older versions the notebooks ran minimised C * SUM(log-loss) + penalty, so
    the same default tol=1e-4 stopped much later. LogisticRegression(tol=1e-4 / n_samples) reproduces the old stopping rule; the literal
    1.6.1 defaults are run as well and reported."""
    out = {}
    for key, est in (("old_sklearn_emulation", LogisticRegression(tol=1e-4 / len(X))),
                     ("sklearn_1_6_defaults", LogisticRegression())):
        r = RFE(est, n_features_to_select=n_select).fit(X, y)
        sel = list(X.columns[r.support_])
        rep_sel = [c for c in X.columns if reported_ranking[c] == 1]
        same = int(sum(reported_ranking[c] == k for c, k in zip(X.columns, r.ranking_)))
        out[key] = {"selected": sel, "selection_matches_notebook": set(sel) == set(rep_sel),
                    "identical_ranks": f"{same}/{X.shape[1]}",
                    "only_reproduced": sorted(set(sel) - set(rep_sel)),
                    "only_notebook": sorted(set(rep_sel) - set(sel))}
        print(f"RFE({n_select}) {key:22s}: selection == notebook: {set(sel) == set(rep_sel)}; "
              f"identical ranks {same}/{X.shape[1]}"
              + ("" if set(sel) == set(rep_sel) else
                 f"; only reproduced {out[key]['only_reproduced']}, only notebook {out[key]['only_notebook']}"))
    e, d = out["old_sklearn_emulation"], out["sklearn_1_6_defaults"]
    notes.append(f"RFE: old-sklearn emulation (tol=1e-4/n) matches the notebook's printed selection: "
                 f"{e['selection_matches_notebook']} (identical ranks {e['identical_ranks']}); literal "
                 f"sklearn 1.6.1 defaults: {d['selection_matches_notebook']} (identical ranks "
                 f"{d['identical_ranks']}, only reproduced {d['only_reproduced']}, only notebook "
                 f"{d['only_notebook']}). The final model uses the notebook's final feature list either way.")
    return out


def fit_mle(X, y):
    """Unpenalised logistic regression with intercept == statsmodels GLM(Binomial) MLE."""
    m = LogisticRegression(penalty=None, solver="newton-cg", max_iter=10000, tol=1e-10)
    m.fit(X.astype(float).values, np.asarray(y))
    return m


def show(rep, rpr, keys=("accuracy", "sensitivity", "specificity", "precision", "f1", "roc_auc")):
    for k in keys:
        a, b = rep.get(k), rpr.get(k)
        a_s = "   n/a  " if a is None else f"{a:.6f}"
        d = "" if a is None else f"  diff {100 * (b - a):+.3f} pp"
        print(f"    {k:12s} reported {a_s}  reproduced {b:.6f}{d}")
    print(f"    confusion    reported {rep.get('confusion')}  reproduced {rpr['confusion']}")


def slots(x):                                                                   # [21]
    if x == "india":
        return "india"
    elif x == "not provided":
        return "not provided"
    return "outside india"


def reproduce(csv_path, out_path=None):
    """Re-run the notebook on csv_path; returns the dict described in published/__init__.py."""
    notes = []
    df = pd.read_csv(csv_path)                                                  # [4]
    assert df.shape == (9240, 37)

    # ---- cleaning
    lower = lambda s: s.lower() if type(s) == str else s  # noqa: E731
    df = df.map(lower) if hasattr(pd.DataFrame, "map") else df.applymap(lower)  # [11] (applymap)
    df = df.replace("api", np.nan)                                              # [12] (comment says 'Select'!)
    nun = df.nunique()                                                          # [13]
    assert (nun["Lead Origin"], nun["Lead Source"], nun["Specialization"], nun["Tags"]) == (4, 20, 19, 26)
    df1 = df.drop(["Magazine", "Receive More Updates About Our Courses",
                   "I agree to pay the amount through cheque", "Get updates on DM Content",
                   "Update me on Supply Chain Content"], axis=1)                # [14]
    df2 = df1.drop(["Asymmetrique Profile Index", "Asymmetrique Activity Index",
                    "Asymmetrique Activity Score", "Asymmetrique Profile Score", "Lead Profile",
                    "Tags", "Lead Quality", "How did you hear about X Education", "City",
                    "Lead Number"], axis=1)                                     # [16]
    for c in ["Specialization", "What matters most to you in choosing a course", "Country",
              "What is your current occupation"]:
        df2[c] = df2[c].fillna("not provided")                                  # [18]
    df2["Country"] = df2.apply(lambda x: slots(x["Country"]), axis=1)           # [21]
    assert df2["Country"].value_counts().to_dict() == {"india": 6492, "not provided": 2461,
                                                       "outside india": 287}
    df3 = df2[df2.isnull().sum(axis=1) < 1]                                     # [24]
    assert len(df3) == 5496 and round(100 * df3.shape[0] / df.shape[0], 2) == 59.48  # [25] [28]
    df_final = df3.drop("Prospect ID", axis=1)                                  # [28]

    # ---- dummies                                                                  [49] [50]
    dummy = pd.get_dummies(df_final[["Lead Origin", "Specialization", "Lead Source", "Do Not Email",
                                     "Last Activity", "What is your current occupation",
                                     "A free copy of Mastering The Interview",
                                     "Last Notable Activity"]], drop_first=True).astype("uint8")
    df_final_dum = pd.concat([df_final, dummy], axis=1)
    assert df_final_dum.shape == (5496, 97)
    df_final_dum = df_final_dum.drop([
        "What is your current occupation_not provided", "Lead Origin", "Lead Source", "Do Not Email",
        "Do Not Call", "Last Activity", "Country", "Specialization", "Specialization_not provided",
        "What is your current occupation", "What matters most to you in choosing a course", "Search",
        "Newspaper Article", "X Education Forums", "Newspaper", "Digital Advertisement",
        "Through Recommendations", "A free copy of Mastering The Interview",
        "Last Notable Activity"], axis=1)
    assert df_final_dum.shape == (5496, 78)

    X = df_final_dum.drop(["Converted"], axis=1)                                # [52]
    y = df_final_dum["Converted"]                                               # [53]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, train_size=0.7, test_size=0.3, random_state=10)                   # [54]
    assert list(X_train.index[:5]) == SPLIT_HEAD["train"]                       # [55] head
    assert list(X_test.index[:5]) == SPLIT_HEAD["test"]                         # [102] head
    assert X_train.shape == (3847, 77) and X_test.shape == (1649, 77)

    num = ["TotalVisits", "Page Views Per Visit", "Total Time Spent on Website"]
    scaler = MinMaxScaler()
    X_train[num] = scaler.fit_transform(X_train[num])                           # [55]
    X_test = X_test.copy()
    X_test[num] = scaler.transform(X_test[num])                                 # [100] train-fitted scaler
    X_test_train_scaled = X_test.copy()   # identical here: the notebook used the train scaler
    assert abs(X_train.loc[7700, "TotalVisits"] - 0.015936) < 5e-7              # [55] head
    assert abs(X_test.loc[5279, "Total Time Spent on Website"] - 0.087601) < 5e-7  # [102] head

    # ---- RFE with LogisticRegression() defaults, 15 features                   [59] [60]
    assert list(X_train.columns) == list(RFE_RANKING_REPORTED)
    rfe = run_rfe(X_train, y_train, RFE_RANKING_REPORTED, 15, notes)

    # ---- final model logm3                                                      [71]
    model = fit_mle(X_train[FINAL_FEATURES], y_train)
    coef = dict(zip(["const"] + FINAL_FEATURES, [model.intercept_[0]] + list(model.coef_[0])))
    max_coef_diff = max(abs(coef[k] - v) for k, v in COEF_REPORTED.items())
    print(f"final model: max |coef - notebook coef| = {max_coef_diff:.5f} (notebook prints 4 d.p.)")
    train_proba = model.predict_proba(X_train[FINAL_FEATURES].astype(float).values)[:, 1]
    test_proba = model.predict_proba(X_test[FINAL_FEATURES].astype(float).values)[:, 1]

    reproduced = {"train": metrics_at(y_train, train_proba, CUTOFF),
                  "test": metrics_at(y_test, test_proba, CUTOFF),
                  "extra": {"train_at_0.5": metrics_at(y_train, train_proba, 0.5),
                            "train_at_0.41": metrics_at(y_train, train_proba, CUTOFF_ALT),
                            "test_at_0.41": metrics_at(y_test, test_proba, CUTOFF_ALT),
                            "max_abs_coef_diff_vs_notebook": max_coef_diff,
                            "coefficients": coef, "rfe": rfe}}
    print("TRAIN (cut-off %.2f):" % CUTOFF)
    show(REPORTED["train"], reproduced["train"])
    print("TEST  (cut-off %.2f):" % CUTOFF)
    show(REPORTED["test"], reproduced["test"])
    print("TEST  (alternative cut-off %.2f, precision-recall):" % CUTOFF_ALT)
    show(REPORTED["extra"]["test_at_0.41"], reproduced["extra"]["test_at_0.41"],
         keys=("accuracy", "sensitivity", "precision"))
    print("TRAIN (cut-off 0.5) / (0.41):")
    show(REPORTED["extra"]["train_at_0.5"], reproduced["extra"]["train_at_0.5"],
         keys=("accuracy", "sensitivity", "specificity", "precision"))
    show(REPORTED["extra"]["train_at_0.41"], reproduced["extra"]["train_at_0.41"],
         keys=("accuracy", "sensitivity", "precision"))

    design_cols = list(X_train.columns)
    leaky_in_design = [s for s in LEAKY_SOURCES if any(c == s or c.startswith(s + "_") for c in design_cols)]
    leaky_final = [c for c in FINAL_FEATURES if any(c == s or c.startswith(s + "_") for s in LEAKY_SOURCES)]
    notes.append(
        "All string values are lower-cased first ([11]); then the notebook replaces 'api' (not "
        "'select') with NaN ([12], the comment says 'Select'), so every API-origin lead becomes "
        "missing and is removed by the complete-case filter ([24]): only 5,496 of 9,240 leads "
        "(59.48%, all non-API) are modelled, test n=1,649. 'select' is kept as a category "
        "(Specialization_select is a final feature). Tags, Lead Quality, Lead Profile and the "
        "Asymmetrique columns are dropped by hand ([16]) but Last Activity / Last Notable Activity "
        "are kept as dummies. Split 70/30 random_state=10, not stratified; MinMaxScaler fitted on "
        "train only and applied to test (no test re-fit), so X_test_train_scaled == X_test. "
        "Primary cut-off 0.35 (sensitivity/specificity, named in the summary PDF); the notebook "
        "also evaluates 0.41 (precision/recall) on test, kept under extra. No AUC is printed as text.")
    out = {"name": NAME, "repo": REPO,
           "X_train": X_train, "X_test": X_test, "X_test_train_scaled": X_test_train_scaled,
           "y_train": y_train, "y_test": y_test,
           "train_index": np.asarray(X_train.index), "test_index": np.asarray(X_test.index),
           "final_features": FINAL_FEATURES, "cutoff": CUTOFF, "cutoff_alt": CUTOFF_ALT,
           "test_proba": test_proba, "train_proba": train_proba,
           "reported": REPORTED, "reproduced": reproduced,
           "leaky_final_features": leaky_final, "leaky_columns_in_design": leaky_in_design,
           "notes": " ".join(notes)}
    if out_path:
        with open(out_path, "wb") as f:
            pickle.dump(out, f)
    print("leaky final features:", leaky_final)
    print("leaky source columns in design matrix:", leaky_in_design)
    print("design matrix:", X_train.shape, X_test.shape, "->", out_path)
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: python ml/experiments/published/sivagiri.py <Leads.csv> [<out.pkl>]")
    reproduce(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
