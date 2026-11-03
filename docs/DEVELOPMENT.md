# Development

How to work on the code: running the parts separately, the checks every change must pass, and the conventions the
code follows. To simply run the project, use `start-all.bat` (Windows) or `./start-all.sh` (macOS, Linux) instead.

## Requirements

- Python 3.10 or newer (3.12 recommended)
- Node.js 20.19 or newer (22 LTS recommended)
- Git, and an editor that reads `.editorconfig`

## The API (backend/)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate              # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt    # the API's packages plus pytest, httpx and ruff
python -m app.cli bootstrap            # database, starting models and the simulated history (first time ~12 min)
python -m app.cli serve                # http://127.0.0.1:8000, interactive docs at /api/docs
```

`python -m app.cli bootstrap --skip-history` prepares only the database and the models (about two minutes), for work
that does not need the six months of simulated learners. Other commands:

| Command | What it does |
|---|---|
| `python -m app.cli migrate` | create or upgrade the database schema |
| `python -m app.cli train lead\|uplift\|all` | train the starting models again |
| `python -m app.cli history create [--n 2000 --days 180 --seed 2026]` | make the simulated starting history |
| `python -m app.cli history remove` | delete every simulated learner and restore the starting models |
| `python -m app.cli simulation status\|reset\|self-check` | the live simulated learners |

Run the API with **one worker**: the background jobs run inside the process, and two workers would run every job
twice. `uvicorn app.main:app --reload` is fine while coding.

## The website and the CRM (frontend/)

```bash
cd frontend
npm ci                  # one install for the three workspaces: shared, web, crm
npm run dev:web         # the website on http://localhost:5173
npm run dev:crm         # the CRM on http://localhost:5174
```

Both dev servers send `/api` to the backend at `API_URL` (default `http://127.0.0.1:8000`), so the browser talks to
one origin and no CORS set-up is needed in development.

- `shared/` holds the design tokens (`src/styles/tokens.css`, light and dark), the UI primitives (`src/ui`) and the
  helpers (`src/lib`: formatting in Indian English, the HTTP client, the theme, chart colours). Both apps import it
  as `@xedu/shared/ui` and `@xedu/shared/lib`.
- Data comes from the API through TanStack Query; each app keeps its API calls in `src/api` (client, types, queries).
- Routes are declared once in `src/app/router.tsx`, with lazy-loaded pages and an error page per route.

## Checks (the same ones CI runs)

From the project folder, with the backend's environment active:

```bash
ruff check .                              # lint: backend, ml and scripts
ruff format --check .                     # formatting (ruff format . to fix)
python scripts/check_no_emoji.py          # no emoji in code, settings or documents
python scripts/api_reference.py --check   # docs/API.md matches the code (run without --check to update it)
cd backend && python -m pytest            # 124 tests, a few minutes; they use a temporary database
```

And in `frontend/`:

```bash
npm run typecheck       # TypeScript, strict, all three workspaces
npm run lint            # ESLint (recommended, typescript-eslint, React hooks, fast refresh)
npm run format:check    # Prettier (npm run format to fix)
npm test                # Vitest: formatting, tokens, labels, receipt, signing out, money lines, planner verdicts
npm run build           # production builds of the website and the CRM
```

`scripts/smoke_test.py` checks a *running* backend end to end over HTTP (every CRM page's data and a learner's whole
journey) and cleans up after itself; it asks for a CRM admin password.

`scripts/real_vs_simulated_check.py` checks that the CRM treats real people exactly like simulated learners: on a
copy of `backend/data` (your data is never changed) it reads every CRM page and a set of Ask answers, turns every
simulated learner into a real person (only the email domain changes), reads them again and compares; only the
real/simulated split may change. It runs its own API on the copy (port 8765) and asks for a CRM admin password.

GitHub Actions runs all of these on every push and pull request (`.github/workflows/ci.yml`).

## Changing the database

The schema is changed only by migrations (`backend/app/db/migrations/versions`), never by hand:

```bash
cd backend
alembic revision -m "what changes"   # writes a new file in app/db/migrations/versions
# write upgrade() and downgrade() with op.execute(...) or op.batch_alter_table(...) (SQLite needs batch mode
# to drop or change columns)
python -m app.cli migrate            # applies it; every start also applies pending migrations
```

`backend/tests/test_migrations.py` checks that the history is linear and that every migration goes down and up again.

## Conventions

**Python.** Ruff with a 120-character line, rules E, F, W, I, B, UP, BLE and SIM (`ruff.toml`). Type hints on public
functions. Modules start with a docstring that says what they are for. Business logic lives in `services` or `ml`,
never in a router. Errors a person can act on are raised as `HTTPException` (or `app.core.errors`) with a sentence
that says what to do; everything else is logged with the request id. A broad `except Exception` needs a comment that
says why the failure must not stop the caller.

**TypeScript.** Strict mode, Prettier with a 120-character line, ESLint with the React hooks rules. Components and
hooks live in separate files from contexts, so fast refresh works. No `any`.

**Words on screen.** Sentence case; plain words a learner or a counsellor would use ("call", "email", "counsellor");
a button says what happens ("Save changes", not "Submit"); an error says what went wrong and how to fix it; numbers
use Indian grouping (₹1,25,000) through `@xedu/shared/lib`. No emoji anywhere, in the code or the interface (checked
by `scripts/check_no_emoji.py`).

**Settings.** Anything that differs between computers goes in `backend/.env` (documented in `.env.example`);
anything the business may tune goes in `crm_settings.json`. Never commit secrets: `backend/.env` and `backend/data/`
are ignored, and a test checks that `.env.example` holds no values for passwords or keys.
