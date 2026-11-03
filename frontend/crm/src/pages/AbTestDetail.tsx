import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, dateTime, errorText, int, money, pct, plural, points, pointsPlain } from "@xedu/shared/lib";
import { Button, buttonClass, EmptyState, Notice, Table, Tabs, Td, Th, useToast } from "@xedu/shared/ui";
import { ChevronLeft, FlaskConical } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { api } from "../api/client";
import type { AbPlan, AbResults, AbTest } from "../api/types";
import { useSession } from "../app/session";
import { VerdictBadge } from "../components/ab";
import { IntervalPlot, TrendChart } from "../components/charts";
import { SimulatedTag } from "../components/lead-bits";
import { Section } from "../components/page";
import { Loading, LoadError } from "../components/state";

interface ResultsResponse {
  test: AbTest;
  plan?: AbPlan;
  results: AbResults | null;
}

const DIMENSIONS = [
  { id: "tier", label: "Tier" },
  { id: "occupation", label: "Occupation" },
  { id: "device", label: "Device" },
  { id: "source", label: "Came from" },
] as const;

type Dim = (typeof DIMENSIONS)[number]["id"];

function armName(arm: string, test: AbTest): string {
  if (arm === "control") return "Control (no email)";
  const v = test.variants.find((x) => x.key === arm);
  return v ? `${arm}: ${v.label}` : arm;
}

function Segments({ r, test }: { r: AbResults; test: AbTest }) {
  const [dim, setDim] = useState<Dim>("tier");
  const rows = r.segments[dim] ?? [];
  const arms = r.arms.map((a) => a.arm);
  return (
    <>
      <Tabs<Dim>
        label="Split the results by"
        value={dim}
        onChange={setDim}
        tabs={DIMENSIONS.map((d) => ({ id: d.id, label: d.label }))}
        className="mb-3"
      />
      <Table label={`Results by ${dim}`}>
        <thead>
          <tr>
            <Th>{DIMENSIONS.find((d) => d.id === dim)?.label}</Th>
            {arms.map((a) => (
              <Th key={a} className="text-right">
                {armName(a, test)}
              </Th>
            ))}
            <Th>Best</Th>
          </tr>
        </thead>
        <tbody>
          {rows.map((s) => (
            <tr key={s.value}>
              <Td className="text-ink">{s.value}</Td>
              {arms.map((a) => {
                const x = s.arms[a];
                return (
                  <Td key={a} className="num text-right">
                    {x ? pct(x.rate, 1, "None") : ""}
                    <span className="block text-[12px] text-muted">{x ? `${int(x.n)} people` : ""}</span>
                  </Td>
                );
              })}
              <Td className="text-ink-2">
                {s.best ? `Variant ${s.best}` : s.enough ? "No clear best" : "Too few people"}
              </Td>
            </tr>
          ))}
        </tbody>
      </Table>
      <p className="mt-2 text-[12.5px] text-muted">
        Exploratory: with many groups, some differences appear by chance. Use them to plan the next test, not to decide.
      </p>
    </>
  );
}

