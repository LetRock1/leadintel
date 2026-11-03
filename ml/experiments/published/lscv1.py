"""Faithful re-implementation of Lead_Score_Case_Study, Lead_Case_Study_v1.ipynb.

usage: python ml/experiments/published/lscv1.py <path to Leads.csv> [<output .pkl path>]

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
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

NAME = "lscv1"
REPO = "Lead_Score_Case_Study (Lead_Case_Study_v1.ipynb)"
LEAKY_SOURCES = ["Tags", "Lead Quality", "Lead Profile", "Last Activity", "Last Notable Activity",
                 "Asymmetrique Activity Index", "Asymmetrique Profile Index",
                 "Asymmetrique Activity Score", "Asymmetrique Profile Score"]

# ---- what the notebook printed ---------------------------------------------------------------
RFE_RANKING_REPORTED = {  # [130] list(zip(X_train.columns, rfe.support_, rfe.ranking_))
    "TotalVisits": 26, "Total Time Spent on Website": 1, "Page Views Per Visit": 24, "Lead Origin_Landing Page Submission": 10, "Lead Origin_Lead Add Form": 1, "Lead Origin_Lead Import": 16, "What is your current occupation_Housewife": 31, "What is your current occupation_Other": 34, "What is your current occupation_Student": 23, "What is your current occupation_Unemployed": 20, "What is your current occupation_Working Professional": 8, "City_Other Cities": 22, "City_Other Cities of Maharashtra": 37, "City_Other Metro Cities": 40, "City_Thane & Outskirts": 38, "City_Tier II Cities": 28, "Specialization_Banking, Investment And Insurance": 14, "Specialization_Business Administration": 39, "Specialization_E-Business": 35, "Specialization_E-COMMERCE": 21, "Specialization_International Business": 41, "Specialization_Management_Specializations": 36, "Specialization_Media and Advertising": 33, "Specialization_Rural and Agribusiness": 30, "Specialization_Services Excellence": 32, "Specialization_Travel and Tourism": 7, "Lead Source_Direct Traffic": 1, "Lead Source_Google": 3, "Lead Source_Live Chat": 42, "Lead Source_Olark Chat": 29, "Lead Source_Organic Search": 2, "Lead Source_Reference": 13, "Lead Source_Referral Sites": 1, "Lead Source_Social Media": 15, "Lead Source_Welingak Website": 1, "Last Activity_Converted to Lead": 11, "Last Activity_Email Bounced": 5, "Last Activity_Email Link Clicked": 27, "Last Activity_Email Opened": 18, "Last Activity_Form Submitted on Website": 17, "Last Activity_Olark Chat Conversation": 6, "Last Activity_Page Visited on Website": 12, "Last Activity_SMS Sent": 1, "Last Notable Activity_Email Link Clicked": 4, "Last Notable Activity_Email Opened": 19, "Last Notable Activity_Modified": 1, "Last Notable Activity_Olark Chat Conversation": 1, "Last Notable Activity_Page Visited on Website": 25, "Last Notable Activity_SMS Sent": 1, "Tags_Busy": 9, "Tags_Closed by Horizzon": 1, "Tags_Interested in other courses": 1, "Tags_Lost to EINS": 1, "Tags_Other_Tags": 1, "Tags_Ringing": 1, "Tags_Will revert after reading the email": 1}
# [135] dropped 'Lead Source_Referral Sites' (p-value), [141] dropped 'Last Notable Activity_SMS Sent' (VIF)
FINAL_FEATURES = [  # col of model #3 [142]
    "Total Time Spent on Website", "Lead Origin_Lead Add Form", "Lead Source_Direct Traffic",
    "Lead Source_Welingak Website", "Last Activity_SMS Sent", "Last Notable Activity_Modified",
    "Last Notable Activity_Olark Chat Conversation", "Tags_Closed by Horizzon",
    "Tags_Interested in other courses", "Tags_Lost to EINS", "Tags_Other_Tags", "Tags_Ringing",
    "Tags_Will revert after reading the email"]
COEF_REPORTED = {  # [142] model #3 summary
    "const": -1.1179, "Total Time Spent on Website": 0.8896, "Lead Origin_Lead Add Form": 1.6630,
    "Lead Source_Direct Traffic": -0.8212, "Lead Source_Welingak Website": 3.8845,
    "Last Activity_SMS Sent": 1.9981, "Last Notable Activity_Modified": -1.6525,
    "Last Notable Activity_Olark Chat Conversation": -1.8023, "Tags_Closed by Horizzon": 7.1955,
    "Tags_Interested in other courses": -2.1318, "Tags_Lost to EINS": 5.9177,
    "Tags_Other_Tags": -2.3737, "Tags_Ringing": -3.4531,
    "Tags_Will revert after reading the email": 4.5070}
CUTOFF = 0.3  # [167] from the accuracy/sensitivity/specificity curve; applied to test in [202]
REPORTED = {
    "train": {  # [169] [170] [172] [173] [175]-[177]
        "cutoff": 0.3, "n": 6267, "confusion": [[3597, 285], [198, 2187]],
        "accuracy": 0.922929631402585, "sensitivity": 0.9169811320754717,
        "specificity": 0.9265842349304482, "precision": 0.8847087378640777,
        "npv": 0.9478260869565217, "fpr": 0.07341576506955177, "f1": None, "roc_auc": None},
    "test": {  # [203] [204] [206]-[209]
        "cutoff": 0.3, "n": 2686, "confusion": [[1563, 113], [81, 929]],
        "accuracy": 0.9277736411020104, "sensitivity": 0.9198019801980198,
        "specificity": 0.9325775656324582, "precision": 0.8915547024952015, "npv": None,
        "fpr": None, "f1": None, "roc_auc": None},
    "extra": {
        "train_at_0.5": {"confusion": [[3693, 189], [281, 2104]], "accuracy": 0.9250039891495133,
                         "sensitivity": 0.8821802935010482, "specificity": 0.9513137557959814,
                         "precision": 0.9175752289576974, "npv": 0.9292903875188727,
                         "fpr": 0.04868624420401855},                               # [149]-[156]
        "train_roc_auc_text": "0.97 (markdown [161], read off the ROC plot legend, 2 d.p.)"},
    "source": "printed outputs of cells [149]-[156] [169]-[182] [203]-[209]",
}
SPLIT_HEAD = {"train": [9196, 4696, 3274, 2164, 1667], "test": [7681, 984, 8135, 6915, 2712]}


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


def reproduce(csv_path, out_path=None):
    """Re-run the notebook on csv_path; returns the dict described in published/__init__.py."""
    notes = []
    leads = pd.read_csv(csv_path)                                               # [2]
    assert leads.shape == (9240, 37)

    leads = leads.drop(["Prospect ID", "Lead Number"], axis=1)                  # [11]
    leads = leads.replace("Select", np.nan)                                     # [12]
    before = set(leads.columns)
    for i in list(leads.columns):                                               # [15] drop >= 45% missing
        if (100 * (leads[i].isnull().sum() / len(leads.index))) >= 45:
            leads = leads.drop(i, axis=1)
    assert before - set(leads.columns) == {
        "How did you hear about X Education", "Lead Quality", "Lead Profile",
        "Asymmetrique Activity Index", "Asymmetrique Profile Index",
        "Asymmetrique Activity Score", "Asymmetrique Profile Score"}

    leads["Country"] = leads["Country"].replace(np.nan, "India")                # [20]
    cols_to_drop = ["Country"]                                                  # [23]
    leads["City"] = leads["City"].replace(np.nan, "Mumbai")                     # [25]
    leads["Specialization"] = leads["Specialization"].replace(np.nan, "Not Specified")  # [28]
    leads["Specialization"] = leads["Specialization"].replace(
        ["Finance Management", "Human Resource Management", "Marketing Management",
         "Operations Management", "IT Projects Management", "Supply Chain Management",
         "Healthcare Management", "Hospitality Management", "Retail Management"],
        "Management_Specializations")                                           # [31]
    leads["What is your current occupation"] = leads["What is your current occupation"].replace(
        np.nan, "Unemployed")                                                   # [34]
    leads["What matters most to you in choosing a course"] = leads[
        "What matters most to you in choosing a course"].replace(np.nan, "Better Career Prospects")  # [39]
    cols_to_drop.append("What matters most to you in choosing a course")       # [42]
    leads["Tags"] = leads["Tags"].replace(np.nan, "Not Specified")              # [44]
    leads["Tags"] = leads["Tags"].replace(
        ["In confusion whether part time or DLP", "in touch with EINS", "Diploma holder (Not Eligible)",
         "Approached upfront", "Graduation in progress", "number not provided", "opp hangup",
         "Still Thinking", "Lost to Others", "Shall take in the next coming month", "Lateral student",
         "Interested in Next batch", "Recognition issue (DEC approval)",
         "Want to take admission but has financial problems", "University not recognized"],
        "Other_Tags")                                                           # [46]
    leads["Tags"] = leads["Tags"].replace(
        ["switched off", "Already a student", "Not doing further education", "invalid number",
         "wrong number given", "Interested  in full time MBA"], "Other_Tags")
    leads["Lead Source"] = leads["Lead Source"].replace(np.nan, "Others")       # [49]
    leads["Lead Source"] = leads["Lead Source"].replace("google", "Google")
    leads["Lead Source"] = leads["Lead Source"].replace("Facebook", "Social Media")
    leads["Lead Source"] = leads["Lead Source"].replace(
        ["bing", "Click2call", "Press_Release", "youtubechannel", "welearnblog_Home", "WeLearn",
         "blog", "Pay per Click Ads", "testone", "NC_EDM"], "Others")
    leads["Last Activity"] = leads["Last Activity"].replace(np.nan, "Others")   # [54]
    leads["Last Activity"] = leads["Last Activity"].replace(
        ["Unreachable", "Unsubscribed", "Had a Phone Conversation", "Approached upfront",
         "View in browser link Clicked", "Email Marked Spam", "Email Received",
         "Resubscribed to emails", "Visited Booth in Tradeshow"], "Others")
    leads = leads.dropna()                                                      # [57]
    assert len(leads) == 9103
    assert leads["Lead Origin"].value_counts().to_dict() == {
        "Landing Page Submission": 4886, "API": 3578, "Lead Add Form": 608, "Lead Import": 31}  # [59]
    cols_to_drop.append("Do Not Call")                                          # [66]
    cols_to_drop.extend(["Search", "Magazine", "Newspaper Article", "X Education Forums", "Newspaper",
                         "Digital Advertisement", "Through Recommendations",
                         "Receive More Updates About Our Courses",
                         "Update me on Supply Chain Content", "Get updates on DM Content",
                         "I agree to pay the amount through cheque"])           # [79]
    leads["Last Notable Activity"] = leads["Last Notable Activity"].replace(
        ["Had a Phone Conversation", "Email Marked Spam", "Unreachable", "Unsubscribed",
         "Email Bounced", "Resubscribed to emails", "View in browser link Clicked",
         "Approached upfront", "Form Submitted on Website", "Email Received"],
        "Other_Notable_activity")                                               # [81]
    leads = leads.drop(cols_to_drop, axis=1)                                    # [85]
    assert leads.shape == (9103, 14)

    # ---- outliers: remove top and bottom 1% (quantiles recomputed after each filter)
    Q3 = leads.TotalVisits.quantile(0.99)                                       # [92]
    leads = leads[(leads.TotalVisits <= Q3)]
    Q1 = leads.TotalVisits.quantile(0.01)
    leads = leads[(leads.TotalVisits >= Q1)]
    assert leads.shape == (9020, 14)                                            # [93]
    Q3 = leads["Page Views Per Visit"].quantile(0.99)                           # [99]
    leads = leads[leads["Page Views Per Visit"] <= Q3]
    Q1 = leads["Page Views Per Visit"].quantile(0.01)
    leads = leads[leads["Page Views Per Visit"] >= Q1]
    assert leads.shape == (8953, 14)                                            # [100]

    # ---- dummies
    cat_cols = leads.select_dtypes(include=["object"]).columns                  # [110]
    assert list(cat_cols) == ["Lead Origin", "Lead Source", "Do Not Email", "Last Activity",
                              "Specialization", "What is your current occupation", "Tags", "City",
                              "A free copy of Mastering The Interview", "Last Notable Activity"]
    varlist = ["A free copy of Mastering The Interview", "Do Not Email"]        # [111]
    leads[varlist] = leads[varlist].apply(lambda x: x.map({"Yes": 1, "No": 0}))
    dummy = pd.get_dummies(leads[["Lead Origin", "What is your current occupation", "City"]],
                           drop_first=True).astype("uint8")                     # [112]
    leads = pd.concat([leads, dummy], axis=1)
    for col, ref in (("Specialization", "Specialization_Not Specified"),       # [113]
                     ("Lead Source", "Lead Source_Others"),                     # [114]
                     ("Last Activity", "Last Activity_Others"),                 # [115]
                     ("Last Notable Activity", "Last Notable Activity_Other_Notable_activity"),  # [116]
                     ("Tags", "Tags_Not Specified")):                           # [117]
        dummy = pd.get_dummies(leads[col], prefix=col).astype("uint8")
        dummy = dummy.drop([ref], axis=1)
        leads = pd.concat([leads, dummy], axis=1)
    # [118] drops ALL cat_cols, including the two just-mapped binaries Do Not Email and
    # A free copy of Mastering The Interview (they were object when cat_cols was taken)
    leads = leads.drop(cat_cols, axis=1)

    y = leads["Converted"]                                                      # [121]
    X = leads.drop("Converted", axis=1)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, train_size=0.7, test_size=0.3, random_state=100)                  # [122]
    assert list(X_train.index[:5]) == SPLIT_HEAD["train"]                       # [125] head
    assert list(X_test.index[:5]) == SPLIT_HEAD["test"]                         # [185] head
    assert X_train.shape == (6267, 56)                                          # [123]

    num_cols = X_train.select_dtypes(include=["float64", "int64"]).columns      # [125]
    assert list(num_cols) == ["TotalVisits", "Total Time Spent on Website", "Page Views Per Visit"]
    scaler = StandardScaler()
    X_train[num_cols] = scaler.fit_transform(X_train[num_cols])
    assert np.allclose(X_train.loc[9196, list(num_cols)].astype(float).values,
                       [0.668862, 1.848117, 1.455819], atol=5e-7)               # [125] head
    X_test_train_scaled = X_test.copy()
    X_test_train_scaled[num_cols] = scaler.transform(X_test[num_cols])
    # [185] the notebook RE-FITS the scaler on the test set
    X_test = X_test.copy()
    num_cols_test = X_test.select_dtypes(include=["float64", "int64"]).columns
    X_test[num_cols_test] = StandardScaler().fit_transform(X_test[num_cols_test])
    assert np.allclose(X_test.loc[7681, list(num_cols)].astype(float).values,
                       [0.575687, -0.311318, 0.092860], atol=5e-7)              # [185] head

    # ---- RFE with LogisticRegression() defaults, 15 features                   [128]
    assert list(X_train.columns) == list(RFE_RANKING_REPORTED)
    rfe = run_rfe(X_train, y_train, RFE_RANKING_REPORTED, 15, notes)

    # ---- final model #3                                                         [142]
    model = fit_mle(X_train[FINAL_FEATURES], y_train)
    coef = dict(zip(["const"] + FINAL_FEATURES, [model.intercept_[0]] + list(model.coef_[0])))
    max_coef_diff = max(abs(coef[k] - v) for k, v in COEF_REPORTED.items())
    print(f"final model: max |coef - notebook coef| = {max_coef_diff:.5f} (notebook prints 4 d.p.)")
    train_proba = model.predict_proba(X_train[FINAL_FEATURES].astype(float).values)[:, 1]
    test_proba = model.predict_proba(X_test[FINAL_FEATURES].astype(float).values)[:, 1]
    test_proba_ts = model.predict_proba(X_test_train_scaled[FINAL_FEATURES].astype(float).values)[:, 1]
    assert np.allclose(test_proba[:5], [0.024819, 0.025692, 0.686054, 0.005880, 0.953208], atol=5e-6)  # [190]

    reproduced = {"train": metrics_at(y_train, train_proba, CUTOFF),
                  "test": metrics_at(y_test, test_proba, CUTOFF),
                  "extra": {"train_at_0.5": metrics_at(y_train, train_proba, 0.5),
                            "test_with_train_fitted_scaler": metrics_at(y_test, test_proba_ts, CUTOFF),
                            "max_abs_coef_diff_vs_notebook": max_coef_diff,
                            "coefficients": coef, "rfe": rfe}}
    print("TRAIN (cut-off %.2f):" % CUTOFF)
    show(REPORTED["train"], reproduced["train"])
    print("TEST  (cut-off %.2f):" % CUTOFF)
    show(REPORTED["test"], reproduced["test"])
    print("TRAIN (cut-off 0.5):")
    show(REPORTED["extra"]["train_at_0.5"], reproduced["extra"]["train_at_0.5"],
         keys=("accuracy", "sensitivity", "specificity", "precision"))
    ts = reproduced["extra"]["test_with_train_fitted_scaler"]
    print(f"TEST with the train-fitted scaler instead of the notebook's test re-fit: accuracy "
          f"{ts['accuracy']:.6f} sensitivity {ts['sensitivity']:.6f} specificity {ts['specificity']:.6f}"
          f" precision {ts['precision']:.6f} auc {ts['roc_auc']:.6f} confusion {ts['confusion']}")

    design_cols = list(X_train.columns)
    leaky_in_design = [s for s in LEAKY_SOURCES if any(c == s or c.startswith(s + "_") for c in design_cols)]
    leaky_final = [c for c in FINAL_FEATURES if any(c == s or c.startswith(s + "_") for s in LEAKY_SOURCES)]
    notes.append(
        "Rows: 9,240 -> 9,103 (rows with missing TotalVisits/Page Views dropped) -> 8,953 after "
        "removing the top and bottom 1% of TotalVisits and then of Page Views Per Visit (rows "
        "removed, not capped; quantiles on the full data before the split). Columns with >=45% "
        "missing dropped (Lead Quality, Lead Profile, Asymmetrique x4, How did you hear); Tags is "
        "kept (NaN -> 'Not Specified', rare tags -> 'Other_Tags'). Do Not Email and A free copy "
        "of Mastering The Interview are binary-mapped and then dropped with cat_cols ([118]), so "
        "they are not in the design matrix. Split 70/30 random_state=100, not stratified. The "
        "notebook re-fits StandardScaler on the test set ([185]) and 'Total Time Spent on Website' "
        f"is a final feature; X_test reproduces that, X_test_train_scaled uses the train scaler "
        f"(test accuracy {ts['accuracy']:.4f} / AUC {ts['roc_auc']:.4f} with it). No test AUC is printed; "
        "train AUC 0.97 appears only in markdown.")
    out = {"name": NAME, "repo": REPO,
           "X_train": X_train, "X_test": X_test, "X_test_train_scaled": X_test_train_scaled,
           "y_train": y_train, "y_test": y_test,
           "train_index": np.asarray(X_train.index), "test_index": np.asarray(X_test.index),
           "final_features": FINAL_FEATURES, "cutoff": CUTOFF,
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
        sys.exit("usage: python ml/experiments/published/lscv1.py <Leads.csv> [<out.pkl>]")
    reproduce(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
