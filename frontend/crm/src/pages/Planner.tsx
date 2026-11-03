import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { compactMoney, errorText, int, money, pct, plural } from "@xedu/shared/lib";
import { Badge, Button, Field, Input, Notice, useToast } from "@xedu/shared/ui";
import { useState } from "react";
import { api } from "../api/client";
import type { MoneyTotals } from "../api/types";
import { useSession } from "../app/session";
import { KpiStrip, PageHeader, Panel, Section } from "../components/page";
import { QueryView } from "../components/state";
import { budgetVerdict, counsellorVerdict, type BudgetView, type CounsellorView } from "../lib/planner";

interface PlannerData {
  as_of: string;
  month: {
    label: string;
    days_in_month: number;
    day: number;
    revenue: number;
    purchases: number;
    discount_given: number;
  };
  pipeline: MoneyTotals & { by_step: Record<string, { label: string; leads: number; add: number }> };
  team: {
    days: number;
    worked_on: { people: number; bought: number; rate: number | null };
    control: { people: number; bought: number; rate: number | null };
    lift?: number;
    lift_ci?: [number, number];
    revenue?: number;
    revenue_ci?: [number, number];
    share_of_buyers?: number;
  };
  counsellor: CounsellorView;
  budget: BudgetView & { days_in_month: number };
  coupons_kept: {
    days: number;
    decisions: number;
    usual: { coupons: number; to_buyers_anyway: number };
    ours: { coupons: number; to_buyers_anyway: number };
    kept: number;
    discount_given: number;
    purchases_with_discount: number;
  };
  average_fee_paid: number;
}

const TONE = { good: "good", neutral: "neutral", warn: "warn" } as const;

/** The owner's two numbers: saving one keeps the other as it is. */
function useSaveSettings() {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: (body: { monthly_discount_budget: number | null; counsellor_monthly_cost: number }) =>
      api.put<PlannerData>("/planner/settings", body),
    onSuccess: (d) => {
      qc.setQueryData(["planner"], d);
      void qc.invalidateQueries({ queryKey: ["pipeline"] });
      void qc.invalidateQueries({ queryKey: ["money"] });
      toast({ tone: "good", text: "Saved. The CRM uses it from its next decision." });
    },
    onError: (e) => toast({ tone: "bad", text: errorText(e) }),
  });
}

function amount(text: string): number | null {
  const v = text.replace(/[,\s₹]/g, "");
  if (v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) && n >= 0 ? n : NaN;
}

function BudgetForm({ data }: { data: PlannerData }) {
  const save = useSaveSettings();
  const [value, setValue] = useState(data.budget.budget === null ? "" : String(Math.round(data.budget.budget)));
  const n = amount(value);
  return (
    <form
      className="flex flex-wrap items-end gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (!Number.isNaN(n))
          save.mutate({ monthly_discount_budget: n, counsellor_monthly_cost: data.counsellor.monthly_cost });
      }}
    >
      <Field label="Monthly discount budget (₹)" hint="Empty: no budget" className="min-w-0 flex-1 basis-48">
        <Input inputMode="numeric" value={value} onChange={(e) => setValue(e.target.value)} placeholder="No budget" />
      </Field>
      <Button type="submit" loading={save.isPending} disabled={Number.isNaN(n)}>
        Save
      </Button>
    </form>
  );
}

function CostForm({ data }: { data: PlannerData }) {
  const save = useSaveSettings();
  const [value, setValue] = useState(String(Math.round(data.counsellor.monthly_cost)));
  const n = amount(value);
  return (
    <form
      className="flex flex-wrap items-end gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (n !== null && !Number.isNaN(n))
          save.mutate({ monthly_discount_budget: data.budget.budget, counsellor_monthly_cost: n });
      }}
    >
      <Field label="What a counsellor costs a month (₹)" className="min-w-0 flex-1 basis-48">
        <Input inputMode="numeric" value={value} onChange={(e) => setValue(e.target.value)} />
      </Field>
      <Button type="submit" loading={save.isPending} disabled={n === null || Number.isNaN(n)}>
        Save
      </Button>
    </form>
  );
}

