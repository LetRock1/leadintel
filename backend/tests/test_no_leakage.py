"""
No leakage into the models or the research numbers.

1. The CRM's own lead model only uses inputs the website records before anyone contacts the lead.
2. The real-data benchmark (ml/real_leads.py, 9,240 real X Education leads) never reads a column that is only known
   after sales has contacted the lead (Tags, Lead Quality, Last Activity, Asymmetrique scores ...). Those columns make
   a score look far better than it can be for a new lead (AUC about 0.98).
3. In the comparison with published solutions (ml/experiments/published_benchmark.py), our new-lead model gets exactly
   those leak-free columns.
"""

from __future__ import annotations

import inspect
import re
import sys
from pathlib import Path

import joblib
import pytest

from app.ml import features as F
from app.ml.training import lead

ROOT = Path(__file__).resolve().parents[2]
ALLOWED_SOURCE_COLUMNS = {
    "Lead Origin",
    "Lead Source",
    "Do Not Email",
    "Do Not Call",
    "TotalVisits",
    "Total Time Spent on Website",
    "Page Views Per Visit",
    "What is your current occupation",
    "Specialization",
    "Converted",
}
SALES_ENTERED = {"Tags", "LeadQuality", "LeadProfile", "LastActivity", "LastNotableActivity"}


@pytest.fixture(scope="module")
def research_modules():
    for p in (str(ROOT / "ml"), str(ROOT / "ml" / "experiments")):
        if p not in sys.path:
            sys.path.insert(0, p)
    import real_leads

    return real_leads


def test_the_lead_model_uses_only_what_the_website_records():
    assert not set(F.MODEL_COLUMNS) & SALES_ENTERED
    bundle = joblib.load(lead.MODEL_PATH)
    assert list(bundle["starter"].feature_names_in_) == list(F.MODEL_COLUMNS)
    assert F.TARGET not in F.MODEL_COLUMNS


def test_the_real_data_benchmark_reads_no_post_contact_column(research_modules):
    rl = research_modules
    source = inspect.getsource(rl.load_real_leads)
    for col in rl.LEAKY_COLUMNS:
        assert f'"{col}"' not in source and f"'{col}'" not in source, f"leaky column read: {col}"
    read = set(re.findall(r'd\["([^"]+)"\]', source))
    assert read <= ALLOWED_SOURCE_COLUMNS, f"unexpected columns read: {sorted(read - ALLOWED_SOURCE_COLUMNS)}"
    rows, y = rl.load_real_leads()
    assert len(rows) == 9240
    assert set(rows[0]) == set(rl.REAL_COLUMNS)


def test_the_published_comparison_gives_our_model_the_same_columns(research_modules):
    rl = research_modules
    import published_benchmark as pb

    frame, _ = pb.new_lead_frame()
    assert list(frame.columns) == list(rl.REAL_COLUMNS)
    pipe = pb.new_lead_model()
    used = sorted(c for _, _, cols in pipe.named_steps["prep"].transformers for c in cols)
    assert used == sorted(rl.REAL_COLUMNS)
