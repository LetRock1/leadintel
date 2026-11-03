# How it works

For every learner, all the time, the CRM works out four things: how likely they are to buy if the team does nothing,
which step would change that and pay for itself, whether that step deserves one of the day's few call slots or a
share of the month's discount money, and what all of it is worth in rupees. It keeps learning from its own results
without counting its own follow-ups as lead quality. This page explains each part in plain words, with the formula
where one helps, and names the experiment that tests it ([RESEARCH.md](RESEARCH.md) has the numbers and the
comparisons with other methods). The people who use the CRM need none of this: its **Start here** page explains what
it does and where each of them begins, in plain words.

## 1. The lead score

**What it means.** The score is the chance that the person buys within 14 days *if the team does nothing now*,
shown as 0 to 100. "If we do nothing" matters: the CRM's own emails, coupons and calls must never be counted as
lead quality (see the learning loop below), and it is what lets the CRM say what comes in anyway (section 4).

**How it is made.** Two parts (`backend/app/ml/lead_model.py`):

```
logit P(buy within 14 days | lead, no step now)
    = a * logit(base(x))                  base model, trained once
    + b + sum_j w_j * s_j(x)              live layer, learned from this CRM's own outcomes
    + effect of time away + effect of lead age
```

- The **base model** is trained at the first start on 60,000 simulated leads that carry every signal the website
  records: profile, visits, time on site, video, pricing page, brochure, chat, webinar, wishlist, cart, checkout,
  enquiry, email clicks, WhatsApp and contact consent. Logistic regression and gradient boosting are compared on a
  held-out 20%; logistic regression is kept unless boosting is clearly better (lower log-loss).
- The **live layer** re-calibrates the base model to this business: how strongly the base score carries over (`a`),
  the overall level of buying (`b`) and small corrections for the strongest signals (`w`), shrunk towards zero so
  they only move as far as real outcomes support. How much time away and the lead's age lower the chance is learned
  too, not set by hand.

**When it changes.** Every tracked event re-scores the learner at once (a click on the pricing page shows on the
CRM within a second), and every lead is re-scored on a timer because time away lowers the chance.

**Tiers** (from `crm_settings.json`): 80 and above *Target Immediately*, 60 to 79 *Nurture via Email/WhatsApp*,
40 to 59 *Marketing Campaign*, below 40 *Low Priority*. The lead page lists the factors behind a score: what each
signal added or took away.

**No leakage.** The model uses only what the website records before anyone contacts the lead. The public X Education
dataset also has columns sales fills in after contact (Tags, Lead Quality and others) that push AUC to 0.98; they are
never used, and a test fails if one is. Tested on real data in **E1** and against published solutions in **E1b**.

## 2. Next-best-action

A score says who is likely to buy. It does not say what to do: a hot lead given a 20% coupon would often have bought
anyway, so the discount is money given away. Next-best-action (`backend/app/ml/nba_core.py`, `nba.py`) estimates,
for every step the team could take, the chance to buy after that step, and picks the step that adds the most profit:

```
expected profit of step a  =  P(buy | person, a) * course fee * (1 - discount of a) - cost of a
extra profit of step a     =  expected profit of a - expected profit of doing nothing
chosen step                =  the allowed step with the largest extra profit after the prices of a call slot and
                              of discount money (section 3), or nothing when none is positive
```

The steps are: do nothing, an information email, an email with a 10% or 20% coupon, a counsellor call, a WhatsApp
message (costs and discounts in `crm_settings.json`).

- **The model** is a logistic S-learner with step-by-context interactions: `logit P(buy | x, a) = beta * c(x) +
  gamma_a * c(x)`, where `c(x)` is a small context built on the lead score (the score itself, price-sensitive
  occupations, high intent, cart or enquiry, professionals, email engagement, WhatsApp opt-in, low engagement).
  Each `gamma_a` reads as "how much step a moves the odds for people like this", so every decision can be explained.
  A flexible gradient-boosting model competes with it in the learning loop; the better one on held-out decisions
  is used.
- **Consent first.** A step the person has not allowed is never chosen: no email after "do not email", no call
  without a phone number or after "do not call", no WhatsApp without opt-in, nothing at all for a lead closed as
  lost or for the 5% control group.
