# The two real datasets

| File | What it is | Used by |
|---|---|---|
| `Leads.csv` | **X Education Lead Scoring dataset** (Kaggle): 9,240 real leads of an online-education company, 37 columns; `Converted` = became a customer (38.5%). | Testing the lead-scoring method on real data without leakage: E1 (`ml/experiments/model_benchmark.py`, only the 9 columns known before any contact), E1b (`ml/experiments/published_benchmark.py`, four public solutions re-run exactly on their own rows and inputs and compared with ours) and `backend/tests/test_no_leakage.py`. It does not train the CRM's own model: it has none of the website signals (video, pricing page, cart, checkout) the CRM scores on. |
| `hillstrom.csv` | **Kevin Hillstrom, MineThatData E-Mail Analytics and Data Mining Challenge (2008)**: 64,000 customers randomly assigned to a men's email, a women's email or no email (one third each); outcomes `visit`, `conversion` and `spend` in the next two weeks. The standard public benchmark for uplift modelling. | E2 (`ml/experiments/hillstrom_uplift.py`) and E3 (`ml/experiments/learning_loop.py`). |

Columns of `Leads.csv` that sales fills in after contacting a lead (Tags, Lead Quality, Lead Profile, Last Activity,
Last Notable Activity, the Asymmetrique scores) leak the outcome and are never used by our model;
`backend/tests/test_no_leakage.py` fails if one is. E1b uses them only where it re-runs other people's published
solutions (which used them), to show what they are worth.

Both are public datasets, kept here so every result in `ml/results/` can be reproduced with
`python ml/run_experiments.py`. If this repository is made public, check the licence terms on the original download
pages first.

Simulated data is made by code, never stored here: `backend/app/simulation/population.py` simulates the 60,000 leads
the starting lead model is trained on and the randomised campaign that gives next-best-action its starting knowledge
(`python -m app.cli train all`); `backend/app/simulation/history.py` makes the six-month starting history of simulated
learners (`python -m app.cli history create`), each of them marked as simulated in the CRM.
