# Demo guide

A 20-minute walk through the project for a review or a viva, in the order that tells the story: a learner arrives,
the CRM scores and decides in real time, the team works the pipeline in rupees, the owner plans with the same
numbers, and the system learns without fooling itself. Each step names what to click and what to point out.

## On the day of the demo

- **Start it once the day before.** The first start takes about 15 minutes (it installs everything and creates six
  months of history); after that it starts in seconds. Check that the website and the CRM open, then stop it.
- **Keep demo mode on** (`DEMO_MODE=true` in `backend/.env`, the default). The CRM then reacts within a minute or
  two: a left cart or checkout is followed up while the teachers watch. With `DEMO_MODE=false` (a real business) the
  same follow-ups wait 30 minutes to an hour on purpose.
- **Do not remove the simulated history before the demo.** It is what fills the Overview, the Pipeline, the Planner
  and the Learning loop with six months of results. Real people you add during the demo are scored, followed up and
  counted exactly like the simulated learners, and every list can show real people only.
- **Show yourself as the real learner** (section 2): sign up with your own email address in front of them; you are a
  lead in the CRM at once, and every click on the website moves your score.
- **No internet is needed.** Without email set up, sign-up codes appear in the "X Education API" window (on macOS and
  Linux in `backend/data/logs/api.out`).
- **If anything hangs,** run `stop-all.bat` (or `./stop-all.sh`) and start again: the data is kept.

## Before you start

1. Run `start-all.bat` (Windows) or `./start-all.sh` (macOS, Linux). The first start takes about 15 minutes; after
   that, seconds. On Windows leave the three server windows open; on macOS and Linux the servers run in the
   background, with their logs in `backend/data/logs`.
2. Open the CRM at http://localhost:5174 and sign in with the address and first password the start window showed
   (also in `backend/data/initial-admin-password.txt`). Choose your own password when asked.
3. In the CRM, open **Start here** (top of the menu). It is the page a new team member reads first: what the CRM
   does by itself, the first steps for a counsellor, a marketer and the owner, whether email and the other parts are
   set up, and the words the CRM uses. A bar at the top of every page points new people to it until they open it.
4. Open the website at http://localhost:5173 in a second browser window, side by side with the CRM.
5. Optional: put Gmail and Gemini keys in `backend/.env` (see `.env.example`) and restart, so codes and emails are
   really sent and drafts are written by Gemini. Without them everything works; sign-up codes appear in the
   "X Education API" window (on macOS and Linux in `backend/data/logs/api.out`).

## 1. The website (2 minutes)

- The **home page** opens on the course finder: say who you are, the areas you want to grow in and the time you can
  give, and the matching courses light up in the course table below. Point out that every course fact (fee,
  duration, modules) comes from the server's catalogue, the same source the help assistant and the emails use.
- Open a course. Show the fee with the EMI option, the modules, reviews by enrolled learners and the questions.
- Open the **help assistant** (bottom right) and ask "What are the fees?" or "Can I study while I work?". It answers
  only from the catalogue and the FAQ, and offers a call with a counsellor when it cannot help.

## 2. A real learner, scored live (3 minutes)

- **Sign up** with your own email address. Without Gmail the six-digit code appears in the "X Education API"
  window (or `backend/data/logs/api.out`); enter it. Complete the short profile (occupation, specialisation, phone).
- In the CRM open **Leads** and search for your address: you are a lead already, with a score.
- On the website open a course, watch the video, open the pricing section, add the course to the cart. Each step
  re-scores you: refresh your lead page in the CRM and the score, its factors and the score history move.
- Leave the cart. In demo mode the CRM decides within about a minute.

## 3. The decision and its receipt (3 minutes)

