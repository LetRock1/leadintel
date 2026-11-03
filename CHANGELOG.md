# Changelog

All notable changes to this project. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
the project uses [semantic versioning](https://semver.org/).

## [7.1.0] - 2026-10-25

One product that counts everything in rupees of extra profit: the pipeline shows what comes in anyway and what the
team can add, discount money is priced like call slots, coupons given by hand are checked first, and the owner gets a
planner. The lead score's update now takes what each of the CRM's own steps adds from its never-contacted control
group. Same database: migrations `0004_anchored_update`, `0005_money` and `0006_email_errors` add the new columns,
and 7.0 data is kept.

### Added

- **The pipeline in rupees** (`backend/app/services/money.py`, Pipeline page). For every open lead: what comes in
  anyway (the lead score times the fee) and what the team can add with the best step now, net of the prices; totals
  at the top and per stage; cards ordered by what the team can add (or by score); one line per card with **Do it**,
  which takes the step and logs it with its receipt; a "No discount needed" mark for likely buyers a coupon would only
  give money away to. The Overview page and Ask show the same numbers.
- **A priced monthly discount budget** (`backend/app/ml/budget.py`). Optional, set on the Planner page. Every rupee
  of expected discount gets a price, re-solved at each decision from the money left (budget minus discounts given and
  the expected cost of open coupons), the days left and the last 7 days of decisions; next-best-action counts every
  step net of the call-slot and discount prices. Decisions log each coupon's advantage, expected cost and price.
- **The coupon guard** (Coupons page, `GET /crm/coupons/check`). Before a coupon is given by hand: the chance to buy
  without and with it, the expected discount and how much of it would go to someone who would have paid in full. A
  coupon that does not pay, or goes over the budget, needs a confirmation; a coupon for a control-group lead is
  refused. Manual coupons are stored with their expected cost and source.
- **The owner's planner** (Planner page, `GET /crm/planner`, `PUT /crm/planner/settings` for the owner). The month in
  rupees, what the team's work adds against the control group (95% interval), whether one more counsellor pays for
  themselves (last week's decisions replayed with 8 more call slots a day), the discount budget with its meter and
  what ₹10,000 more would add, and the discount kept against a coupon for every left cart. Ask answers "Should we hire
  another counsellor?".
- **Each step's effect, measured from the never-contacted control group** (`backend/app/ml/anchor.py`,
  `learning.py`). At every update, for each next-best-action step the loop compares the leads it acted on with that
  step against the control-group leads it would have given the same step, and refits the lead score with that effect
  fixed, so the step cannot be learned as lead quality. Steps without 20 decision points on each side yet, campaign
  emails and the effects of time are learned from the data; with no control group the update works as in 7.0.
- **Start here**, the first page for a new team member (top of the menu, `GET /crm/start`): what the CRM does by
  itself, the first steps for a counsellor, a marketer and the owner, a live check of what is set up (email, writing
  help, team, learners, discount budget) and the CRM's words in plain language. A bar on every page points new people
  to it until they have opened it once.
- **A simpler Learning loop page**: how many outcomes the CRM learned from, the score's accuracy on never-contacted
  leads, expected against actual buying update by update, what the team's work adds after each step, how time changes
  the chance to buy, the learned corrections, every update, the real-time loop and the latest events.
- Experiments **E8** (`anchored_histories.py`, `anchored_check.py`: ways to update the score, on 11 histories of the
  product, judged on a 10% evaluation group never contacted or trained on), **E8b** (`exploration_check.py`: what the
  random learning steps cost, five runs in each of 14 simulated worlds) and **E9** (`money_check.py`: the discount
  budget, the coupon guard, the pipeline in rupees and the planner against known truth).
- Tests: 124 backend (the money features, Start here, the step effects with known truth, the migrations, email through a
  real SMTP conversation, two people acting at once) and 39 frontend.

### Changed

- The research comparisons (other ways to update the score, the research paper's cut-off estimator) moved out of the
  product into `docs/RESEARCH.md` and the experiments; the setting `learning.retrain_method` is gone.
- Plainer words on the Next-best-action and Model health pages (no "inverse propensity weighting"; "Learning steps"
  instead of "the random slice").
- The six-history report (`history_runs.md`), the lead-ageing study (E6) and the what-if paths study (E5) were re-run
  with this version; RESEARCH.md quotes the new numbers.
- The Overview's emails, clicks and purchases after a click are counted in one query instead of one per clicked email
  (1.3 s down to 0.04 s on a six-month install; the same numbers, checked on a copy of it and by a new test).
- The Coupons page counts every coupon (it showed at most 2,000 and called that the total: "2,000 coupons, 67 used"
  where there were 2,582 and 87) and pages through them on the server; "Used" and "Not used" now show all of them.
- **Emails that could not be sent are kept as such** (migration `0006_email_errors`): when the mail server refuses
  the login, cannot be reached or hits its daily limit, the email is marked with the reason instead of being counted
  as sent. Delivery counts on the Overview and Campaigns pages count only emails that went out; the lead's timeline
  says "Email not sent" and why; they are tried again automatically every 10 minutes for a day (six tries at most,
  never after the person opts out), and a campaign offers "Send the emails that did not go out again" (same links,
  same hold-out group).
- **Any mail server, not only Gmail**: `SMTP_HOST`, `SMTP_PORT` and `SMTP_SECURITY` (ssl, starttls, or none for a local
  relay) in `backend/.env`; Gmail stays the default.
- **When a person was last on the website**: the leads list and the lead page show their last visit (their own
  activity; the column used to show when the CRM last made a contact record), the list is ordered by it by default
  ("Latest contact record first" is still there), and the CSV export has it.
- The website says plainly that checkout is a demonstration payment ("nothing was charged") on the thank-you page and
  in the confirmation email, and promises a confirmation email only when email is set up.
- Sign-up codes appear in `backend/data/logs/api.out` at once (the output was block-buffered when written to a file,
  so a code could show up minutes late).
- Accessibility: the checkout's coupon box and the team's password boxes were labelled on their wrapper, not on the
  input (screen readers did not announce them); "Cart, 1 courses" now reads "Cart, 1 course".
- Ask the CRM answers counting questions ("How many leads came in this week?", "How many customers do we have?"),
  real people and simulated learners apart; it used to reply with the list of things it can do.
- Pages for admins only (Team, Audit log) opened from an old link or typed in now say "This page is not part of your
  role" instead of showing an admin page whose buttons fail.
- An email link opened once counts as one click (the website reported it twice while React checks its code in
  development, which is how the start scripts run it); the overview video and the brochure are recorded once too.
- Switching off a counsellor says where their leads go (to the other counsellors, or unassigned when there is none).
- Two people closing the same task or call-back at the same moment: the first one's outcome stands and the second is
  told so (before, both were told "Saved" and a second note was written).
- The unsubscribe page says "No more emails about courses" once it is done.
- A lead who signed up a moment ago gets their money line on the pipeline at once (the 30-second cache of the money
  view showed them with ₹0 and no step until it refreshed); a purchase or a deleted account leaves the totals at once.
- **Chances of buying, not rupees, for the team.** A lead's page, its decision receipt and what-if paths, Today's
  actions and the pipeline cards show the chance of buying and how much each step changes it ("6% → 9% with a 20%
  coupon email"), never a per-lead "+₹483 extra profit": nobody has paid anything yet. The decision still weighs fees,
  discounts, costs and the call-slot price inside; the owner's forecasts (Pipeline totals, Overview, Planner) and the
  Next-best-action page keep rupees. Decision explanations, the coupon guard and Ask's call list speak in chances.
- **At most one coupon a week per person**, used or not (`coupon_gap_days`), on top of one open coupon at a time.
- A lead who has not looked at a course yet says "Not chosen yet" instead of "Interested in Unknown".
- **One open coupon per person, a code of its own, and no step twice in a row by hand.** A person who still holds a
  coupon they can use is not given a second one, automatically or by hand (the coupon guard says so and refuses even
  when confirmed): in a six-month history 20% of coupon decisions had gone to someone who already held one, and the
  team could press "Send it now" again and again (five 20% coupon emails to one person in a minute). Every coupon has
  its own code (SMARTSTART20-K7Q2M instead of the same SMARTSTART20 for everyone; A/B test coupons too), which works
  only for that person.
  The same email step cannot be taken again by hand within 24 hours (`manual_repeat` in `crm_settings.json`), nor a
  second call or WhatsApp message while the first is waiting; the lead page says when, and the pipeline updates at
  once.
- **Real and simulated learners are treated the same** (new test): a real learner and a simulated one who do the
  same things get the same score, tier, decision receipt, money line, stage and coupon guard, and both count. On a
  copy of a six-month install whose 2,001 simulated learners were all relabelled as real people, the 25 CRM pages and
  11 Ask answers compared showed exactly the same numbers before and after; only the real/simulated split changed
  (`scripts/real_vs_simulated_check.py` repeats this check on a copy of any install).
- **A business with real learners only** (tested on a new install without simulated history and with the simulated
  learners switched off): the Journeys page no longer breaks before the first decisions (it crashed on a missing
  list); with `SIMULATION_ENABLED=false` the Simulation page and the menu say "Switched off" instead of "Running",
  and resuming or sending a simulated visit is refused with the reason; the planner states a month's coupon cost only
  from 30 paying decisions (it extrapolated from two); the Overview, Model health and Journeys explain what is not
  measured yet instead of showing empty charts, "None" or "0 everyone who signed up"; Start here counts only learners
  who entered their emailed code, like the Overview (a sign-up without the code was counted as a learner).

### Found

- The random learning steps cost money in simulation: with none, the CRM earned more in 12 of 14 worlds (E8b), and 5%
  was not clearly better than 15%. They stay at 15%, because without them nothing can be measured.
- In a CRM that follows leads up at later triggers, the research paper's cut-off estimator measures acting now
  against acting later, not against never contacting a lead; used to update the score it made the score worse when
  random steps were few (E8).

## [7.0.0] - 2026-10-20

A rebuild of the whole project as one repository with one API, two TypeScript apps on one design system, tests and
continuous integration. Data from 6.x is not migrated: the first start creates a fresh database, models and history.

### Added

- **Capacity-aware next-best-action.** Each call slot gets a price, re-solved at every decision from the last seven
  days of decisions and the slots left; a call is made only when it adds more than that price over the best step
  without a call. Shown on decision receipts, in a capacity meter on Today's actions and the Next-best-action page,
  and as a price chart. Experiment E7 (`ml/experiments/capacity_check.py`) compares it with first come, first
  served, a fixed price and the best allocation in hindsight.
- One-time codes are stored only as HMAC-SHA256 keyed hashes (migration `0003_hashed_codes`); simulated learners and
  test accounts on the reserved `.test` domain read their codes from an inbox table instead of being emailed.
- Changing or resetting a password signs out every other session (tokens carry a fingerprint of the password hash).
- Backend test suite (83 tests, pytest) on a temporary database, and frontend tests (25, Vitest, including component
  tests of the decision receipt and of signing out).
- GitHub Actions CI: Ruff, pytest, the emoji check, the API reference check, TypeScript, ESLint, Prettier, Vitest and
  production builds.
- `scripts/smoke_test.py` (end-to-end check of a running system), `scripts/latency_check.py` (event to new score,
  measured over HTTP), `scripts/check_no_emoji.py`, `scripts/api_reference.py` (writes `docs/API.md` and
  `docs/openapi.json` from the code).
- CI runs the backend tests on Python 3.10 and 3.12.
- Documentation: architecture, how it works, API reference, research results, development guide, demo guide.
- `start-all.sh` and `stop-all.sh` for macOS and Linux next to the Windows scripts; both install only what changed.
- An hourly housekeeping job that deletes expired one-time codes.
- Readiness endpoint `/api/ready` (database, models, background jobs) next to `/api/health`.
- The Learning loop page shows the honesty check in full: what the model in use, ours and a naive retrain
  expected the untouched control group to buy against what it bought, run by run, which model the usual check on
  the CRM's own outcomes would pick, what the CRM's own steps add and the learned effects of time. The Journeys
  page has a journey map (stage, step, reaction, outcome), and the Overview the CRM's impact against the control
  group and the open leads by score.

### Changed

- **Backend** restructured into a standard FastAPI layout (`api`, `schemas`, `services`, `ml`, `simulation`, `jobs`,
  `db`, `core`) serving both the website (`/api/v1`) and the CRM (`/api/v1/crm`) from one process and one SQLite
  database, with versioned Alembic migrations, typed settings (pydantic-settings) and a command-line tool
  (`python -m app.cli bootstrap | migrate | train | history | simulation | serve`).
- **Website and CRM** rebuilt in TypeScript with React 19, React Router 7, TanStack Query and Tailwind CSS 4, sharing
  one design system (`frontend/shared`) with light and dark themes, built for phone width, and written in plain
  sentence-case words without emoji.
- The research scripts run on the backend's own code (`ml/experiments`), each history in a temporary copy of the
  project, and `ml/run_experiments.py` reproduces every result.
- The owner's first password is written only to `backend/data/initial-admin-password.txt`, never to the log, and the
  file is deleted once the owner has chosen a password.
- An empty value in `backend/.env` now means "use the default", so `.env.example` can be copied as it is.

### Removed

- The separate user and marketing backends, their databases and the JavaScript frontends of 6.x.
- Hand-written decay rules (the score's time effects are learned), and the old one-off scripts in `ml/`
  (`first_run.py`, `generate_dataset.py`, `generate_history.py`, `train_model.py`, `train_uplift.py`,
  `live_simulation.py`, `nba_simulation.py`), replaced by the backend's command-line tool.

## [6.6.0] - 2026-10-12

The CRM as a team works with it: accounts with roles, lead owners, notes, lost leads, contact preferences, callbacks
and tasks with outcomes, the team report and the audit log. Only the learners are simulated.

## [6.5.0]

Learned lead age in the score (days since sign-up), checked on the control group.

## [6.4.0]

Benchmarks against published lead-scoring solutions on the real X Education data, and a precise feedback-bias metric
for the learning loop on real randomised data.
