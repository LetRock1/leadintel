"""Faithful re-implementation of Lead_Scoring_Case_Study,
"Lead_Scoring Case Study-Mamta Lohani and Garima Bansal.ipynb".

usage: python ml/experiments/published/lohani.py <path to Leads.csv> [<output .pkl path>]

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

NAME = "lohani"
REPO = "Lead_Scoring_Case_Study (Lead_Scoring Case Study-Mamta Lohani and Garima Bansal.ipynb)"
LEAKY_SOURCES = ["Tags", "Lead Quality", "Lead Profile", "Last Activity", "Last Notable Activity",
                 "Asymmetrique Activity Index", "Asymmetrique Profile Index",
                 "Asymmetrique Activity Score", "Asymmetrique Profile Score"]

# ---- what the notebook printed ---------------------------------------------------------------
RFE_RANKING_REPORTED = {  # [142] list(zip(X_train.columns, rfe.support_, rfe.ranking_))
    "Do Not Email": 1, "TotalVisits": 2, "Total Time Spent on Website": 1, "Page Views Per Visit": 3, "Lead Origin_Lead Add Form": 1, "Lead Origin_Lead Import": 4, "Lead Source_Direct Traffic": 1, "Lead Source_Facebook": 5, "Lead Source_Google": 1, "Lead Source_Organic Search": 1, "Lead Source_Reference": 1, "Lead Source_Referral Sites": 1, "Lead Source_Social Media": 6, "Lead Source_Welingak Website": 1, "What is your current occupation_Businessman": 1, "What is your current occupation_Housewife": 1, "What is your current occupation_Other": 1, "What is your current occupation_Student": 1, "What is your current occupation_Unemployed": 1, "What is your current occupation_Working Professional": 1}
# dropped by p-value: [148] occupation_Housewife, [152] Lead Source_Welingak Website,
# [156] occupation_Businessman, [159] occupation_Other  -> model #5 [161]
FINAL_FEATURES = [
    "Do Not Email", "Total Time Spent on Website", "Lead Origin_Lead Add Form",
    "Lead Source_Direct Traffic", "Lead Source_Google", "Lead Source_Organic Search",
    "Lead Source_Reference", "Lead Source_Referral Sites", "What is your current occupation_Student",
    "What is your current occupation_Unemployed",
    "What is your current occupation_Working Professional"]
COEF_REPORTED = {  # [161] model #5 summary
    "const": -1.2020, "Do Not Email": -0.3600, "Total Time Spent on Website": 1.1023,
    "Lead Origin_Lead Add Form": 4.6119, "Lead Source_Direct Traffic": -1.0496,
    "Lead Source_Google": -0.7804, "Lead Source_Organic Search": -0.8639,
    "Lead Source_Reference": -1.7425, "Lead Source_Referral Sites": -1.3749,
    "What is your current occupation_Student": 1.1342,
    "What is your current occupation_Unemployed": 1.2613,
    "What is your current occupation_Working Professional": 3.7575}
CUTOFF = 0.3  # [191] from the accuracy/sensitivity/specificity curve; applied to test in [237]
REPORTED = {
    "train": {  # [198] [199] [201] [202] [204]-[206] [212] [213]
        "cutoff": 0.3, "n": 6372, "confusion": [[2905, 1048], [414, 2005]],
        "accuracy": 0.7705586942875079, "sensitivity": 0.8288548987184787,
        "specificity": 0.7348848975461675, "precision": 0.6567310841794956,
        "npv": 0.8752636336245857, "fpr": 0.2651151024538325, "f1": None, "roc_auc": None},
    "test": {  # [243] [244] [246] [247] [249] [250]
        "cutoff": 0.3, "n": 2731, "confusion": [[1252, 437], [177, 865]],
        "accuracy": 0.7751739289637496, "sensitivity": 0.8301343570057581,
        "specificity": 0.7412670219064535, "precision": 0.6643625192012289, "npv": None,
        "fpr": None, "f1": None, "roc_auc": None},
    "extra": {
        "train_at_0.5": {"confusion": [[3550, 403], [849, 1570]], "accuracy": 0.8035153797865662,
                         "sensitivity": 0.649028524183547, "specificity": 0.8980521123197571,
                         "precision": 0.7957425240750127, "npv": 0.8070015912707433,
                         "fpr": 0.10194788768024285},                               # [172]-[179]
        "train_roc_auc_text": "0.86 (markdown [185], read off the ROC plot legend, 2 d.p.)"},
    "source": "printed outputs of cells [172]-[179] [198]-[213] [243]-[250]",
}
SPLIT_HEAD = {"train": [7962, 5520, 1962, 1566, 9170], "test": [3504, 4050, 7201, 1196, 8219]}


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
    leads_df = pd.read_csv(csv_path)                                            # [4]
    assert leads_df.shape == (9240, 37)                                         # [7]

    leads_df = leads_df.drop(["Prospect ID", "Lead Number"], axis=1)            # [17]
    leads_df = leads_df.replace("Select", np.nan)                               # [19]
    for i in list(leads_df.columns):                                            # [24] drop >= 35% missing
        if (100 * (leads_df[i].isnull().sum() / len(leads_df.index))) >= 35:
            leads_df = leads_df.drop(i, axis=1)
    assert list(leads_df.columns) == [                                          # [25]
        "Lead Origin", "Lead Source", "Do Not Email", "Do Not Call", "Converted", "TotalVisits",
        "Total Time Spent on Website", "Page Views Per Visit", "Last Activity", "Country",
        "What is your current occupation", "What matters most to you in choosing a course", "Search",
        "Magazine", "Newspaper Article", "X Education Forums", "Newspaper", "Digital Advertisement",
        "Through Recommendations", "Receive More Updates About Our Courses",
        "Update me on Supply Chain Content", "Get updates on DM Content",
        "I agree to pay the amount through cheque", "A free copy of Mastering The Interview",
        "Last Notable Activity"]
    cols_to_drop = ["Search", "Magazine", "Newspaper Article", "X Education Forums", "Newspaper",
                    "Digital Advertisement", "Through Recommendations",
                    "Receive More Updates About Our Courses", "Update me on Supply Chain Content",
                    "Get updates on DM Content", "I agree to pay the amount through cheque",
                    "A free copy of Mastering The Interview"]                   # [30]
    leads_df["Lead Source"] = leads_df["Lead Source"].replace(np.nan, "Google")  # [34]
    leads_df["Lead Source"] = leads_df["Lead Source"].replace("google", "Google")
    leads_df["Lead Source"] = leads_df["Lead Source"].replace(
        ["bing", "Click2call", "Press_Release", "youtubechannel", "welearnblog_Home", "WeLearn",
         "blog", "Pay per Click Ads", "testone", "NC_EDM", "Live Chat"], "Others")  # [35]
    leads_df["Country"] = leads_df["Country"].replace(np.nan, "not provided")   # [41]
    cols_to_drop.append("Country")                                              # [44]
    leads_df["What is your current occupation"] = leads_df["What is your current occupation"].replace(
        np.nan, "Not provided")                                                 # [48]
    leads_df["What matters most to you in choosing a course"] = leads_df[
        "What matters most to you in choosing a course"].replace(np.nan, "Better Career Prospects")  # [54]
    cols_to_drop.append("What matters most to you in choosing a course")       # [57]
    leads_df["Last Activity"] = leads_df["Last Activity"].replace(np.nan, "Email Opened")  # [61]
    leads_df["Last Activity"] = leads_df["Last Activity"].replace(
        ["Unreachable", "Unsubscribed", "Had a Phone Conversation", "Approached upfront",
         "View in browser link Clicked", "Email Marked Spam", "Email Received",
         "Resubscribed to emails", "Visited Booth in Tradeshow"], "Others")     # [62]
    cols_to_drop.append("Last Activity")                                        # [65] sales-team data
    leads_df = leads_df.dropna()                                                # [67]
    assert leads_df.shape == (9103, 25)                                         # [68]
    cols_to_drop.append("Do Not Call")                                          # [75]
    leads_df["Last Notable Activity"] = leads_df["Last Notable Activity"].replace(
        ["Had a Phone Conversation", "Email Marked Spam", "Unreachable", "Unsubscribed",
         "Email Bounced", "Resubscribed to emails", "View in browser link Clicked",
         "Approached upfront", "Form Submitted on Website", "Email Received"], "Others")  # [78]
    cols_to_drop.append("Last Notable Activity")                                # [81] sales-team data
    leads = leads_df.drop(cols_to_drop, axis=1)                                 # [83]
    assert leads.shape == (9103, 8)

    # ---- outlier capping at the 5th / 95th percentiles                          [96] [109]
    # (the notebook uses chained assignment leads[col][mask] = value, which modified `leads` in
    # place under the pandas 1.0 it ran; the X_train head check below confirms the capping happened)
    for col in ["TotalVisits", "Page Views Per Visit"]:
        percentiles = leads[col].quantile([0.05, 0.95]).values
        leads.loc[leads[col] <= percentiles[0], col] = percentiles[0]
        leads.loc[leads[col] >= percentiles[1], col] = percentiles[1]

    leads["Do Not Email"] = leads["Do Not Email"].map({"Yes": 1, "No": 0})      # [117]
    cat_cols = leads.select_dtypes(include=["object"]).columns                  # [121]
    assert list(cat_cols) == ["Lead Origin", "Lead Source", "What is your current occupation"]
    dummy = pd.get_dummies(leads[["Lead Origin"]], drop_first=True).astype("uint8")  # [122]
    leads = pd.concat([leads, dummy], axis=1)
    dummy = pd.get_dummies(leads["Lead Source"], prefix="Lead Source").astype("uint8")
    dummy = dummy.drop(["Lead Source_Others"], axis=1)
    leads = pd.concat([leads, dummy], axis=1)
    dummy = pd.get_dummies(leads["What is your current occupation"],
                           prefix="What is your current occupation").astype("uint8")
    dummy = dummy.drop(["What is your current occupation_Not provided"], axis=1)
    leads = pd.concat([leads, dummy], axis=1)
    leads = leads.drop(cat_cols, axis=1)                                        # [123]

    X = leads.drop("Converted", axis=1)                                         # [127]
    y = leads["Converted"]                                                      # [128]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, train_size=0.7, test_size=0.3, random_state=100)                  # [129]
    assert list(X_train.index[:5]) == SPLIT_HEAD["train"]                       # [132] head
    assert list(X_test.index[:5]) == SPLIT_HEAD["test"]                         # [219] head

    num_cols = X_train.select_dtypes(include=["float64", "int64"]).columns      # [132]
    assert list(num_cols) == ["Do Not Email", "TotalVisits", "Total Time Spent on Website",
                              "Page Views Per Visit"]
    scaler = StandardScaler()
    X_train[num_cols] = scaler.fit_transform(X_train[num_cols])
    assert np.allclose(X_train.loc[7962, list(num_cols)].astype(float).values,
                       [-0.294015, -0.068258, 1.476324, -0.423364], atol=5e-7)  # [132] head
    assert abs(X_train.loc[1566, "TotalVisits"] - 2.435517) < 5e-7             # capped at the 95th pct
    X_test = X_test.drop(["Lead Source_Olark Chat", "Lead Origin_Landing Page Submission"], axis=1)  # [136]
    X_train = X_train.drop(["Lead Source_Olark Chat", "Lead Origin_Landing Page Submission"], axis=1)  # [137]
    X_test_train_scaled = X_test.copy()
    X_test_train_scaled[num_cols] = scaler.transform(X_test[num_cols])
    # [219] the notebook RE-FITS the scaler on the test set
    num_cols_test = X_test.select_dtypes(include=["float64", "int64"]).columns
    assert list(num_cols_test) == list(num_cols)
    X_test = X_test.copy()
    X_test[num_cols_test] = StandardScaler().fit_transform(X_test[num_cols_test])
    assert np.allclose(X_test.loc[3504, list(num_cols)].astype(float).values,
                       [-0.293797, -0.058621, -0.108519, 0.416452], atol=5e-7)  # [219] head

    # ---- RFE with LogisticRegression() defaults, 15 features                   [140]
    assert list(X_train.columns) == list(RFE_RANKING_REPORTED)
    rfe = run_rfe(X_train, y_train, RFE_RANKING_REPORTED, 15, notes)

    # ---- final model #5                                                         [161]
    model = fit_mle(X_train[FINAL_FEATURES], y_train)
    coef = dict(zip(["const"] + FINAL_FEATURES, [model.intercept_[0]] + list(model.coef_[0])))
    max_coef_diff = max(abs(coef[k] - v) for k, v in COEF_REPORTED.items())
    print(f"final model: max |coef - notebook coef| = {max_coef_diff:.5f} (notebook prints 4 d.p.)")
    train_proba = model.predict_proba(X_train[FINAL_FEATURES].astype(float).values)[:, 1]
    test_proba = model.predict_proba(X_test[FINAL_FEATURES].astype(float).values)[:, 1]
    test_proba_ts = model.predict_proba(X_test_train_scaled[FINAL_FEATURES].astype(float).values)[:, 1]
    assert np.allclose(train_proba[:5], [0.733427, 0.150019, 0.223565, 0.968245, 0.308725], atol=5e-6)  # [167]
    assert np.allclose(test_proba[:5], [0.306096, 0.886499, 0.147829, 0.305665, 0.203766], atol=5e-6)   # [224]

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
        "Rows: 9,240 -> 9,103 (rows with missing TotalVisits/Page Views dropped). Columns with "
        ">=35% missing dropped (Specialization, How did you hear, Tags, Lead Quality, Lead Profile, "
        "City, Asymmetrique x4); Last Activity and Last Notable Activity dropped explicitly as "
        "sales-team data, so no post-contact column reaches the design matrix. TotalVisits and Page "
        "Views Per Visit capped at their 5th/95th percentiles computed on all 9,103 rows before the "
        "split. 'Lead Source_Olark Chat' and 'Lead Origin_Landing Page Submission' dropped by hand "
        "before RFE ([136]/[137]). Split 70/30 random_state=100, not stratified. The notebook "
        "re-fits StandardScaler on the test set ([219]) and 'Do Not Email' and 'Total Time Spent on "
        "Website' are final features; X_test reproduces that, X_test_train_scaled uses the train "
        f"scaler (test accuracy {ts['accuracy']:.4f} / AUC {ts['roc_auc']:.4f} with it). No test AUC "
        "is printed; train AUC 0.86 appears only in markdown.")
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
        sys.exit("usage: python ml/experiments/published/lohani.py <Leads.csv> [<out.pkl>]")
    reproduce(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
