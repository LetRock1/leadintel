# API reference

Generated from the backend's OpenAPI description by `scripts/api_reference.py`; do not edit by hand. The running
backend serves the same reference interactively at http://127.0.0.1:8000/api/docs (try any request there) and the
machine-readable description at `/api/openapi.json` (also saved as [openapi.json](openapi.json)).

## Conventions

- Two APIs share one server. `/api/v1/...` is the learner website's API, `/api/v1/crm/...` the CRM team's API.
- Sign-in returns a JSON Web Token; send it as `Authorization: Bearer <token>`. Learner and team tokens have
  different audiences, so neither opens the other API. A token stops working when its account's password changes.
- Team roles are checked on every request: **admin** (everything), **marketing** (campaigns, A/B tests, coupons,
  exports, the learning loop) and **counsellor** (leads, today's actions, callbacks, pipeline, questions; changes
  only their own leads and unassigned ones). Reading campaigns and tests is open to the whole team.
- Errors are JSON: `{"detail": "a sentence a person can act on"}` with the usual status codes (400 invalid input,
  401 not signed in, 403 not allowed for this role, 404 not found, 409 conflict, 422 malformed request,
  429 too many attempts, 503 a dependency such as email is unavailable).
- Every response carries `X-Request-ID` (sent back when the caller supplies one) and the security headers
  `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` and `Cache-Control: no-store`.
- Times are the server's local time as `YYYY-MM-DD HH:MM:SS`; money is in Indian rupees.

125 routes in 16 groups.

## Health

| Method | Path | What it does |
|---|---|---|
| GET | `/api/health` | The process answers |
| GET | `/api/ready` | Database, models and background jobs |

## Learner accounts

| Method | Path | What it does |
|---|---|---|
| POST | `/api/v1/auth/signup` | Create an account and email a verification code |
| POST | `/api/v1/auth/verify-otp` | Verify the sign-up code and sign in |
| POST | `/api/v1/auth/login` | Sign in |
| GET | `/api/v1/auth/me` | The signed-in learner and their profile |
| POST | `/api/v1/auth/resend-otp` | Send a new sign-up code |
| POST | `/api/v1/auth/forgot-password` | Email a password reset code |
| POST | `/api/v1/auth/reset-password` | Set a new password with the reset code |
| POST | `/api/v1/auth/change-password` | Change the password of the signed-in learner |

## Learner profile and privacy

