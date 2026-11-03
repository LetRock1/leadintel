"""Faithful re-implementation of shinde-chandrakant/Lead-Scoring-Case-Study, LeadScoring.ipynb.

usage: python ml/experiments/published/lsc.py <path to Leads.csv> [<output .pkl path>]

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

NAME = "lsc"
REPO = "https://github.com/shinde-chandrakant/Lead-Scoring-Case-Study (LeadScoring.ipynb)"
LEAKY_SOURCES = ["Tags", "Lead Quality", "Lead Profile", "Last Activity", "Last Notable Activity",
                 "Asymmetrique Activity Index", "Asymmetrique Profile Index",
                 "Asymmetrique Activity Score", "Asymmetrique Profile Score"]

# ---- what the notebook printed ---------------------------------------------------------------
RFE_SELECTED_REPORTED = [  # [127]
    "Do Not Email", "Lead Origin_Lead Add Form", "Lead Source_Welingak Website", "Tags_Busy",
    "Tags_Closed by Horizzon", "Tags_Lost to EINS", "Tags_Ringing",
    "Tags_Will revert after reading the email", "Tags_invalid number", "Tags_number not provided",
    "Tags_switched off", "Tags_wrong number given", "Lead Quality_Not Sure", "Lead Quality_Worst",
    "Last Notable Activity_SMS Sent"]
RFE_RANKING_REPORTED = {  # [126] list(zip(X_train.columns, rfe.support_, rfe.ranking_))
    "Do Not Email": 1, "TotalVisits": 43, "Total Time Spent on Website": 4, "Page Views Per Visit": 41, "Lead Origin_Landing Page Submission": 20, "Lead Origin_Lead Add Form": 1, "Lead Origin_Lead Import": 3, "Lead Source_Facebook": 49, "Lead Source_Google": 45, "Lead Source_Olark Chat": 6, "Lead Source_Organic Search": 46, "Lead Source_Others": 48, "Lead Source_Reference": 72, "Lead Source_Referral Sites": 54, "Lead Source_Welingak Website": 1, "Last Activity_Email Bounced": 51, "Last Activity_Email Link Clicked": 39, "Last Activity_Email Opened": 71, "Last Activity_Form Submitted on Website": 73, "Last Activity_Had a Phone Conversation": 13, "Last Activity_Olark Chat Conversation": 17, "Last Activity_Others": 34, "Last Activity_Page Visited on Website": 40, "Last Activity_SMS Sent": 8, "Last Activity_Unreachable": 18, "Last Activity_Unsubscribed": 22, "Last Activity_View in browser link Clicked": 35, "Specialization_Business Administration": 62, "Specialization_E-Business": 69, "Specialization_E-COMMERCE": 19, "Specialization_Finance Management": 44, "Specialization_Healthcare Management": 42, "Specialization_Hospitality Management": 63, "Specialization_Human Resource Management": 57, "Specialization_IT Projects Management": 66, "Specialization_International Business": 27, "Specialization_Marketing Management": 37, "Specialization_Media and Advertising": 38, "Specialization_Operations Management": 70, "Specialization_Others": 24, "Specialization_Retail Management": 58, "Specialization_Rural and Agribusiness": 52, "Specialization_Services Excellence": 59, "Specialization_Supply Chain Management": 50, "Specialization_Travel and Tourism": 28, "What is your current occupation_Housewife": 47, "What is your current occupation_Other": 56, "What is your current occupation_Student": 10, "What is your current occupation_Unemployed": 2, "What is your current occupation_Working Professional": 30, "Tags_Busy": 1, "Tags_Closed by Horizzon": 1, "Tags_Diploma holder (Not Eligible)": 14, "Tags_Graduation in progress": 60, "Tags_In confusion whether part time or DLP": 32, "Tags_Interested  in full time MBA": 21, "Tags_Interested in other courses": 12, "Tags_Lost to EINS": 1, "Tags_Not doing further education": 15, "Tags_Others": 23, "Tags_Ringing": 1, "Tags_Will revert after reading the email": 1, "Tags_in touch with EINS": 9, "Tags_invalid number": 1, "Tags_number not provided": 1, "Tags_opp hangup": 25, "Tags_switched off": 1, "Tags_wrong number given": 1, "Lead Quality_Low in Relevance": 68, "Lead Quality_Might be": 11, "Lead Quality_Not Sure": 1, "Lead Quality_Worst": 1, "City_Other Cities": 53, "City_Other Cities of Maharashtra": 67, "City_Other Metro Cities": 64, "City_Thane & Outskirts": 55, "City_Tier II Cities": 29, "Last Notable Activity_Email Link Clicked": 16, "Last Notable Activity_Email Opened": 65, "Last Notable Activity_Had a Phone Conversation": 31, "Last Notable Activity_Modified": 7, "Last Notable Activity_Olark Chat Conversation": 5, "Last Notable Activity_Others": 61, "Last Notable Activity_Page Visited on Website": 26, "Last Notable Activity_SMS Sent": 1, "Last Notable Activity_Unreachable": 33, "Last Notable Activity_Unsubscribed": 36}
# [139] [142] [145]: dropped by p-value: Tags_invalid number, Tags_number not provided, Tags_wrong number given
FINAL_FEATURES = [  # col3, model logm4 [145]
    "Do Not Email", "Lead Origin_Lead Add Form", "Lead Source_Welingak Website", "Tags_Busy",
    "Tags_Closed by Horizzon", "Tags_Lost to EINS", "Tags_Ringing",
    "Tags_Will revert after reading the email", "Tags_switched off", "Lead Quality_Not Sure",
    "Lead Quality_Worst", "Last Notable Activity_SMS Sent"]
COEF_REPORTED = {  # [145] logm4 summary
    "const": -1.9192, "Do Not Email": -1.2835, "Lead Origin_Lead Add Form": 1.2035,
    "Lead Source_Welingak Website": 3.2825, "Tags_Busy": 3.8043, "Tags_Closed by Horizzon": 7.9789,
    "Tags_Lost to EINS": 9.1948, "Tags_Ringing": -1.8121,
    "Tags_Will revert after reading the email": 3.9906, "Tags_switched off": -2.4456,
    "Lead Quality_Not Sure": -3.5218, "Lead Quality_Worst": -3.9106,
    "Last Notable Activity_SMS Sent": 2.7395}
CUTOFF = 0.25  # [187]/[191]/[199]: 0.25 from the precision-recall curve is applied to the test set
#               ([168] picked 0.2 from the sensitivity/specificity curve; identical train metrics)
REPORTED = {
    "train": {  # [170] [172] (cut-off 0.2) == [189] [190] (cut-off 0.25); AUC [161]
        "cutoff": 0.25, "n": 6351, "confusion": [[3690, 215], [349, 2097]],
        "accuracy": 0.911195087387813, "sensitivity": 0.857318070318888,
        "specificity": 0.9449423815620999, "precision": 0.9070069204152249,
        "npv": 0.9135924733845011, "fpr": 0.05505761843790013, "f1": None,
        "roc_auc": 0.9488012517235278},
    "test": {  # [200] [201] [204] [206]
        "cutoff": 0.25, "n": 2723, "confusion": [[1640, 94], [157, 832]],
        "accuracy": 0.9078222548659567, "sensitivity": 0.8412537917087968,
        "specificity": 0.9457900807381776, "precision": 0.8984881209503239,
        "npv": 0.9126321647189761, "fpr": 0.05420991926182238, "f1": None,
        "roc_auc": 0.9388647090311768},
    "extra": {"test_f1_class1_classification_report_2dp": 0.87,
              "train_f1_class1_classification_report_2dp": 0.88},
    "source": "printed outputs of cells [161] [170] [172] [189] [190] [200] [201] [204] [206]",
}
SPLIT_HEAD = {"train": [3009, 1012, 9226, 4750, 7987], "test": [3271, 1490, 7936, 4216, 3830]}


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
    lead_df = pd.read_csv(csv_path)                                            # [6]
    assert lead_df.shape == (9240, 37)

    # ---- Step 2: data cleaning
    lead_df = lead_df.drop(["Lead Number", "Prospect ID"], axis=1)            # [14]
    lead_df = lead_df.replace("Select", np.nan)                                 # [16]
    pct = round(100 * (lead_df.isnull().sum() / len(lead_df.index)), 2)
    lead_df = lead_df.drop(lead_df.loc[:, list(pct > 52)].columns, axis=1)    # [19]
    assert "Lead Profile" not in lead_df and "How did you hear about X Education" not in lead_df
    assert "Lead Quality" in lead_df                                            # 51.59% kept
    lead_df["Lead Quality"] = lead_df["Lead Quality"].replace(np.nan, "Not Sure")  # [25]
    asym_list = ["Asymmetrique Activity Index", "Asymmetrique Profile Index",
                 "Asymmetrique Activity Score", "Asymmetrique Profile Score"]
    lead_df = lead_df.drop(asym_list, axis=1)                                   # [29]
    lead_df["City"] = lead_df["City"].replace(np.nan, "Mumbai")                 # [33]
    lead_df["Specialization"] = lead_df["Specialization"].replace(np.nan, "Others")  # [36]
    for var in ["Tags", "What matters most to you in choosing a course",
                "What is your current occupation", "Country"]:                  # [37] [39]
        top_frequent = lead_df[var].describe()["top"]
        lead_df[var] = lead_df[var].replace(np.nan, top_frequent)
    lead_df.dropna(inplace=True)                                                # [45]
    assert len(lead_df) == 9074                                                 # [54] count 9074

    # ---- outlier capping at the 95th percentile                                 [57]
    for var in ["TotalVisits", "Page Views Per Visit"]:
        percentile = lead_df[var].quantile([0.95]).values
        lead_df.loc[lead_df[var] >= percentile[0], var] = percentile[0]   # notebook used chained assignment
    assert lead_df["TotalVisits"].max() == 10.0                                 # [105] max 10

    # ---- category merging
    lead_df["Lead Source"] = lead_df["Lead Source"].replace(["google"], "Google")  # [69]
    categories = lead_df["Lead Source"].unique()                                # [70]
    assert list(categories) == ["Olark Chat", "Organic Search", "Direct Traffic", "Google",
                                "Referral Sites", "Reference", "Welingak Website", "Facebook",
                                "blog", "Pay per Click Ads", "bing", "Social Media", "WeLearn",
                                "Click2call", "Live Chat", "welearnblog_Home", "youtubechannel",
                                "testone", "Press_Release", "NC_EDM"]
    lead_df["Lead Source"] = lead_df["Lead Source"].replace(list(categories[8:]), "Others")  # [71]
    categories = lead_df["Last Activity"].unique()                              # [77]
    assert list(categories[-5:]) == ["Visited Booth in Tradeshow", "Approached upfront",
                                     "Resubscribed to emails", "Email Received", "Email Marked Spam"]
    lead_df["Last Activity"] = lead_df["Last Activity"].replace(list(categories[-5:]), "Others")  # [79]
    categories = lead_df["Tags"].unique()                                       # [91]
    assert list(categories[-8:]) == ["Still Thinking", "Lost to Others",
                                     "Shall take in the next coming month", "Lateral student",
                                     "Interested in Next batch", "Recognition issue (DEC approval)",
                                     "Want to take admission but has financial problems",
                                     "University not recognized"]
    lead_df["Tags"] = lead_df["Tags"].replace(list(categories[-8:]), "Others")  # [93]
    categories = lead_df["Last Notable Activity"].unique()                      # [97]
    assert list(categories[-6:]) == ["Approached upfront", "Resubscribed to emails",
                                     "View in browser link Clicked", "Form Submitted on Website",
                                     "Email Received", "Email Marked Spam"]
    lead_df["Last Notable Activity"] = lead_df["Last Notable Activity"].replace(
        list(categories[-6:]), "Others")                                        # [99]
    lead_df = lead_df.drop(["Do Not Call", "Country", "What matters most to you in choosing a course",
                            "Search", "Magazine", "Newspaper Article", "X Education Forums",
                            "Newspaper", "Digital Advertisement", "Through Recommendations",
                            "Receive More Updates About Our Courses",
                            "Update me on Supply Chain Content", "Get updates on DM Content",
                            "I agree to pay the amount through cheque",
                            "A free copy of Mastering The Interview"], axis=1)   # [102]
    assert lead_df.shape == (9074, 14)                                          # [104]

    # ---- Step 4: data preparation
    lead_df["Do Not Email"] = lead_df["Do Not Email"].map({"Yes": 1, "No": 0})  # [107]
    cat_var = list(lead_df.columns[lead_df.dtypes == "object"])                 # [110]
    assert cat_var == ["Lead Origin", "Lead Source", "Last Activity", "Specialization",
                       "What is your current occupation", "Tags", "Lead Quality", "City",
                       "Last Notable Activity"]
    dummy = pd.get_dummies(lead_df[cat_var], drop_first=True).astype("uint8")   # [111] (uint8 as in pandas<2)
    lead_df = pd.concat([lead_df, dummy], axis=1)
    lead_df = lead_df.drop(cat_var, axis=1)
    assert lead_df.shape == (9074, 88)                                          # [112] 88 columns

    X = lead_df.drop(["Converted"], axis=1)                                     # [115]
    y = lead_df["Converted"]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, train_size=0.7, test_size=0.3, random_state=100)                  # [116]
    assert list(X_train.index[:5]) == SPLIT_HEAD["train"]                       # [121] head
    assert list(X_test.index[:5]) == SPLIT_HEAD["test"]                         # [193] head

    num_var = ["TotalVisits", "Total Time Spent on Website", "Page Views Per Visit"]  # [53] [120]
    scaler = StandardScaler()
    X_train[num_var] = scaler.fit_transform(X_train[num_var])                   # [121]
    # test matrix scaled with the TRAIN scaler (correct practice; not what the notebook did)
    X_test_train_scaled = X_test.copy()
    X_test_train_scaled[num_var] = scaler.transform(X_test[num_var])
    # [193] the notebook RE-FITS the scaler on the test set: X_test[num_var] = scaler.fit_transform(...)
    X_test = X_test.copy()
    X_test[num_var] = StandardScaler().fit_transform(X_test[num_var])
    notes.append("Notebook re-fits StandardScaler on the test set ([193] scaler.fit_transform(X_test)); "
                 "X_test reproduces that. No numeric column is among the final features, so it does "
                 "not affect the final model's test predictions. X_test_train_scaled uses the "
                 "train-fitted scaler instead.")

    # ---- Step 5: RFE with LogisticRegression() defaults, 15 features             [124] [125]
    assert list(X_train.columns) == list(RFE_RANKING_REPORTED)                  # same design columns, same order
    assert sorted(RFE_SELECTED_REPORTED) == sorted(c for c, k in RFE_RANKING_REPORTED.items() if k == 1)
    rfe = run_rfe(X_train, y_train, RFE_RANKING_REPORTED, 15, notes)

    # ---- final model (logm4) on the notebook's final features                    [145]
    model = fit_mle(X_train[FINAL_FEATURES], y_train)
    coef = dict(zip(["const"] + FINAL_FEATURES, [model.intercept_[0]] + list(model.coef_[0])))
    max_coef_diff = max(abs(coef[k] - v) for k, v in COEF_REPORTED.items())
    print(f"final model: max |coef - notebook coef| = {max_coef_diff:.5f} (notebook prints 4 d.p.)")
    train_proba = model.predict_proba(X_train[FINAL_FEATURES].astype(float).values)[:, 1]
    test_proba = model.predict_proba(X_test[FINAL_FEATURES].astype(float).values)[:, 1]
    test_proba_ts = model.predict_proba(X_test_train_scaled[FINAL_FEATURES].astype(float).values)[:, 1]

    reproduced = {"train": metrics_at(y_train, train_proba, CUTOFF),
                  "test": metrics_at(y_test, test_proba, CUTOFF),
                  "extra": {"train_at_0.2": metrics_at(y_train, train_proba, 0.2),
                            "test_with_train_fitted_scaler": metrics_at(y_test, test_proba_ts, CUTOFF),
                            "max_abs_coef_diff_vs_notebook": max_coef_diff,
                            "coefficients": coef, "rfe": rfe}}
    print("TRAIN (cut-off %.2f):" % CUTOFF)
    show(REPORTED["train"], reproduced["train"])
    print("TEST  (cut-off %.2f):" % CUTOFF)
    show(REPORTED["test"], reproduced["test"])

    design_cols = list(X_train.columns)
    leaky_in_design = [s for s in LEAKY_SOURCES if any(c == s or c.startswith(s + "_") for c in design_cols)]
    leaky_final = [c for c in FINAL_FEATURES if any(c == s or c.startswith(s + "_") for s in LEAKY_SOURCES)]
    notes.append("Rows: 9,240 -> 9,074 after dropping rows with any missing value (Lead Source, "
                 "TotalVisits, Page Views Per Visit, Last Activity); split 70/30 random_state=100, "
                 "not stratified. Columns with >52% missing dropped (How did you hear, Lead Profile); "
                 "Lead Quality (51.59% missing) deliberately kept with NaN -> 'Not Sure'; Asymmetrique "
                 "x4 dropped by hand; Tags NaN -> mode 'Will revert after reading the email'. "
                 "TotalVisits and Page Views Per Visit capped at the 95th percentile of all 9,074 rows "
                 "before the split. Test cut-off 0.25 (precision-recall); train metrics are identical "
                 "at 0.2 (sensitivity-specificity choice).")
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
        sys.exit("usage: python ml/experiments/published/lsc.py <Leads.csv> [<out.pkl>]")
    reproduce(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