function Results({ r, test }: { r: AbResults; test: AbTest }) {
  const qc = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  const { can } = useSession();
  const apply = useMutation({
    mutationFn: (variant: string) =>
      api.post<{ campaign_id: number; message: string }>(`/ab-tests/${test.id}/apply`, { variant }),
    onSuccess: (x) => {
      toast({ tone: "good", text: x.message });
      void qc.invalidateQueries({ queryKey: ["campaigns"] });
      navigate("/campaigns");
    },
    onError: (e) => toast({ tone: "bad", text: errorText(e) }),
  });
  const what = r.metric === "bought" ? "bought" : "clicked";
  const series = r.arms.map((a) => ({ key: a.arm, label: armName(a.arm, test) }));
  return (
    <>
      {r.srm_problem && (
        <Notice tone="bad" title="The random split looks broken" className="mb-6">
          The groups are not the sizes the random split should give (sample-ratio test p = {r.srm_p?.toFixed(4)}). Do
          not trust these results until the cause is found.
        </Notice>
      )}
      <Section
        title="Groups"
        description={`Share who ${what} within ${plural(r.window_days, "day")} of the email, with a 95% interval.`}
      >
        <Table label="Groups">
          <thead>
            <tr>
              <Th>Group</Th>
              <Th className="text-right">People</Th>
              <Th className="text-right">{r.metric === "bought" ? "Bought" : "Clicked"}</Th>
              <Th className="text-right">Share</Th>
              <Th className="text-right">Revenue per person</Th>
              <Th className="text-right">Profit per person</Th>
              {can("marketing") && <Th aria-label="Actions" />}
            </tr>
          </thead>
          <tbody>
            {r.arms.map((a) => (
              <tr key={a.arm}>
                <Td className="text-ink">{armName(a.arm, test)}</Td>
                <Td className="num text-right">{int(a.n)}</Td>
                <Td className="num text-right">{int(r.metric === "bought" ? a.purchases : a.clicks)}</Td>
                <Td className="num text-right">
                  {pct(a.rate, 1, "None")}
                  {a.rate_ci[0] !== null && a.rate_ci[1] !== null && (
                    <span className="block text-[12px] text-muted">
                      {pct(a.rate_ci[0], 1)} to {pct(a.rate_ci[1], 1)}
                    </span>
                  )}
                </Td>
                <Td className="num text-right">{money(a.revenue_per_person, "")}</Td>
                <Td className="num text-right">{money(a.profit_per_person, "")}</Td>
                {can("marketing") && (
                  <Td className="text-right">
                    {a.arm !== "control" && (
                      <Button
                        size="sm"
                        variant="ghost"
                        loading={apply.isPending && apply.variables === a.arm}
                        onClick={() => apply.mutate(a.arm)}
                      >
                        Use as a campaign
                      </Button>
                    )}
                  </Td>
                )}
              </tr>
            ))}
          </tbody>
        </Table>
      </Section>

      {r.comparisons.length > 0 && (
        <Section
          title={`Difference against ${r.reference === "control" ? "sending nothing" : `variant ${r.reference}`}`}
          description={`In percentage points, with a 95% interval corrected for ${plural(r.bonferroni_comparisons, "comparison")}. An interval across zero is not a clear difference.`}
        >
          <div className="rounded-md border border-line bg-surface px-4">
            <IntervalPlot
              label="Differences"
              format={(v) => points(v)}
              rows={r.comparisons.map((c) => ({
                label: armName(c.variant, test),
                note: `p = ${c.p_adjusted === null ? "not known" : c.p_adjusted.toFixed(4)} after the correction${c.significant ? ", clear" : ""}`,
                value: c.lift,
                low: c.lift_ci[0],
                high: c.lift_ci[1],
                emphasis: c.significant,
              }))}
            />
          </div>
        </Section>
      )}

      {r.curve.length > 1 && (
        <Section title="Day by day" description={`Share of each group who ${what} by each day after the email.`}>
          <TrendChart
            title={`Share who ${what}`}
            data={r.curve}
            x="day"
            xFormat={(d) => `Day ${d}`}
            series={series}
            format={(v) => `${v.toFixed(1)}%`}
            height={240}
          />
        </Section>
      )}

      <Section title="By group of people">
        <Segments r={r} test={test} />
      </Section>

      <p className="mt-6 text-[12.5px] text-muted">
        {r.final
          ? "Final: the outcome window has passed for everyone."
          : `Still counting: day ${r.days_since_start} of ${r.window_days}.`}{" "}
        Each group needed about {int(r.planned_per_arm)} people for a difference of {pointsPlain(test.mde ?? 0.05)}; the
        smallest has {int(r.smallest_arm)}
        {r.detectable_lift ? `, enough to notice ${pointsPlain(r.detectable_lift, 1)} or more` : ""}.
      </p>
    </>
  );
}

