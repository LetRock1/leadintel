"""
Faithful re-implementations of four public solutions of the X Education lead-scoring case study
(the same Leads.csv, byte for byte), used by ml/experiments/published_benchmark.py to compare our
method with them on THEIR OWN train/test split and inputs.

Each module re-implements one notebook step by step (cell numbers in the comments) with pandas,
numpy and scikit-learn only (the notebooks' statsmodels GLM is the same maximum-likelihood fit as an
unpenalised LogisticRegression), checks itself against what the notebook printed (row counts, the
first rows of the split, scaled values, coefficients, the first predicted probabilities), and
reproduces every printed confusion matrix exactly.

    reproduce(csv_path) -> dict with X_train / X_test (the full design matrix the notebook's feature
    selection could choose from), X_test_train_scaled (the test rows scaled with the scaler fitted on
    the training rows), y_train / y_test, train_index / test_index (row numbers in Leads.csv),
    final_features, cutoff, test_proba (the notebook's final model on its test rows), reported /
    reproduced metrics, leaky_final_features, leaky_columns_in_design, notes.

The notebooks (public GitHub repositories, commits checked on 8 October 2026):
"""
SOLUTIONS = [
    {"key": "lsc", "module": "lsc", "label": "shinde-chandrakant / Lead-Scoring-Case-Study",
     "url": "https://github.com/shinde-chandrakant/Lead-Scoring-Case-Study", "commit": "f87f8bc"},
    {"key": "sivagiri", "module": "sivagiri", "label": "Sivagiri12 / Lead-Scoring-Case-Study---Sivagiri",
     "url": "https://github.com/Sivagiri12/Lead-Scoring-Case-Study---Sivagiri", "commit": "06d99b2"},
    {"key": "lscv1", "module": "lscv1", "label": "ShahadShaikh / Lead_Score_Case_Study",
     "url": "https://github.com/ShahadShaikh/Lead_Score_Case_Study", "commit": "123119e"},
    {"key": "lohani", "module": "lohani", "label": "garima2811 / Lead_Scoring_Case_Study (Lohani & Bansal)",
     "url": "https://github.com/garima2811/Lead_Scoring_Case_Study", "commit": "f15474f"},
]
