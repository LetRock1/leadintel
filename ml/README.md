# Research

The experiments behind the paper. They import the backend's own code (`backend/app`), so what they measure is what
the CRM runs; studies that need whole simulated histories make each one in a temporary copy of the project, so your
own database and models are never touched.

```
ml/
  run_experiments.py      runs E1 to E9 and writes ml/results (fixed seeds)
  real_leads.py           loads the real X Education leads with only the columns a new lead has
  requirements.txt        matplotlib for the figures, on top of the backend's packages
  data/                   the two real public datasets (see data/README.md)
  experiments/            one script per study, plus _project.py (temporary project copies)
    published/            four public lead-scoring solutions, re-run exactly as their authors wrote them
  results/                the reports (.md), their numbers (.json) and figures/
```

Run from the project folder with the backend's Python after the first start (which trains the starting models):

```bash
pip install -r ml/requirements.txt
python ml/run_experiments.py            # E1 to E9, about 4 hours (E8 makes 11 simulated histories)
python ml/run_experiments.py quick      # without the slow studies (E2b, E6, E8, E8b), under an hour
python ml/run_experiments.py E9         # one experiment
```

What each experiment asks, its result and how it compares: [docs/RESEARCH.md](../docs/RESEARCH.md). The methods in
plain words: [docs/HOW_IT_WORKS.md](../docs/HOW_IT_WORKS.md).