export default function AbTestDetail() {
  const { testId } = useParams();
  const id = Number(testId);
  const qc = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  const { can } = useSession();
  const data = useQuery({
    queryKey: ["ab-tests", id],
    queryFn: () => api.get<ResultsResponse>(`/ab-tests/${id}/results`),
    refetchInterval: 30_000,
    enabled: Number.isFinite(id),
  });
  const send = useMutation({
    mutationFn: () => api.post<{ message: string }>(`/ab-tests/${id}/send`),
    onSuccess: (r) => {
      toast({ tone: "good", text: r.message });
      void qc.invalidateQueries({ queryKey: ["ab-tests"] });
    },
    onError: (e) => toast({ tone: "bad", text: errorText(e) }),
  });
  const remove = useMutation({
    mutationFn: () => api.del(`/ab-tests/${id}`),
    onSuccess: () => {
      toast({ tone: "good", text: "Draft deleted." });
      void qc.invalidateQueries({ queryKey: ["ab-tests"] });
      navigate("/ab-tests");
    },
    onError: (e) => toast({ tone: "bad", text: errorText(e) }),
  });

  if (data.isPending) return <Loading label="Loading the test" />;
  if (data.isError) {
    if (data.error instanceof ApiError && data.error.status === 404) {
      return (
        <EmptyState
          icon={FlaskConical}
          title="This test does not exist"
          action={
            <Link to="/ab-tests" className={buttonClass()}>
              Back to the tests
            </Link>
          }
        />
      );
    }
    return <LoadError error={data.error} what="the test" retry={() => void data.refetch()} />;
  }
  const { test, plan, results } = data.data;
  const verdict = results?.verdict ?? test.verdict;
  const tone =
    verdict?.status === "winner"
      ? "good"
      : verdict?.status === "broken" || verdict?.status === "loser"
        ? "bad"
        : "info";

  return (
    <>
      <Link to="/ab-tests" className="mb-3 inline-flex items-center gap-1 text-[13px] text-muted hover:text-ink">
        <ChevronLeft aria-hidden className="size-4" />
        A/B tests
      </Link>
      <header className="mb-6">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-[22px] font-semibold leading-tight text-ink">{test.name}</h1>
          <VerdictBadge v={verdict} state={test.state} />
          {test.simulated && <SimulatedTag />}
        </div>
        <p className="mt-1 text-[13.5px] text-muted">
          {test.tier}. Measures {test.metric === "purchase" ? "buying a course" : "clicks"}.{" "}
          {test.started_at ? `Sent ${dateTime(test.started_at)}.` : "Not sent yet."}
        </p>
        {test.hypothesis && <p className="mt-2 max-w-[75ch] text-[14px] text-ink-2">{test.hypothesis}</p>}
      </header>

      {verdict && test.state !== "draft" && (
        <Notice tone={tone} title={verdict.headline} className="mb-8 max-w-3xl">
          {verdict.detail}
        </Notice>
      )}

      {test.state === "draft" && (
        <div className="mb-8 max-w-3xl">
          {plan && (
            <Notice
              tone={plan.enough ? "info" : "warn"}
              title={plan.enough ? "Ready to send" : "The audience is small for this test"}
            >
              About {int(plan.audience)} people would take part, {int(plan.per_arm_available)} per group. Each group
              needs about {int(plan.planned_per_arm)} to notice a difference of {pointsPlain(plan.mde)}.
            </Notice>
          )}
          {can("marketing") && (
            <div className="mt-4 flex gap-2">
              <Button variant="primary" loading={send.isPending} onClick={() => send.mutate()}>
                Send the test
              </Button>
              <Button variant="danger" loading={remove.isPending} onClick={() => remove.mutate()}>
                Delete the draft
              </Button>
            </div>
          )}
        </div>
      )}

      {results && <Results r={results} test={test} />}

      <Section title="The emails" className="mt-10">
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {test.variants.map((v) => (
            <article key={v.key} className="rounded-md border border-line bg-surface">
              <header className="border-b border-line px-4 py-2.5">
                <p className="text-[13px] font-semibold text-ink">
                  Variant {v.key}: {v.label}
                </p>
                {v.offer_pct > 0 && <p className="text-[12.5px] text-muted">With a {v.offer_pct}% coupon</p>}
              </header>
              <div className="px-4 py-3">
                <p className="text-[14px] font-medium text-ink">{v.subject}</p>
                <p className="mt-2 whitespace-pre-line text-[13.5px] leading-relaxed text-ink-2">{v.body}</p>
              </div>
            </article>
          ))}
        </div>
      </Section>
    </>
  );
}