- On your **lead page** open the **Next step** tab. The **decision receipt** lists every step the CRM could take
  (nothing, an information email, a 10% or 20% coupon, a call, WhatsApp) with the chance to buy after it and how
  many points that changes it. The chosen step is marked; steps you did not allow show why ("No phone number", "Opted out of
  email"). The **Decisions** tab lists the earlier decisions, each with its receipt and what happened after it.
- Point out that the CRM may choose *no coupon* for a hot lead: a discount to someone who would buy anyway is money
  given away. That is the difference between a score and next-best-action.
- If asked "why this step and not the one with the biggest jump?": the CRM also weighs each step's cost, any
  discount and today's call slots. That calculation stays inside the decision; the team sees only chances of
  buying, never a per-lead profit (nobody has paid anything yet).
- **What-if paths** below it: if the team does this now, what learners like this usually do in the next three days,
  and the best step after each reaction.

## 4. The pipeline in rupees (3 minutes)

- Open **Pipeline**. The strip at the top is the owner's forecast: expected sales from the open leads if the team
  does nothing, what the team can still add with the best steps, and how many leads need no discount. These are
  estimates over all open leads, not money earned.
- Each card shows the lead's chance of buying and the best step with the chance it gives, for example "6% → 9% with a
  20% coupon email"; cards are ordered so the leads where a step makes the most difference come first. Press
  **Do it**: the step is taken at once and logged with its receipt like any other decision.
- Switch the order to **Highest score** and back: the hottest leads are often the ones who would buy anyway, so
  working them first adds little. In the simulation with known truth, "most to add first" adds 89% to 93% of the most
  the team could add, "highest score first" 4% to 62% (E9).
- **No discount needed** on a card: more likely than not to buy anyway, and a coupon would hardly change that.
- Coupons: a person holds one open coupon at most, and gets at most one coupon a week, used or not.

## 5. Two scarce resources, priced (2 minutes)

- Open **Today's actions**. The **call meter** shows the day's call slots (8 for one counsellor) and how many are
  used. The **Next-best-action** page shows the same meter with the price of a slot, for the owner.
- Explain: decisions arrive one at a time, so a plain cap gives the slots away first come, first served. Instead each
  slot has a price, worked out again at every decision from the last week of decisions and the slots left: a call is
  booked only when it adds more than the best step without a call *and* more than that price. On a lead's receipt a
  call that lost out says "Today's call slots are kept for learners a call helps more". With demand two to eight times the capacity, first come, first
  served captures 41% to 70% of the value of the call slots; the priced slots 95% to 97% (E7).
- Discount money works the same way once the owner sets a monthly budget (next section): a coupon goes out only when
  the profit it adds beats what its money would earn on later leads this month. With a tight budget that gets 97% to
  100% of the best allocation in hindsight, against 37% to 62% first come, first served (E9).
- Press **Call now** on a simulated learner's task: the simulator decides whether they answer, and the outcome is
  saved under your name. For a real person you ring the number and press **Record the call**.

## 6. The coupon guard (1 minute)

- Open **Coupons** and press **Give a coupon**. Pick a warm lead: the dialog shows their chance to buy without a
  coupon and how much of the discount would go to someone who would have paid in full, and the button turns into
  **Give it anyway**. Pick a lead a coupon would really help: "This coupon pays for itself", with the chance with and
  without it.
- Point out that a coupon for a control-group lead is never given, and that every coupon given by hand counts against
  the discount budget.

## 7. The owner's planner (2 minutes)

- Open **Planner**. The month in rupees at the top; then **What the team's work adds**: buying among leads the CRM
  worked on against the control group it never contacts, with a 95% interval, in rupees.
- **Should we hire another counsellor?** Last week's decisions replayed with 8 more call slots a day: what the extra
  calls would add a month against what a counsellor costs (change the cost and save).
- **Discount budget**: set a monthly budget and save. The meter shows what was given, what is promised in open
  coupons, what is left and the price of a rupee of discount now; from the next decision the CRM spends it by that
  price. Empty the field to remove the budget.
- **Discount kept**: what a coupon for every left cart would have given to people who were going to buy anyway, against
  what the CRM's own decisions gave them.

## 8. Marketing that measures itself (1 minute)

- **A/B tests**: open a finished test. Each variant is compared with a control group that got no email, with a 95%
  interval, a fixed 14-day window and a check that the split is healthy. A clear winner is adopted as the standard
  email with 10% kept on the old one, and switched back automatically if it stops winning.
- **Campaigns**: scheduled emails with a held-out share, so their effect is measured too.

## 9. A learning loop that does not fool itself (2 minutes)

- Open **Learning loop**. **Is the score accurate?** compares what the score expected the never-contacted leads to buy
  with what they bought, update by update. Explain why those leads: nobody's follow-ups shaped what they did, so a
  score that had learned the team's own emails and calls as lead quality would show up here as over-predicting.
- **What the team's work adds, by step**: points of buying chance, measured by comparing the leads the CRM worked on
  after each step (its follow-ups included) with leads of its control group that it would have treated the same way.
  This is kept out of the score, so a lead's score never includes the team's own work. Which step works best on its
  own is on the Next-best-action page (the learning steps).
- **How time changes the chance to buy** is learned instead of a hand-set decay rule (E6), and **Updates** lists every
  update with its result: a new score replaces the old one only when it predicts the never-contacted leads better.
- The result on real data (E3): naive retraining over-predicts what customers do when nobody contacts them by 22%;
  this loop removes 88% of that bias.
- **Overview** shows the CRM's impact against the control group too, and **Journeys** maps how learners move from
  stage to step to reaction to buying.

## 10. Ask the CRM, and the finishing touches

- **Ask the CRM**: "Who should we call today?", "What is the pipeline worth?", "Should we hire another counsellor?",
  "Is the CRM actually making a difference?", "What do our emails and calls add?". The numbers come from the database;
  Gemini, if configured, only phrases them.
- Switch to **dark mode** (the moon icon) and narrow the window to phone width: both apps are built for both.
- The **simulated learners** (sidebar, bottom): 2,000 learners live in real time over the website's own API. Press
  "Let a new learner sign up" and watch them appear in Leads. Only learners are simulated; nobody on the team is.
- Finally, on the website open **Settings** and delete your account: every record linked to you is removed, and the
  CRM no longer lists you.

## Checking it yourself (on your laptop)

Run these with the system started (`start-all`), from the project folder. Each asks for your CRM password and never
prints it.

| Check | macOS, Linux | Windows |
|---|---|---|
| Every page's data and a learner's whole journey, end to end (a minute or less) | `backend/.venv/bin/python scripts/smoke_test.py` | `backend\.venv\Scripts\python scripts\smoke_test.py` |
| Real people are treated exactly like simulated learners (a few minutes; works on a copy of your data) | `backend/.venv/bin/python scripts/real_vs_simulated_check.py` | `backend\.venv\Scripts\python scripts\real_vs_simulated_check.py` |
| How fast a website event reaches the score | `backend/.venv/bin/python scripts/latency_check.py` | `backend\.venv\Scripts\python scripts\latency_check.py` |

The smoke test ends with "Every request answered as expected", the second check with "0 differences besides the
real/simulated split".

**Business timings (optional, takes about 35 minutes).** Set `DEMO_MODE=false` in `backend/.env` and start again.
Sign up on the website as a new real person, add a course to the cart, open the checkout and close the tab. After 30
to 35 minutes the person's lead page in the CRM shows "Left the checkout" and what the CRM decided (sometimes
nothing: for the never-contacted control group, or when no step pays for itself). Set `DEMO_MODE=true` again before a
demo.