export default function Planner() {
  const { can } = useSession();
  const data = useQuery({
    queryKey: ["planner"],
    queryFn: () => api.get<PlannerData>("/planner"),
    refetchInterval: 60_000,
  });
  return (
    <>
      <PageHeader
        title="Planner"
        description="The month in rupees: what the team's work adds, and what one more counsellor or more discount money would add, worked out from the CRM's own decisions of the last week."
      />
      <QueryView query={data} what="the planner">
        {(d) => {
          const cv = counsellorVerdict(d.counsellor);
          const bv = budgetVerdict(d.budget);
          const b = d.budget;
          const t = d.team;
          const k = d.coupons_kept;
          return (
            <>
              <KpiStrip
                items={[
                  {
                    label: `Revenue in ${d.month.label}`,
                    value: compactMoney(d.month.revenue),
                    detail: `${plural(d.month.purchases, "purchase")}, day ${d.month.day} of ${d.month.days_in_month}`,
                  },
                  {
                    label: "Comes in anyway",
                    value: compactMoney(d.pipeline.anyway),
                    detail: `open leads, next ${d.pipeline.window_days} days`,
                  },
                  {
                    label: "The team can add",
                    value: compactMoney(d.pipeline.add),
                    detail: `with the best step for ${int(d.pipeline.work)} leads`,
                  },
                  {
                    label: "Discount kept this week",
                    value: compactMoney(k.kept),
                    detail: "against a coupon for every left cart",
                  },
                ]}
              />

              <Section
                id="team"
                title="What the team's work adds"
                description={`Learners who joined at least ${t.days} days ago: those the CRM worked on against the control group it never contacts. Because the control group is chosen at random, the difference is what the team's steps add.`}
              >
                {typeof t.lift === "number" && t.lift_ci ? (
                  <Panel>
                    <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                      <div>
                        <dt className="text-[12.5px] text-muted">Worked on, bought within {t.days} days</dt>
                        <dd className="num text-[24px] font-semibold text-ink">{pct(t.worked_on.rate, 1)}</dd>
                        <dd className="text-[12.5px] text-muted">{int(t.worked_on.people)} people</dd>
                      </div>
                      <div>
                        <dt className="text-[12.5px] text-muted">Never contacted</dt>
                        <dd className="num text-[24px] font-semibold text-ink">{pct(t.control.rate, 1)}</dd>
                        <dd className="text-[12.5px] text-muted">{int(t.control.people)} people</dd>
                      </div>
                      <div>
                        <dt className="text-[12.5px] text-muted">Revenue the team added</dt>
                        <dd className="num text-[24px] font-semibold text-ink">{compactMoney(t.revenue)}</dd>
                        <dd className="num text-[12.5px] text-muted">
                          95% interval {compactMoney(t.revenue_ci?.[0])} to {compactMoney(t.revenue_ci?.[1])}
                        </dd>
                      </div>
                    </dl>
                    <p className="mt-3 text-[13.5px] text-ink-2">
                      The team&apos;s steps raised buying by {(t.lift * 100).toFixed(1)} points (95% interval{" "}
                      {(t.lift_ci[0] * 100).toFixed(1)} to {(t.lift_ci[1] * 100).toFixed(1)}): about{" "}
                      {pct(t.share_of_buyers ?? null)} of the buyers would not have bought without them, at an average
                      fee of {money(d.average_fee_paid)}.
                    </p>
                  </Panel>
                ) : (
                  <Notice tone="info">
                    Not measured yet: the control group needs learners who joined long enough ago.
                  </Notice>
                )}
              </Section>

              <div className="mt-9 grid grid-cols-1 gap-x-6 gap-y-9 lg:grid-cols-2 [&>section]:mt-0">
                <Section id="counsellor" title="Should we hire another counsellor?">
                  <Panel>
                    <div className="flex items-center gap-2">
                      <Badge tone={TONE[cv.tone]}>{cv.label}</Badge>
                    </div>
                    <p className="mt-2 text-[13.5px] text-ink-2">{cv.text}</p>
                    {d.counsellor.enough_data && (
                      <dl className="mt-4 grid grid-cols-2 gap-4 border-t border-line pt-3 text-[13px]">
                        <div>
                          <dt className="text-muted">Today&apos;s {d.counsellor.slots_now} call slots add</dt>
                          <dd className="num text-ink">{money(d.counsellor.slots_now_add_per_month)} a month</dd>
                        </div>
                        <div>
                          <dt className="text-muted">{d.counsellor.extra_slots} more slots would add</dt>
                          <dd className="num text-ink">{money(d.counsellor.extra_adds_per_month)} a month</dd>
                        </div>
                      </dl>
                    )}
                    <p className="mt-3 text-[12.5px] text-muted">
                      Last week&apos;s decisions replayed with more call slots: the extra calls the CRM would then have
                      made, each worth what it adds over the best step without a call.
                    </p>
                    {can("team") && (
                      <div className="mt-4 border-t border-line pt-4">
                        <CostForm data={d} />
                      </div>
                    )}
                  </Panel>
                </Section>
                <Section id="budget" title="Discount budget">
                  <Panel>
                    <div className="flex items-center gap-2">
                      <Badge tone={TONE[bv.tone]}>{bv.label}</Badge>
                    </div>
                    <p className="mt-2 text-[13.5px] text-ink-2">{bv.text}</p>
                    {b.budget !== null && (
                      <>
                        <div
                          role="meter"
                          aria-label="Discount budget used this month"
                          aria-valuemin={0}
                          aria-valuemax={b.budget}
                          aria-valuenow={Math.min(b.spent + b.committed, b.budget)}
                          className="mt-3 h-3 overflow-hidden rounded-[2px] bg-sunken ring-1 ring-inset ring-line"
                        >
                          <div
                            className="h-full bg-brand"
                            style={{
                              width: `${Math.min(100, (100 * (b.spent + b.committed)) / Math.max(b.budget, 1))}%`,
                            }}
                          />
                        </div>
                        <dl className="mt-3 grid grid-cols-2 gap-3 text-[13px] sm:grid-cols-4">
                          <div>
                            <dt className="text-muted">Budget</dt>
                            <dd className="num text-ink">{money(b.budget)} a month</dd>
                          </div>
                          <div>
                            <dt className="text-muted">Given</dt>
                            <dd className="num text-ink">{money(b.spent)}</dd>
                          </div>
                          <div>
                            <dt className="text-muted">In open coupons</dt>
                            <dd className="num text-ink">{money(b.committed)}</dd>
                          </div>
                          <div>
                            <dt className="text-muted">Left, {Math.ceil(b.days_left)} days to go</dt>
                            <dd className="num text-ink">{money(Math.max(b.left ?? 0, 0))}</dd>
                          </div>
                        </dl>
                        {b.extra && b.extra.adds_per_month > 0 && (
                          <p className="mt-3 text-[13px] text-ink-2">
                            {money(b.extra.amount)} more a month would add about {money(b.extra.adds_per_month)} of
                            profit.
                          </p>
                        )}
                      </>
                    )}
                    {can("team") && (
                      <div className="mt-4 border-t border-line pt-4">
                        <BudgetForm data={d} />
                      </div>
                    )}
                  </Panel>
                </Section>
              </div>

              <Section
                id="kept"
                title="Discount kept"
                description={`Left carts and checkouts in the last ${k.days} days, from each lead's chance to buy without a coupon.`}
              >
                <Panel>
                  <p className="text-[13.5px] text-ink-2">
                    A coupon for every left cart or checkout (the usual cart-recovery email, 10% off) would have given
                    about <span className="num font-semibold text-ink">{money(k.usual.to_buyers_anyway)}</span> of
                    discount to people who were going to buy anyway. The CRM&apos;s own decisions sent{" "}
                    {plural(k.ours.coupons, "coupon")} instead of {int(k.usual.coupons)}, giving them about{" "}
                    <span className="num font-semibold text-ink">{money(k.ours.to_buyers_anyway)}</span>.
                  </p>
                  <p className="mt-2 text-[12.5px] text-muted">
                    Discount actually given in that time: {money(k.discount_given)} on{" "}
                    {plural(k.purchases_with_discount, "purchase")}.
                  </p>
                </Panel>
              </Section>
            </>
          );
        }}
      </QueryView>
    </>
  );
}