| Method | Path | What it does |
|---|---|---|
| GET | `/api/v1/profile/options` | The choices the profile form offers (the lead model's own vocabulary) |
| POST | `/api/v1/profile/complete` | Save the profile (occupation, specialisation, city, phone) |
| PUT | `/api/v1/profile/preferences` | Contact preferences: email, calls, WhatsApp, phone number |
| GET | `/api/v1/dashboard` | Everything on the learner's own dashboard |
| GET | `/api/v1/coupons` | The learner's coupons |
| GET | `/api/v1/me/insights` | What the CRM currently thinks about the signed-in learner (demo view) |
| GET | `/api/v1/live-score` | The learner's current score |
| DELETE | `/api/v1/me` | Delete the account and every record linked to it (right to erasure) |

## Learner activity

| Method | Path | What it does |
|---|---|---|
| POST | `/api/v1/session/start` | Start a visit (a new tab, or after 30 minutes idle) |
| POST | `/api/v1/session/ping` | Still here (every 30 s while the page is in use) |
| POST | `/api/v1/track` | Record one event and re-score the learner |
| POST | `/api/v1/email/click` | An email's button was opened (reported by the course page) |
| POST | `/api/v1/email/unsubscribe` | One-click unsubscribe from marketing emails |

## Courses

| Method | Path | What it does |
|---|---|---|
| GET | `/api/v1/courses` | Every course (titles, prices and facts come from the server) |
| GET | `/api/v1/faq` | Answers to common questions (the same text the help assistant uses) |
| GET | `/api/v1/courses/{slug}` | One course |
| GET | `/api/v1/recommendations` | Courses for the signed-in learner |
| GET | `/api/v1/reviews/{course_slug}` | Reviews of a course (by enrolled learners only) |
| POST | `/api/v1/reviews` | Review a course you are enrolled in |
| GET | `/api/v1/qna/{course_slug}` | Questions and answers on a course page |
| POST | `/api/v1/qna` | Ask a question about a course |

## Cart and checkout

| Method | Path | What it does |
|---|---|---|
| GET | `/api/v1/cart` | The learner's cart |
| POST | `/api/v1/cart` | Add a course to the cart |
| DELETE | `/api/v1/cart/{course_slug}` | Remove a course from the cart |
| GET | `/api/v1/wishlist` | The learner's wishlist |
| POST | `/api/v1/wishlist` | Save a course to the wishlist |
| DELETE | `/api/v1/wishlist/{course_slug}` | Remove a course from the wishlist |
| POST | `/api/v1/checkout/start` | The learner opened the checkout page |
| POST | `/api/v1/coupons/check` | Check a coupon before paying |
| POST | `/api/v1/checkout` | Pay for the cart (simulated payment: nothing is charged) |
| GET | `/api/v1/purchases` | The learner's enrolments |
| POST | `/api/v1/enquiry` | Ask about a course (always confirmed by email) |

## Help and call-backs

| Method | Path | What it does |
|---|---|---|
| POST | `/api/v1/chat` | Ask the website's help assistant |
| POST | `/api/v1/callback` | Ask a counsellor to call back |

## CRM sign-in

| Method | Path | What it does |
|---|---|---|
| POST | `/api/v1/crm/auth/login` | Sign in to the CRM |
| GET | `/api/v1/crm/me` | The signed-in person, what their role may do, and the team |
| POST | `/api/v1/crm/me/password` | Change your own password |

## CRM dashboard

| Method | Path | What it does |
|---|---|---|
| GET | `/api/v1/crm/stats` | Headline numbers |
| GET | `/api/v1/crm/stats/daily` | Sign-ups, purchases and revenue per day |
| GET | `/api/v1/crm/forecast` | Revenue to expect from open leads, with a 90% range |
| GET | `/api/v1/crm/priority-queue` | Open leads with the highest expected value |
| GET | `/api/v1/crm/model/health` | Calibration of the lead score on people whose outcome is known |
| GET | `/api/v1/crm/nba/performance` | How well next-best-action is doing (off-policy estimates) |
| GET | `/api/v1/crm/campaign-influence` | Emails, clicks and purchases after a click, per kind of email |
| GET | `/api/v1/crm/capacity` | What a call slot is worth right now (capacity-aware next-best-action) |
| POST | `/api/v1/crm/automations/run` | Run every automatic follow-up now instead of waiting for the timer |

## CRM leads

| Method | Path | What it does |
|---|---|---|
| GET | `/api/v1/crm/leads` | Leads, one row per person |
| GET | `/api/v1/crm/leads/export.csv` | Every lead as CSV (one row per person) |
| GET | `/api/v1/crm/leads/{lead_id}` | One person's page (any of their records opens their current state) |
| GET | `/api/v1/crm/leads/{lead_id}/now` | What the CRM would do for this person right now (nothing is sent) |
| POST | `/api/v1/crm/leads/{lead_id}/act` | Take one step now (logged like an automatic decision) |
| GET | `/api/v1/crm/leads/{lead_id}/attribution` | The person's timeline, first touch and last touch before buying |
| GET | `/api/v1/crm/leads/{lead_id}/explain` | Why this score: what each signal added or took away |
| POST | `/api/v1/crm/leads/{lead_id}/rescore` | Score this lead again with the current model |
| GET | `/api/v1/crm/leads/{lead_id}/paths` | What-if paths: each step now, the likely reaction, the best follow-up |
| PUT | `/api/v1/crm/leads/{lead_id}/owner` | Give the lead to someone on the team (or take an unassigned one) |
| POST | `/api/v1/crm/leads/{lead_id}/notes` | Add a note to the lead |
| DELETE | `/api/v1/crm/notes/{note_id}` | Delete a note (its author or an admin) |
| POST | `/api/v1/crm/leads/{lead_id}/status` | Close the lead as lost (with a reason), or re-open it |
| POST | `/api/v1/crm/leads/{lead_id}/consent` | Record that the person does not want emails, calls or WhatsApp |

## CRM today's actions

| Method | Path | What it does |
|---|---|---|
| GET | `/api/v1/crm/actions` | Call and WhatsApp tasks: open ones by expected extra profit, closed ones by date |
| POST | `/api/v1/crm/actions/{task_id}/done` | Record what happened on a call or WhatsApp to a real person |
| POST | `/api/v1/crm/actions/{task_id}/call` | Call a simulated learner (the simulator answers) |
| GET | `/api/v1/crm/callbacks` | Call-back requests from the website |
| POST | `/api/v1/crm/callbacks/{callback_id}/done` | Mark a call-back request as done |

## CRM outreach

| Method | Path | What it does |
|---|---|---|
| POST | `/api/v1/crm/emails` | Send an email written on the lead page |
| POST | `/api/v1/crm/emails/improve` | Check or rewrite a draft (Gemini when configured, else rule-based) |
| POST | `/api/v1/crm/whatsapp` | Open WhatsApp with the message for this lead (click-to-chat) |
| GET | `/api/v1/crm/whatsapp/log` | WhatsApp messages opened from the CRM |
| GET | `/api/v1/crm/coupons/check` | The coupon guard: what a personal coupon would do for this learner |
| POST | `/api/v1/crm/coupons` | Give one learner a personal coupon (the coupon guard checks it first) |
| GET | `/api/v1/crm/coupons` | Every coupon issued, newest first, with the true totals |
| DELETE | `/api/v1/crm/coupons/{coupon_id}` | Withdraw a coupon |

## CRM campaigns and A/B tests

| Method | Path | What it does |
|---|---|---|
| GET | `/api/v1/crm/campaigns` | Every campaign with its delivery and its effect against the hold-out group |
| POST | `/api/v1/crm/campaigns` | Schedule a campaign |
| POST | `/api/v1/crm/campaigns/{campaign_id}/send-now` | Send a campaign now |
| POST | `/api/v1/crm/campaigns/{campaign_id}/send-failed` | Send the emails the mail server did not take, again |
| DELETE | `/api/v1/crm/campaigns/{campaign_id}` | Delete a campaign that has not been sent |
| GET | `/api/v1/crm/ab-tests` | Every A/B test with its verdict |
| POST | `/api/v1/crm/ab-tests` | Create an A/B test (a draft until it is sent) |
| GET | `/api/v1/crm/ab-tests/plan` | How many people a test needs, and how many the audience gives |
| POST | `/api/v1/crm/ab-tests/{test_id}/send` | Send an A/B test |
| GET | `/api/v1/crm/ab-tests/{test_id}/results` | Results of one A/B test (or its plan, for a draft) |
| POST | `/api/v1/crm/ab-tests/{test_id}/apply` | Turn a variant into a campaign draft |
| DELETE | `/api/v1/crm/ab-tests/{test_id}` | Delete a draft A/B test |
| GET | `/api/v1/crm/adoptions` | A/B winners in use as the standard email, and how their check is going |
| POST | `/api/v1/crm/adoptions/check` | Run the adoption check now |
| POST | `/api/v1/crm/adoptions/{adoption_id}/revert` | Switch back to the old standard email |

## CRM insights

| Method | Path | What it does |
|---|---|---|
| GET | `/api/v1/crm/learning/overview` | Everything the Learning loop page shows |
| POST | `/api/v1/crm/learning/run` | Run the learning loop now |
| GET | `/api/v1/crm/latency` | Response times of the real-time loop (median and 95th percentile) |
| GET | `/api/v1/crm/journeys` | Lifecycle funnel, journey map, converting paths and drop-offs |
| GET | `/api/v1/crm/pipeline` | The pipeline board: every lead in its lifecycle stage |
| PUT | `/api/v1/crm/pipeline/{user_id}` | Move a lead to a stage by hand (Lost needs a reason) |
| DELETE | `/api/v1/crm/pipeline/{user_id}` | Back to automatic: the stage follows the learner's behaviour again |
| GET | `/api/v1/crm/planner` | The month in rupees, what the team adds, what more counsellors or budget would add |
| PUT | `/api/v1/crm/planner/settings` | The monthly discount budget and what a counsellor costs (admin) |
| GET | `/api/v1/crm/money` | The open pipeline in rupees and the discount the coupon decisions kept this week |
| GET | `/api/v1/crm/start` | What the Start here page needs: is everything set up, and the rules it explains |
| POST | `/api/v1/crm/copilot` | Ask a question about the CRM's live data (answers only from the data) |
| GET | `/api/v1/crm/copilot` | Suggested questions, the data tools and recent questions |
| GET | `/api/v1/crm/qna` | Unanswered questions from course pages |
| POST | `/api/v1/crm/qna/answer` | Answer a question (published on the course page and emailed) |

## CRM team

| Method | Path | What it does |
|---|---|---|
| GET | `/api/v1/crm/team` | Every account, the team settings and the roles |
| POST | `/api/v1/crm/team` | Add an account (they choose their own password at the first sign-in) |
| PUT | `/api/v1/crm/team/{member_id}` | Change an account's name, role, status or lead intake |
| DELETE | `/api/v1/crm/team/{member_id}` | Delete an account (its leads become unassigned) |
| POST | `/api/v1/crm/team/{member_id}/password` | Set a new password (they choose their own at the next sign-in) |
| PUT | `/api/v1/crm/team-settings` | How leads are given out, service levels and task expiry |
| POST | `/api/v1/crm/team/assign-now` | Give out leads now (backlog=true: also older open leads) |
| GET | `/api/v1/crm/team/performance` | One row per counsellor: leads, tasks, speed, purchases and revenue |
| GET | `/api/v1/crm/audit` | Who changed what (people on the team; leads by number only) |

## CRM simulated learners

| Method | Path | What it does |
|---|---|---|
| GET | `/api/v1/crm/simulation` | What the simulated learners did recently |
| POST | `/api/v1/crm/simulation/visit` | Send a simulated learner to the website now (or let a new one sign up) |
| POST | `/api/v1/crm/simulation/enabled` | Pause or resume the simulated learners |
