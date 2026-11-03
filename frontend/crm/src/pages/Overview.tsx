import { useQuery } from "@tanstack/react-query";
import { compactMoney, int, money, pct, plural, points, shortDate } from "@xedu/shared/lib";
import { Table, Td, Th } from "@xedu/shared/ui";
import { Link } from "react-router";
import { api } from "../api/client";
import { useStats } from "../api/queries";
import type { DailyPoint, Forecast, Impact, MoneyTotals } from "../api/types";
import { IntervalPlot, TrendChart } from "../components/charts";
import { Person, Score } from "../components/lead-bits";
import { KpiStrip, PageHeader, Panel, Section } from "../components/page";
import { Loading, LoadError, QueryView } from "../components/state";
import { TIERS } from "../lib/labels";

interface PriorityLead {
  id: number;
  user_id: number;
  lead_score: number;
  conversion_probability: number;
  plv: number | null;
  recommended_action: string;
  course_type: string | null;
  name: string;
  email: string;
}

type Influence = Record<string, { emails_sent: number; clicks: number; influenced_conversions: number }>;

const EMAIL_KIND: Record<string, string> = {
  session_end: "After a visit",
  enquiry: "After an enquiry",
  wishlist: "Wishlist reminders",
  cart_abandon: "Left the cart",
  checkout_abandon: "Left the checkout",
  campaign: "Campaigns",
  ab_test: "A/B tests",
  manual: "Written by hand",
};