## Questions you may be asked

| Question | Short answer |
|---|---|
| Is the data real? | The learners in the CRM are simulated (marked as such); every learner you add yourself is real. The methods are tested on two real public datasets (E1, E1b, E2, E3); the money features with known truth in simulation (E7, E9). |
| Which data trains the CRM's score, and why the 9,240-lead Kaggle file? | The score in the product is trained on 60,000 generated leads that carry every signal the website records (video, pricing, cart, checkout...), then corrected by the CRM's own real outcomes. The Kaggle file trains nothing in the product: it has none of those website signals. It is used only to prove the method on real people, with its leaked columns (Tags, Lead Quality, Last Activity and others the sales team fills in after a call) removed: AUC 0.874 for a brand-new lead, above the best published leak-free results (0.8605 and 0.864). Without it every number would be simulated. |
| Why not just use the lead score? | The score says who will buy, not what to do. A coupon to a hot lead mostly gives money away. Next-best-action chooses the step that changes the outcome and pays for itself, and the pipeline orders the work by it. |
| How is "comes in anyway" different from a weighted pipeline? | A weighted pipeline uses probabilities learned from leads the team worked, so it already includes the team's work. Here the score is the chance to buy if the team does nothing, and what the team adds is shown separately (E9: both within 2% of the truth in simulation). |
| What stops the model from learning its own emails as quality? | It scores "if we do nothing", what the CRM's own work adds is measured against the never-contacted control group and kept out of the score, and every new model is judged on that control group (E3, E8). |
| Why the control group and not the random steps or next-best-action's own cut-off? | A lead the CRM leaves alone today is usually followed up at its next trigger, so those compare acting now with acting later. Only leads that are never contacted show what a lead does with no help (E8). |
| Why price call slots and discount money instead of a cap or a budget that runs out? | A cap or a budget fills up with whoever comes first. A price keeps them for the leads where they add the most, and it is worked out from the CRM's own decisions (E7, E9). |
| Is the counsellor advice reliable? | It is an estimate from last week's decisions: in simulation within 11% below to 3% above the true value of the extra calls. The page says "about". |
| Do the random learning steps cost money? | In simulation, yes: with none the CRM earned more in 12 of 14 worlds (E8b). They are kept at 15% because without them nothing can be measured; the owner can change `exploration_rate`. |
| Can a new marketer use it without training? | Start here explains the CRM in five minutes, with first steps for each job, a check of what is set up and the CRM's words in plain language; every page starts with one line on what it is for. |
| Can it run without internet? | Yes. Without Gmail or Gemini, emails and codes are recorded in the log and templates write the messages. |
| Can real people use it? | Yes: real learners sign up next to the simulated ones and every list can show real people only. The CRM treats them exactly like simulated learners (same score, step, money line and counts; `scripts/real_vs_simulated_check.py` shows every page reads the same when all simulated learners are turned into real people). Set up Gmail (or another mail server) so their codes and emails really arrive. For real learners only, switch the simulated learners off and remove their history (README, "Using it with real people"). Checkout is a demonstration payment: nothing is charged, and the site says so. |
| How is it tested? | 124 backend tests and 39 frontend tests, lint and type checks, and production builds, on every push (GitHub Actions). |