- **What the team sees.** Every step is chosen on its expected value (chance of buying x fee, after the discount and
  the step's cost, and the call-slot price), but lead-level screens show only chances of buying and how much a step
  changes them: nobody has paid anything yet, so a per-lead "profit" would mislead. Rupee totals appear only as the
  owner's forecasts (Pipeline totals, Overview, Planner) and on the Next-best-action page.
- **One open coupon per person, and at most one a week.** While someone still holds a coupon they can use (from the
  CRM or the team), no second coupon is chosen or given: discounts would only stack on the same purchase. After a
  coupon, the next one waits 7 days whether it was used or not (`coupon_gap_days` in `crm_settings.json`), so
  coupons do not teach people to wait for the next one. Every coupon has its own code (a
  readable name for the discount and five random characters, for example SMARTSTART20-K7Q2M) that works only for that
  person, once.
- **No step twice in a row by hand.** The team cannot send a person the same email step again within 24 hours
  (`manual_repeat` in `crm_settings.json`), or plan a second call or WhatsApp message while the first one is still
  waiting in Today's actions; the lead page says when the step can be taken again.
- **Learning by design.** 15% of automatic decisions are random among the allowed steps, and every decision is
  logged with the probability it had. That makes honest evaluation and retraining possible (inverse-propensity
  weighting) without a separate experiment. The setting is `exploration_rate`; what the random steps cost is
  measured in **E8b**.
- **The decision receipt.** Each decision is stored with every option, its chance to buy, its extra profit and the
  prices it was charged, so the lead page shows exactly why the CRM did what it did.

Tested on a real randomised email experiment in **E2** and, with the assumptions about the world deliberately
broken, in **E2b**.

## 3. Two scarce resources, priced: call slots and discount money

A business has two things it cannot hand out to everyone: counsellor time and discount money. Next-best-action
decides one learner at a time, as triggers arrive, so a plain limit hands both out first come, first served: a call
or a coupon that adds a little in the morning takes what an evening lead needed far more. The CRM gives each a
price, worked out again at every decision, and a step is chosen only when it beats its price (the bid price of
airline revenue management, Talluri and van Ryzin, 2004).

### Call slots

The team can make only so many calls a day (`daily_call_capacity`, 8 for one counsellor). What a call adds is not
its whole value, only what it adds over the best step without a call, because an email is often nearly as good
(`backend/app/ml/capacity.py`):

```
call advantage   d = extra profit of a call - max(extra profit of every other allowed step, including nothing)
slot price       the smallest x for which the calls with d > x, expected in the rest of today, fit into the
                 slots that are left
```

The expected arrivals come from the CRM's own decision log: every automatic decision of the last 7 days where a call
was possible stores its `d` and its time of day. With `R` the share of a day's call-worthy decisions that usually
arrive after now, `D` the number of days seen and `S` the slots left:

```
k     = floor(S * D / R)
price = the (k + 1)-th largest d of the window   (0 when there are fewer)
```

So the price falls when slots are left late in the day and rises when they are being used up early; it is infinite
when no slot is left and zero when demand is below capacity. Until 50 decisions with a possible call exist, or with
`call_capacity.policy` set to `fcfs`, the price is 0. The hard daily cap stays as a backstop.

**Result (E7).** On simulated days with known true effects, when call-worthy decisions outnumber the slots 2 to 8
times, first come, first served captures 41% to 70% of the value of the call slots that the best allocation with
hindsight gets; the re-solved slot price captures 95% to 97%. With spare capacity it changes nothing.

### Discount money

Without a budget, a coupon goes out whenever it adds more profit than its discount costs. The owner can set a
monthly discount budget on the Planner page (`backend/app/ml/budget.py`). A coupon costs money only when it is used:

```
expected discount  c = P(buy | coupon) * course fee * discount
coupon advantage   v = extra profit of the best allowed coupon
                       - max(extra profit of every other allowed step, including nothing; a call net of its price)
money left         B = budget - discounts given this month - expected discount of the coupons still open
price              the (k + 1)-th largest v / c of the last 7 days' decisions, with k the most coupons (largest
                   v / c first) whose c fits B * D / T     (D days in the window, T days left in the month)
```

Every step is then counted net of its prices: `extra profit - slot price * [call] - discount price * expected
discount`. The price rises when money is going fast and falls when it is left over; it is 0 with no budget or when
there is money for every coupon that pays, and when the money is gone, coupons stop until next month. Until 30
decisions where a coupon paid have been seen, the price is 0 and coupons simply stop when the money is used up.

**Result (E9).** With a budget of 10% to 50% of what every paying coupon would cost, spending it first come, first
served gets 37% to 62% of the value of the best single price chosen with hindsight; the re-solved price gets 97% to
100%, a fixed price set at the start of the month 89% to 95%, and the usual cart-recovery rule (a 10% coupon for every
left cart) loses money. The re-solved price stays within the budget (95% to 97% of it used, in truth).

**What the team sees.** The decision receipt shows a step net of its prices ("+₹8,251 before the call slot price of
₹324"); Today's actions and the Next-best-action page show the call meter (calls used, slots left, the price now);
the Planner page shows the discount budget (given, promised in open coupons, left, the price now).

## 4. The pipeline in rupees

**The problem.** A usual pipeline shows stages, and a forecast that multiplies each deal by a probability. That
probability is learned from leads the team worked, so it already includes the team's work: the forecast cannot say
what comes in anyway and what the team's work adds. And a list sorted by score puts first the people who would buy
anyway, where the team adds least.

**What the CRM shows** (`backend/app/services/money.py`, the Pipeline page). For every open lead, from the same
numbers as next-best-action:

```
comes in anyway    = P(buy within 14 days | no step) * course fee     (the lead score, in rupees)
the team can add   = extra profit of the best step now, net of the prices of section 3
```

- At the top: what comes in anyway from all open leads, what the team can still add and with how many leads.
- Each stage shows both numbers, and its cards are ordered by what the team can add (or by score, if preferred).
- Each card has one line, for example "+₹6,320 with a 20% coupon email", and **Do it** takes that step at once
  (logged like any other decision, with its receipt).
- **No discount needed** marks leads who are more likely than not to buy anyway and for whom no coupon would add
  profit: a coupon there only gives money away.
- Leads in the control group, customers and lost leads have nothing to add.

**Result (E9).** On simulated pipelines of 1,200 open leads with known truth, "comes in anyway" is within 0.1% of the
true total and "the team can add" within 2%. When the team has time for 5% to 40% of the leads, working them in this
order adds 89% to 93% of the most it could add, against 4% to 62% for highest score first and 24% to 50% at random.
Of the leads marked "No discount needed", 91% truly lose money with a coupon.

## 5. The coupon guard

**The problem.** Discounts given by hand to "close" warm leads mostly go to people who would have paid in full.

**What the CRM does** (`money.coupon_check`, the Coupons page). Before a personal coupon is given, the dialog shows
what it would do for that person, from the same numbers as next-best-action:

```
chance without    p0 = the lead score
chance with       p1 = P(buy | coupon), from next-best-action's model (its 10% or 20% coupon, the nearer one)
expected discount    = p1 * course fee * discount
extra profit         = p1 * course fee * (1 - discount) - p0 * course fee
```

- If the coupon pays for itself, it is given as usual.
- If it does not, the dialog says why ("97% chance to buy without a coupon: about ₹2,729 of discount, 99% of it to
  someone who would have paid in full") and the coupon is given only if someone confirms with **Give it anyway**.
- If it would go over what is left of the month's discount budget, the dialog says so, with the same confirmation.
- A coupon for a lead in the control group is never given: it would spoil the CRM's own measurement.
- A second coupon for someone who still holds an open one is never given either: withdraw the first one to change it.

Every coupon given by hand is stored with its expected discount, so it counts against the budget like the CRM's own.

**Result (E9).** Of coupons a counsellor would give to the warmest 10% of leads, the guard stops all of them, and
98% to 100% truly lose money; of coupons for every left cart it stops 59% to 67%, 95% to 96% of them rightly, which
turns those coupons from a loss into a profit; of coupons for leads picked at random it stops 36% to 45%, 74% to 80%
of them rightly.

## 6. The owner's planner

**The problem.** The owner's questions (what does the team's work bring in, should we hire another counsellor, how
much discount money is worth setting aside) are usually answered from reports that cannot separate what would have
come in anyway.

**What the CRM shows** (`backend/app/services/planner.py`, the Planner page), from its own decision log and its
control group:

- **The month in rupees:** revenue so far, what comes in anyway from the open leads, what the team can add, and the
  discount the CRM's decisions kept this week against a coupon for every left cart.
- **What the team's work adds:** the share who bought within 30 days among leads the CRM worked on against the
  control group it never contacts. The control group is chosen at random, so the difference is what the team's steps
  add; it is shown with its 95% interval and in rupees at the average fee paid.
- **Should we hire another counsellor?** Last week's decisions are replayed with 8 more call slots a day (one more
  counsellor): the extra calls the CRM's own rule would then have made, each worth what it adds over the best step
  without a call, against what a counsellor costs a month (a setting on the page).
- **The discount budget:** set or remove the monthly budget, see what the coupons that pay would cost in a month
  without a limit, and what ₹10,000 more would add.

**Result (E9).** The estimate of what one more counsellor adds is within 11% below to 3% above the true extra profit
of the extra slots (call demand 1 to 8 times today's slots); the value of today's slots within 4%. The estimate of
what 20% more discount money adds is within 12% below to 15% above the truth when the budget is tight; when there is
already money for every coupon that pays, both are close to zero.

## 7. A learning loop that does not fool itself

**The problem.** A CRM that retrains its score on "who bought" learns its own follow-ups as if they were lead
quality: hot leads get emails, coupons and calls, those make them buy, and the retrained model concludes that people
like them are even hotter. The usual check, accuracy on recent data, then picks the inflated model, because the same
follow-ups shaped that data. And when next-best-action acts by a rule on the score's own signals (the pricing page,
the cart, an enquiry), the same leads always get the same step, so the decision log alone cannot tell the step from
the signal.

**What the loop does** (`backend/app/ml/learning.py`, `anchor.py`), whenever enough new outcomes are known:

1. **Data.** Every decision point with a known outcome: what the CRM knew about the lead then, what it did, and
   whether they bought within 14 days.
2. **What the CRM's work adds, measured.** The CRM runs an experiment on itself: the 5% control group is chosen by a hash,
   whatever the lead does, and never contacted, and next-best-action still logs the step it would have taken for
   them. So for each step (the information email, each coupon, the call, WhatsApp) the loop compares the leads it
   acted on with that step against the control-group leads it would have given the same step:

   ```
   lift of step a   = logit(share bought | acted on with a) - logit(share bought | control group, would have got a)
   standard error   bootstrap over people (a lead appears at several decision points)
   ```

   A step needs at least 20 decision points on each side; until then, and for campaign emails, its effect is learned
   from the data with the CRM's steps as inputs. Only the control group measures "never contacted": a lead the CRM
   leaves alone now is usually followed up at its next trigger, inside the 14 days. For the same reason the lift
   includes the follow-ups that come after the step: it is what the CRM's work adds, starting with that step, which
   is exactly what must be kept out of the score. (Which step works best on its own is measured by the random
   learning steps, on the Next-best-action page.)
3. **Learn.** The live layer is refitted with each lift fixed, and the score switches every step off:

   ```
   logit P(buy | lead, step now) = live layer(lead) + lift_a * [step a taken]     lift_a fixed, the rest fitted
   score                         = the same with no step
   ```

   Time away and lead age stay in the score; their size is learned. The lifts come only from the people a model is
   trained on (cross-fitting), so the check below stays honest.
4. **Check.** The new score and the one in use are compared on the control group: people nobody's follow-ups shaped,
   and new models are judged only on people they were not fitted on.
5. **Swap** only if the new score beats the one in use on the control group in at least 90% of bootstrap resamples.
6. **Record** every update, its numbers and its reason.

The next-best-action model is retrained in the same run from the decision log and replaced only if the lower end of
the 95% interval of its profit gain on held-out decisions is above zero.

**What the team sees** (the Learning loop page): how many outcomes the CRM has learned from, how accurate the score
is on never-contacted leads and when the next update is due; expected against actual buying of those leads, update
by update; what the team's work adds after each step, in points of buying chance; how time away changes the chance;
what the CRM has corrected in the starting model; every update with its result; how long the live steps take; and
the latest events. **Ask** answers "What do our emails and calls add?" from the same numbers.

**Result.** On real randomised data (**E3**), naive retraining over-predicts what customers do when nobody contacts
them by 2.35 points (22% of the true rate); this loop removes 88% of that bias, while the usual check would have
picked the inflated model in 50 of 50 repeats. In simulated histories of the whole CRM (**E8**), judged on learners
nobody contacted or trained on, the score over-states buying by 6%, against 31% for a naive retrain.

## 8. A/B tests that can be trusted, and winners adopted with a check

The A/B engine (`backend/app/ml/experiments.py`) follows Kohavi, Tang and Xu (2020):

- Two or three email variants and a **control group that gets no email** (20% by default), so each result is the
  extra purchases the email caused, not just "A beat B".
- **Deterministic assignment** by a hash of test and person, stored with its probability, so the split can be
  re-checked and every assignment is a decision point for the learning loop.
- A **planned sample size** for the smallest lift worth finding (80% power), a **fixed 14-day window** (numbers before
  that are marked not final, so peeking cannot fool anyone), 95% Newcombe intervals, two-proportion tests with a
  Bonferroni correction for several variants, and a **sample-ratio check** that warns when the split is broken.
- **Adopting winners.** When a test is final and a variant clearly won, its wording becomes the standard information
  email for that audience, but 10% of the audience keeps the old email. The CRM keeps comparing them and switches
  back by itself if the new email turns out worse ("ship the winner with a holdback"). Variants that carry a
  discount are never adopted: whether to give a discount is next-best-action's decision per person.

Tested with thousands of simulated tests whose truth is known in **E4**.

## 9. What-if paths

For one lead, the CRM shows what would probably happen next: "if the team does this now, the learner will probably
do that in the next 3 days, and then the best next step is ..." (`backend/app/ml/paths.py`).

- **Step 1** uses exactly the numbers and the pick of the decision receipt, so the two can never disagree.
- **Reactions** come from how learners in the same lifecycle stage reacted to the same step in this CRM's history
  (bought, moved to cart or enquiry, came back, clicked, nothing), weighted by the probability of each logged
  decision. With too little history the page says so instead of guessing.
- **Step 2** is the best follow-up for the learner as they would then be, re-scored by the same models.

Tested out of time on the CRM's own history in **E5**.

## 10. Lead age and time away, learned

Hand-written decay rules ("minus 10 points a week") are common in CRMs. Here the effect of time away and of the
lead's age (days since sign-up, in buckets) is learned by the learning loop next to its own steps, and checked on the
control group like everything else. Compared with hand-set decay rules in **E6**.

## 11. The assistants and the messages

- **The website's help assistant** answers questions about courses, fees, duration and schedules only from the course
  catalogue and the FAQ (`backend/app/resources`), and offers a call with a counsellor when it cannot help. It never
  pretends to be a person.
- **Ask, the CRM's assistant**, answers questions about the CRM's own data (how many leads, sign-ups and customers,
  who to call today, the hottest leads, the pipeline in rupees, whether to hire another counsellor, the learning loop,
  the A/B tests, the CRM's impact, the call-slot price, revenue) with numbers read from the database; it can also
  draft an email or an A/B test. Gemini, when configured, phrases the answer; the numbers never come from the
  language model.
- **Messages** (emails, WhatsApp texts, call scripts) are written from templates, or by Gemini when configured,
  restricted to the catalogue's facts; a checker flags unprovable claims (salaries, guaranteed jobs, deadlines).

Without Gmail or Gemini every part still works: emails and sign-up codes are recorded in the log, and templates
write the messages. Any other mail server can stand in for Gmail (`SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY`). An email
the mail server does not take (no connection, a refused login, a daily limit) is kept as "not sent" with the reason,
shown on the lead's timeline, tried again every 10 minutes for a day (six tries at most, never after an opt-out), and a
campaign can send its failed emails again at once; delivery numbers count only emails that went out.
