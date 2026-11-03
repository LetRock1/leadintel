import { useQuery } from "@tanstack/react-query";
import { int, money, pct, shortDate } from "@xedu/shared/lib";
import { Notice, Table, Td, Th } from "@xedu/shared/ui";
import { api } from "../api/client";
import { useCapacity } from "../api/queries";
import type { ActionKey, NbaPerformance } from "../api/types";
import { CapacityMeter } from "../components/capacity";
import { IntervalPlot, TrendChart } from "../components/charts";
import { PageHeader, Panel, Section } from "../components/page";
import { Loading, LoadError, QueryView } from "../components/state";
import { ACTION_ORDER, actionLabel } from "../lib/labels";

const POLICY_NAME: Record<string, string> = {
  "follow the model": "Follow the model",
  "do nothing": "Do nothing for everyone",
  "information email to all": "Information email to everyone",
};

export default function Decisions() {
  const capacity = useCapacity(30_000);
  const perf = useQuery({
    queryKey: ["nba", "performance"],
    queryFn: () => api.get<NbaPerformance>("/nba/performance"),
    refetchInterval: 60_000,
  });

  return (
    <>
      <PageHeader
        title="Next-best-action"
        description="For every lead the CRM compares each step it could take and picks the one with the highest expected extra profit. This page shows how call slots are priced and how well the choices are doing."
      />

      <Section
        id="capacity"
        title="Call slots"
        description="Counsellors can make only so many calls a day. Instead of first come, first served, each call slot has a price: the extra profit of the best call it would crowd out later today. A call is booked only when it beats that price."
      >
        {capacity.isPending ? (
          <Loading />
        ) : capacity.isError ? (
          <LoadError error={capacity.error} what="the call slots" retry={() => void capacity.refetch()} />
        ) : (
          <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
            <CapacityMeter capacity={capacity.data} showPrice />
            {capacity.data.history.length > 1 ? (
              <TrendChart
                title="Price of a call slot"
                description="Each time it was worked out again, last 14 days"
                data={capacity.data.history}
                x="computed_at"
                xFormat={(d) => `${shortDate(d)}, ${d.slice(11, 16)}`}
                series={[{ key: "price", label: "Price" }]}
                format={(v) => money(v)}
                height={180}
              />
            ) : (
              <Panel>
                <p className="text-[14px] font-semibold text-ink">Price of a call slot</p>
                <p className="mt-1 text-[13.5px] text-muted">
                  The price is worked out again every 15 minutes while decisions are made. A chart appears after the
                  second time.
                </p>
              </Panel>
            )}
          </div>
        )}
      </Section>

      <QueryView query={perf} what="the decision results">
        {(p) => {
          const estimates = Object.entries(p.policy_estimates);
          const slice = ACTION_ORDER.filter((a) => p.randomised_slice[a]).map((a) => ({
            action: actionLabel(a, true),
            rate: p.randomised_slice[a].rate ?? 0,
            n: p.randomised_slice[a].n,
          }));
          return (
            <>
              <Section
                id="value"
                title="What each way of choosing is worth"
                description="What a lead would bring on average if every decision were made one way, worked out from past decisions. Each line shows the estimate and the range it is 95% likely to be in."
              >
                <Panel padded={false} className="px-4">
                  <IntervalPlot
                    label="Profit per lead by policy"
                    format={(v) => money(v)}
                    rows={estimates.map(([name, e]) => ({
                      label: POLICY_NAME[name] ?? name,
                      note: `${int(e.matched_decisions)} matching decisions${e.enough ? "" : ", not enough yet"}`,
                      value: e.snips_profit_per_lead,
                      low: e.ci95?.[0] ?? null,
                      high: e.ci95?.[1] ?? null,
                      emphasis: name === "follow the model",
                    }))}
                  />
                </Panel>
                <p className="mt-3 max-w-[80ch] text-[13.5px] text-ink-2">{p.verdict}</p>
                <p className="mt-1 max-w-[80ch] text-[12.5px] text-muted">{p.note}</p>
              </Section>

              <Section
                id="random"
                title="Learning steps"
                description="A small share of decisions take a random allowed step. Their results compare the steps fairly, because nothing about the person chose the step."
              >
                {slice.length ? (
                  <TrendChart
                    title="Bought within the outcome window, by step"
                    description={`${int(slice.reduce((s, r) => s + r.n, 0))} random decisions with a known outcome`}
                    kind="bar"
                    data={slice}
                    x="action"
                    series={[{ key: "rate", label: "Share who bought" }]}
                    format={(v) => pct(v)}
                    height={220}
                  />
                ) : (
                  <Notice tone="info">No random decisions with a known outcome yet.</Notice>
                )}
              </Section>

              <Section
                id="steps"
                title="Decisions by step"
                description={`${int(p.decisions_total)} decisions, ${int(p.decisions_with_outcome)} with a known outcome.`}
              >
                <Table label="Decisions by step">
                  <thead>
                    <tr>
                      <Th>Step</Th>
                      <Th className="text-right">Decisions</Th>
                      <Th className="text-right">Random</Th>
                      <Th className="text-right">Outcome known</Th>
                      <Th className="text-right">Bought</Th>
                      <Th className="text-right">Share who bought</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {ACTION_ORDER.filter((a) => p.by_action[a]).map((a: ActionKey) => {
                      const r = p.by_action[a];
                      return (
                        <tr key={a}>
                          <Td className="text-ink">{actionLabel(a)}</Td>
                          <Td className="num text-right">{int(r.decisions)}</Td>
                          <Td className="num text-right">{int(r.explore)}</Td>
                          <Td className="num text-right">{int(r.known_outcome)}</Td>
                          <Td className="num text-right">{int(r.converted)}</Td>
                          <Td className="num text-right">
                            {pct(r.known_outcome ? r.converted / r.known_outcome : null, 0, "None")}
                          </Td>
                        </tr>
                      );
                    })}
                  </tbody>
                </Table>
                <p className="mt-2 text-[12.5px] text-muted">
                  Shares in this table are not comparable between steps: the model gives each step to different people.
                  The learning steps above are the fair comparison.
                </p>
              </Section>
            </>
          );
        }}
      </QueryView>
    </>
  );
}