export default function Overview() {
  const stats = useStats(30_000);
  const daily = useQuery({
    queryKey: ["stats", "daily"],
    queryFn: () => api.get<{ days: number; series: DailyPoint[] }>("/stats/daily", { days: 30 }),
    refetchInterval: 60_000,
  });
  const forecast = useQuery({
    queryKey: ["forecast"],
    queryFn: () => api.get<Forecast>("/forecast"),
    refetchInterval: 60_000,
  });
  const queue = useQuery({
    queryKey: ["priority-queue"],
    queryFn: () => api.get<{ priority_queue: PriorityLead[] }>("/priority-queue", { limit: 8 }),
    refetchInterval: 30_000,
  });
  const influence = useQuery({
    queryKey: ["campaign-influence"],
    queryFn: () => api.get<{ campaign_influence: Influence }>("/campaign-influence"),
    refetchInterval: 60_000,
  });
  const moneyView = useQuery({
    queryKey: ["money"],
    queryFn: () =>
      api.get<{ pipeline: MoneyTotals; kept: { days: number; kept: number; ours: { coupons: number } } }>("/money"),
    refetchInterval: 60_000,
  });
  // the same data as the Learning loop page, which shows the impact in full
  const learning = useQuery({
    queryKey: ["learning"],
    queryFn: () => api.get<{ impact: Impact }>("/learning/overview"),
    refetchInterval: 120_000,
    staleTime: 30_000,
  });

  return (
    <>
      <PageHeader
        title="Overview"
        description="How admissions are going: people, purchases, revenue and what to expect next."
      />
      <QueryView query={stats} what="the headline numbers" loading={<Loading className="h-24" />}>
        {(s) => (
          <KpiStrip
            items={[
              { label: "Revenue", value: compactMoney(s.revenue), detail: `${money(s.revenue_today)} today` },
              {
                label: "Customers",
                value: int(s.customers),
                detail: `of ${plural(s.total_leads, "person", "people")}`,
              },
              {
                label: "Open leads",
                value: int(s.open_leads),
                detail: `${int(s.by_tier["Target Immediately"] ?? 0)} ready to buy`,
              },
              { label: "Purchases today", value: int(s.purchases_today), detail: `${int(s.total_purchases)} in all` },
              {
                label: "Email click rate",
                value: pct(s.emails_sent ? s.email_clicks / s.emails_sent : null, 0, "No emails yet"),
                detail: `${int(s.emails_sent)} emails sent`,
              },
              {
                label: "Open tasks",
                value: int(s.open_tasks),
                detail: `${plural(s.open_callbacks, "call-back")} waiting`,
              },
            ]}
          />
        )}
      </QueryView>

      {moneyView.data && (
        <section
          aria-label="The pipeline in rupees"
          className="mt-6 flex flex-wrap items-center gap-x-8 gap-y-3 rounded-md border border-line bg-surface px-4 py-3.5"
        >
          <div>
            <p className="text-[12.5px] text-muted">Comes in anyway, next {moneyView.data.pipeline.window_days} days</p>
            <p className="num text-[20px] font-semibold text-ink">{compactMoney(moneyView.data.pipeline.anyway)}</p>
          </div>
          <div>
            <p className="text-[12.5px] text-muted">The team can still add</p>
            <p className="num text-[20px] font-semibold text-good">+{compactMoney(moneyView.data.pipeline.add)}</p>
          </div>
          <div>
            <p className="text-[12.5px] text-muted">Discount kept, last {moneyView.data.kept.days} days</p>
            <p className="num text-[20px] font-semibold text-ink">{compactMoney(moneyView.data.kept.kept)}</p>
          </div>
          <p className="min-w-0 flex-1 basis-64 text-[13px] text-ink-2">
            The team can add the most where the pipeline shows it, and no discount goes to people likely to buy anyway.{" "}
            <Link className="text-brand-ink hover:underline" to="/planner">
              Open the planner
            </Link>
          </p>
        </section>
      )}

      <div className="mt-8 grid grid-cols-1 gap-6 xl:grid-cols-2">
        {daily.isPending ? (
          <Loading />
        ) : daily.isError ? (
          <LoadError error={daily.error} what="the daily numbers" retry={() => void daily.refetch()} />
        ) : (
          <>
            <TrendChart
              title="Sign-ups and purchases per day"
              description="Last 30 days"
              data={daily.data.series}
              x="date"
              xFormat={(d) => shortDate(d)}
              series={[
                { key: "signups", label: "Sign-ups" },
                { key: "purchases", label: "Purchases" },
              ]}
              format={(v) => int(v)}
              empty="No sign-ups or purchases in the last 30 days yet."
            />
            <TrendChart
              title="Revenue per day"
              description="Last 30 days, after discounts"
              kind="bar"
              data={daily.data.series}
              x="date"
              xFormat={(d) => shortDate(d)}
              series={[{ key: "revenue", label: "Revenue" }]}
              format={(v) => money(v)}
              axisFormat={(v) => compactMoney(v)}
              empty="No purchases in the last 30 days yet."
            />
          </>
        )}
      </div>

      <div className="mt-9 grid grid-cols-1 gap-x-6 gap-y-9 xl:grid-cols-2 [&>section]:mt-0">
        <Section
          title="Does the CRM make a difference?"
          description="People the CRM worked on against the untouched control group it never contacts, chosen at random."
        >
          <QueryView query={learning} what="the CRM's impact">
            {({ impact: i }) => (
              <Panel>
                {i.control.people === 0 && (
                  <p className="mb-3 text-[13.5px] text-ink-2">
                    Not measured yet: it compares people who signed up at least {plural(i.days, "day")} ago, so their
                    outcome is known, and the control group gets only {pct(i.share, 0)} of new learners. It fills as
                    learners stay with the CRM that long.
                  </p>
                )}
                <dl className="grid grid-cols-2 gap-4">
                  <div>
                    <dt className="text-[12.5px] text-muted">Worked on</dt>
                    <dd className="num text-[22px] font-semibold text-ink">{pct(i.worked_on.rate, 1, "Not yet")}</dd>
                    <dd className="text-[12.5px] text-muted">
                      {int(i.worked_on.bought)} of {plural(i.worked_on.people, "person", "people")} bought
                    </dd>
                  </div>
                  <div>
                    <dt className="text-[12.5px] text-muted">Control group</dt>
                    <dd className="num text-[22px] font-semibold text-ink">{pct(i.control.rate, 1, "Not yet")}</dd>
                    <dd className="text-[12.5px] text-muted">
                      {int(i.control.bought)} of {plural(i.control.people, "person", "people")} bought
                    </dd>
                  </div>
                </dl>
                {i.lift !== undefined && i.lift_ci && (
                  <div className="mt-4 border-t border-line">
                    <IntervalPlot
                      label="What the CRM adds"
                      format={(v) => points(v)}
                      rows={[
                        {
                          label: "What the CRM adds",
                          note: `Bought within ${plural(i.days, "day")}, 95% interval`,
                          value: i.lift,
                          low: i.lift_ci[0],
                          high: i.lift_ci[1],
                          emphasis: true,
                        },
                      ]}
                    />
                  </div>
                )}
                <p className="mt-3 text-[12.5px] text-muted">
                  Because the control group is chosen at random, the difference is what the CRM&apos;s emails, calls and
                  messages add. More on the{" "}
                  <Link to="/learning" className="text-brand-ink hover:underline">
                    Learning loop
                  </Link>{" "}
                  page.
                </p>
              </Panel>
            )}
          </QueryView>
        </Section>
        <QueryView query={stats} what="the scores" loading={<Loading />}>
          {(s) => (
            <TrendChart
              title="Open leads by score"
              description="Customers are counted on their own and are not scored."
              kind="bar"
              data={Object.entries(s.score_distribution).map(([band, leads]) => ({ band, leads }))}
              x="band"
              xFormat={(v) => v.replace("-", "–")}
              series={[{ key: "leads", label: "Open leads" }]}
              format={(v) => int(v)}
              empty="No open leads yet."
            />
          )}
        </QueryView>
      </div>

      <div className="mt-9 grid grid-cols-1 gap-x-6 gap-y-9 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)] [&>section]:mt-0">
        <Section title="Revenue to expect" description="From the open leads, if their scores are right.">
          <QueryView query={forecast} what="the forecast">
            {(f) => (
              <Panel>
                <p className="text-[13px] text-muted">Next {f.window_days ?? 14} days</p>
                <p className="num mt-1 text-[26px] font-semibold leading-tight text-ink">
                  {compactMoney(f.expected_revenue)}
                </p>
                <p className="num mt-0.5 text-[13px] text-muted">
                  90% range {compactMoney(f.range_90[0])} to {compactMoney(f.range_90[1])}, about{" "}
                  {int(f.expected_customers)} customers
                </p>
                <table className="mt-4 w-full text-[13px]">
                  <thead>
                    <tr className="text-muted">
                      <th scope="col" className="pb-1.5 text-left font-medium">
                        Tier
                      </th>
                      <th scope="col" className="pb-1.5 text-right font-medium">
                        Leads
                      </th>
                      <th scope="col" className="pb-1.5 text-right font-medium">
                        Customers
                      </th>
                      <th scope="col" className="pb-1.5 text-right font-medium">
                        Revenue
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...f.by_tier]
                      .sort(
                        (a, b) =>
                          TIERS.indexOf(a.tier as (typeof TIERS)[number]) -
                          TIERS.indexOf(b.tier as (typeof TIERS)[number]),
                      )
                      .map((t) => (
                        <tr key={t.tier} className="border-t border-line">
                          <th scope="row" className="py-1.5 text-left font-normal text-ink-2">
                            {t.tier}
                          </th>
                          <td className="num py-1.5 text-right text-ink">{int(t.leads)}</td>
                          <td className="num py-1.5 text-right text-ink">{t.expected_customers.toFixed(1)}</td>
                          <td className="num py-1.5 text-right text-ink">{compactMoney(t.expected_revenue)}</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
                {f.note && <p className="mt-3 text-[12.5px] text-muted">{f.note}</p>}
              </Panel>
            )}
          </QueryView>
        </Section>

        <Section
          title="Open leads to work first"
          description="The most likely to buy, weighted by the course they want; customers left out."
        >
          <QueryView query={queue} what="the leads">
            {(q) => (
              <Table label="Open leads to work first">
                <thead>
                  <tr>
                    <Th>Person</Th>
                    <Th>Score</Th>
                  </tr>
                </thead>
                <tbody>
                  {q.priority_queue.map((l) => (
                    <tr key={l.id}>
                      <Td className="max-w-80">
                        <Person leadId={l.id} name={l.name} email={l.course_type ?? l.email} />
                      </Td>
                      <Td>
                        <Score score={l.lead_score} tier={l.recommended_action} />
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
          </QueryView>
        </Section>
      </div>

      <Section
        title="What the emails led to"
        description="Purchases within the outcome window after a click. A click before buying is not proof the email caused it: the A/B tests and hold-out groups measure that."
      >
        <QueryView query={influence} what="the email numbers">
          {(r) => (
            <Table label="Emails by kind">
              <thead>
                <tr>
                  <Th>Kind of email</Th>
                  <Th className="text-right">Sent</Th>
                  <Th className="text-right">Clicked</Th>
                  <Th className="text-right">Click rate</Th>
                  <Th className="text-right">Bought after a click</Th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(r.campaign_influence).map(([k, v]) => (
                  <tr key={k}>
                    <Td className="text-ink">{EMAIL_KIND[k] ?? k}</Td>
                    <Td className="num text-right">{int(v.emails_sent)}</Td>
                    <Td className="num text-right">{int(v.clicks)}</Td>
                    <Td className="num text-right">
                      {pct(v.emails_sent ? v.clicks / v.emails_sent : null, 0, "None")}
                    </Td>
                    <Td className="num text-right">{int(v.influenced_conversions)}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </QueryView>
      </Section>
    </>
  );
}
