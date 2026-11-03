import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { date, dateTime, errorText, int, money, pct, plural, relative, shortDate } from "@xedu/shared/lib";
import { Badge, Button, Notice, Table, Td, Th, useToast } from "@xedu/shared/ui";
import { useState } from "react";
import { api } from "../api/client";
import { useSession } from "../app/session";
import { TrendChart } from "../components/charts";
import { EffectBars } from "../components/effect-bars";
import { SimulatedTag } from "../components/lead-bits";
import { KpiStrip, PageHeader, Panel, Section } from "../components/page";
import { QueryView } from "../components/state";
import { eventLabel } from "../lib/labels";
import {
  fooledOverTime,
  latestChecked,
  overstatement,
  splitEffects,
  type ControlCheck,
  type LearnedEffect,
} from "../lib/learning";

interface SignalPoint {
  signal: string;
  label: string;
  weight: number;
  points: number;
}

interface Run {
  id: number;
  as_of: string;
  reason: string;
  status: string;
  outcomes_known: number;
  new_outcomes: number;
  lead_decision: "kept" | "swapped" | "not_enough_data" | string;
  lead_prob_better: number | null;
  nba_decision: string;
  note: string | null;
  simulated: number;
  learned: {
    points: SignalPoint[];
    outcomes_used: number;
    control: ControlCheck | null;
  } | null;
  nba_detail: {
    champion: string;
    champion_profit_per_lead: number | null;
    challenger_profit_per_lead: Record<string, number>;
    note: string;
  } | null;
}

interface Latency {
  count: number;
  median_ms: number;
  p95_ms: number;
  max_ms: number;
}

interface Overview {
  counts: { control_group: number };
  runs: Run[];
  status: {
    outcomes_known: number;
    new_outcomes: number;
    min_new_outcomes: number;
    latency: Record<string, Latency>;
  };
  lead_model: {
    learned_signals?: SignalPoint[];
    own_effects?: LearnedEffect[];
    live?: { outcomes_used?: number; learned_as_of?: string } | null;
  } | null;
  feed: { kind: string; what: string; name: string; at: string; simulated: boolean }[];
  settings: {
    swap_confidence: number;
    min_new_outcomes: number;
    window_days: number;
    control_share: number;
  };
}

const LATENCY_LABEL: Record<string, string> = {
  event_to_score: "A website event to a new score",
  trigger_to_action: "A trigger to the step being taken",
  pipeline_board: "Drawing the pipeline board",
};

const DECISION_TEXT: Record<string, string> = {
  kept: "Kept",
  swapped: "Replaced",
  not_enough_data: "Not enough data yet",
};

const LEAD_DECISION: Record<string, string> = {
  kept: "kept the score in use",
  swapped: "replaced the score in use with the new one",
  not_enough_data: "waited for more outcomes",
};

/** How far an expectation is from what happened, in plain words: "on target", "3 points high". */
function accuracyText(expected: number | null | undefined, actual: number | null | undefined): string {
  if (typeof expected !== "number" || typeof actual !== "number") return "Not checked yet";
  const gap = Math.round((expected - actual) * 100);
  if (gap === 0) return "On target";
  return `${Math.abs(gap)} ${Math.abs(gap) === 1 ? "point" : "points"} ${gap > 0 ? "high" : "low"}`;
}

function effectItems(effects: readonly LearnedEffect[]) {
  return effects.map((e) => ({ key: e.input, label: e.label, points: e.points }));
}

function RunDetail({ run }: { run: Run }) {
  const c = run.learned?.control;
  const n = run.nba_detail;
  return (
    <div className="grid grid-cols-1 gap-6 bg-sunken/50 px-4 py-4 lg:grid-cols-2">
      <div className="text-[13px]">
        <p className="mb-1 font-semibold text-ink">Lead score</p>
        {c && c.people > 0 ? (
          <p className="text-ink-2">
            Checked on {plural(c.people, "person", "people")} the team never contacted: {pct(c.actual)} bought; the
            score in use expected {pct(c.predicted.champion)}, the new one {pct(c.predicted.challenger)}.
          </p>
        ) : (
          <p className="text-muted">Not enough never-contacted people with a known outcome yet.</p>
        )}
      </div>
      <div className="text-[13px]">
        <p className="mb-1 font-semibold text-ink">Next-best-action</p>
        {n ? (
          <>
            <p className="text-ink-2">
              In use: {money(n.champion_profit_per_lead, "none yet")} extra profit per lead on held-out decisions
              {Object.entries(n.challenger_profit_per_lead).length > 0 &&
                `; new: ${Object.values(n.challenger_profit_per_lead)
                  .map((v) => money(v))
                  .join(", ")}`}
              .
            </p>
            <p className="mt-1 text-muted">{n.note}</p>
          </>
        ) : (
          <p className="text-muted">No comparison in this update.</p>
        )}
      </div>
    </div>
  );
}

function Runs({ runs }: { runs: Run[] }) {
  const [open, setOpen] = useState<number | null>(null);
  return (
    <Table label="Updates">
      <thead>
        <tr>
          <Th>Date</Th>
          <Th className="text-right">Outcomes</Th>
          <Th>Lead score</Th>
          <Th>Next-best-action</Th>
          <Th aria-label="Details" />
        </tr>
      </thead>
      <tbody>
        {runs.map((r) => (
          <RunRow key={r.id} run={r} open={open === r.id} toggle={() => setOpen(open === r.id ? null : r.id)} />
        ))}
      </tbody>
    </Table>
  );
}

function RunRow({ run: r, open, toggle }: { run: Run; open: boolean; toggle: () => void }) {
  return (
    <>
      <tr>
        <Td>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-ink">{dateTime(r.as_of)}</span>
            {r.simulated ? <SimulatedTag /> : null}
          </div>
          <span className="block text-[12.5px] text-muted">
            {r.reason === "history" ? "During the history" : r.reason === "manual" ? "Run by hand" : "Automatic"}
          </span>
        </Td>
        <Td className="num text-right">
          {int(r.outcomes_known)}
          <span className="block text-[12px] text-muted">{int(r.new_outcomes)} new</span>
        </Td>
        <Td>
          <Badge tone={r.lead_decision === "swapped" ? "good" : "neutral"}>
            {DECISION_TEXT[r.lead_decision] ?? r.lead_decision}
          </Badge>
        </Td>
        <Td>
          <Badge tone={r.nba_decision === "swapped" ? "good" : "neutral"}>
            {DECISION_TEXT[r.nba_decision] ?? r.nba_decision}
          </Badge>
        </Td>
        <Td className="text-right">
          <Button size="sm" variant="ghost" aria-expanded={open} onClick={toggle}>
            {open ? "Hide" : "Details"}
          </Button>
        </Td>
      </tr>
      {open && (
        <tr>
          <td colSpan={5} className="border-b border-line p-0">
            <RunDetail run={r} />
            {r.note && <p className="bg-sunken/50 px-4 pb-4 text-[12.5px] text-muted">{r.note}</p>}
          </td>
        </tr>
      )}
    </>
  );
}

export default function Learning() {
  const { can } = useSession();
  const qc = useQueryClient();
  const toast = useToast();
  const data = useQuery({
    queryKey: ["learning"],
    queryFn: () => api.get<Overview>("/learning/overview"),
    refetchInterval: 30_000,
  });
  const run = useMutation({
    mutationFn: () =>
      api.post<{ message?: string; status?: string; lead_decision?: string; nba_decision?: string }>("/learning/run"),
    onSuccess: (r) => {
      const lead = DECISION_TEXT[r.lead_decision ?? ""]?.toLowerCase();
      const nba = DECISION_TEXT[r.nba_decision ?? ""]?.toLowerCase();
      toast({
        tone: r.status === "busy" ? "info" : "good",
        text:
          r.message ?? `Update finished. Lead score: ${lead ?? "no change"}. Next-best-action: ${nba ?? "no change"}.`,
      });
      void qc.invalidateQueries({ queryKey: ["learning"] });
      void qc.invalidateQueries({ queryKey: ["model"] });
    },
    onError: (e) => toast({ tone: "bad", text: errorText(e) }),
  });

  return (
    <>
      <PageHeader
        title="Learning loop"
        description="The lead score and next-best-action learn from every outcome. A new version replaces the one in use only when it predicts better for the leads the team never contacts, so the team's own follow-ups cannot fool it."
        actions={
          can("marketing") ? (
            <Button variant="primary" loading={run.isPending} onClick={() => run.mutate()}>
              Update now
            </Button>
          ) : undefined
        }
      />
      <QueryView query={data} what="the learning loop">
        {(d) => {
          const checked = latestChecked(d.runs);
          const c = checked?.control;
          const trend = fooledOverTime(d.runs);
          const effects = splitEffects(d.lead_model?.own_effects);
          const signals = [...(d.lead_model?.learned_signals ?? [])]
            .filter((s) => Math.abs(s.points) >= 0.1)
            .sort((a, b) => b.points - a.points);
          const last = d.runs[0];
          return (
            <>
              <KpiStrip
                items={[
                  {
                    label: "Learned from",
                    value: `${int(d.lead_model?.live?.outcomes_used ?? d.status.outcomes_known)} outcomes`,
                    detail: last ? `Last update ${relative(last.as_of)}` : "No update yet",
                  },
                  {
                    label: "Accuracy on never-contacted leads",
                    value: accuracyText(c?.predicted.challenger, c?.actual),
                    detail: c
                      ? `Expected ${pct(c.predicted.challenger)}, bought ${pct(c.actual)}`
                      : "Needs people of the control group with a known outcome",
                  },
                  {
                    label: "Next update",
                    value: `${int(d.status.new_outcomes)} of ${int(d.status.min_new_outcomes)}`,
                    detail: "new outcomes; then it starts by itself",
                  },
                  {
                    label: "Control group",
                    value: int(d.counts.control_group),
                    detail: `${pct(d.settings.control_share)} of learners, never contacted`,
                  },
                ]}
              />

              <Section
                id="accuracy"
                title="Is the score accurate?"
                description={`The lead score is the chance to buy within ${plural(d.settings.window_days, "day")} if the team does nothing. It is checked on the leads the team never contacts, because nobody's follow-ups shaped what they did.`}
              >
                {checked && c ? (
                  <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
                    <Panel>
                      <dl className="grid grid-cols-2 gap-4">
                        <div>
                          <dt className="text-[12.5px] text-muted">The score expected</dt>
                          <dd className="num text-[26px] font-semibold text-ink">{pct(c.predicted.challenger, 1)}</dd>
                        </div>
                        <div>
                          <dt className="text-[12.5px] text-muted">They bought</dt>
                          <dd className="num text-[26px] font-semibold text-ink">{pct(c.actual, 1)}</dd>
                        </div>
                      </dl>
                      <p className="mt-3 text-[13.5px] text-ink-2">
                        Latest check, {date(checked.as_of)}: {plural(c.people, "person", "people")} the team never
                        contacted ({plural(c.rows, "decision")}). The update{" "}
                        {LEAD_DECISION[checked.lead_decision] ?? ""}
                        {typeof checked.lead_prob_better === "number" &&
                          ` (better in ${pct(checked.lead_prob_better)} of resamples; ${pct(d.settings.swap_confidence)} needed)`}
                        .
                      </p>
                      {typeof c.predicted.naive === "number" && (
                        <p className="mt-2 text-[13px] text-muted">
                          A score retrained the usual way would have expected {pct(c.predicted.naive, 1)} (
                          {Math.round(Math.abs(overstatement(c.predicted.naive, c.actual) ?? 0) * 100)}%{" "}
                          {(overstatement(c.predicted.naive, c.actual) ?? 0) >= 0 ? "too high" : "too low"}): it counts
                          the team&apos;s own follow-ups as lead quality.
                        </p>
                      )}
                    </Panel>
                    {trend.length > 1 ? (
                      <TrendChart
                        title="Expected and actual buying, update by update"
                        data={trend}
                        x="date"
                        xFormat={(v) => shortDate(v)}
                        series={[
                          { key: "ours", label: "The score expected", dashed: true },
                          { key: "actual", label: "They bought" },
                        ]}
                        format={(v) => pct(v, 1)}
                        axisFormat={(v) => pct(v)}
                        dots
                      />
                    ) : (
                      <Notice tone="info">The chart appears after the second update.</Notice>
                    )}
                  </div>
                ) : (
                  <Notice tone="info">
                    Not checked yet: the check needs people of the control group whose outcome is known.
                  </Notice>
                )}
              </Section>

              <div className="mt-9 grid grid-cols-1 gap-x-6 gap-y-9 lg:grid-cols-2 [&>section]:mt-0">
                <Section
                  id="own-steps"
                  title="What the team's work adds, by step"
                  description="Points of buying chance within 14 days for a lead with a 30% chance on their own: leads the CRM worked on after each step, the follow-ups after it included, against similar leads it never contacts. This is kept out of the lead score, so a score never includes the team's own work. To compare the steps on their own, see the learning steps on the Next-best-action page."
                >
                  {effects.steps.length ? (
                    <EffectBars label="What the team's work adds, by step" items={effectItems(effects.steps)} />
                  ) : (
                    <p className="text-[13.5px] text-muted">
                      Not learned yet: the first score the loop adopts stores them.
                    </p>
                  )}
                </Section>
                <Section
                  id="time"
                  title="How time changes the chance to buy"
                  description="Learned from outcomes instead of a hand-set decay rule. Points of buying chance for a typical lead."
                >
                  {effects.time.length ? (
                    <EffectBars label="Learned effects of time" items={effectItems(effects.time)} />
                  ) : (
                    <p className="text-[13.5px] text-muted">
                      Not learned yet: the first score the loop adopts stores them.
                    </p>
                  )}
                </Section>
              </div>

              {signals.length > 0 && (
                <Section
                  id="learned"
                  title="What raises or lowers the chance, learned from your outcomes"
                  description={`Corrections to the starting model from ${int(d.lead_model?.live?.outcomes_used ?? 0)} outcomes of this CRM, in points of buying chance for a typical lead.`}
                >
                  <div className="max-w-3xl">
                    <EffectBars
                      label="Learned corrections"
                      items={signals.map((s) => ({ key: s.signal, label: s.label, points: s.points }))}
                    />
                  </div>
                </Section>
              )}

              <Section
                id="runs"
                title="Updates"
                description={`An update starts when ${int(d.settings.min_new_outcomes)} new outcomes are known. The score in use is replaced only with ${pct(d.settings.swap_confidence)} confidence that the new one is better.`}
              >
                {d.runs.length ? <Runs runs={d.runs} /> : <Notice tone="info">No update yet.</Notice>}
              </Section>

              <div className="mt-9 grid grid-cols-1 gap-x-6 gap-y-9 lg:grid-cols-2 [&>section]:mt-0">
                <Section
                  title="Real-time loop"
                  description="How long the live steps take on this computer, over the last 1,000 of each since the server started."
                >
                  {Object.keys(d.status.latency).length === 0 ? (
                    <Notice tone="info">
                      Nothing measured yet since the server started: the times appear with the first website events.
                    </Notice>
                  ) : (
                    <Table label="Response times">
                      <thead>
                        <tr>
                          <Th>Step</Th>
                          <Th className="text-right">Median</Th>
                          <Th className="text-right">95th percentile</Th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(d.status.latency).map(([k, v]) => (
                          <tr key={k}>
                            <Td className="text-ink">{LATENCY_LABEL[k] ?? k}</Td>
                            <Td className="num text-right">{v.median_ms.toFixed(0)} ms</Td>
                            <Td className="num text-right">{v.p95_ms.toFixed(0)} ms</Td>
                          </tr>
                        ))}
                      </tbody>
                    </Table>
                  )}
                </Section>
                <Section title="Happening now" description="The latest events the loop learns from.">
                  <ul className="rounded-md border border-line bg-surface">
                    {d.feed.slice(0, 10).map((f, i) => (
                      <li
                        key={i}
                        className="flex flex-wrap items-baseline gap-x-3 border-b border-line px-4 py-2 text-[13px] last:border-b-0"
                      >
                        <span className="text-ink">{f.name}</span>
                        <span className="text-ink-2">
                          {f.kind === "event" ? eventLabel(f.what).toLowerCase() : f.what.replace(/_/g, " ")}
                        </span>
                        {f.simulated && <SimulatedTag />}
                        <span className="ml-auto text-muted">{relative(f.at)}</span>
                      </li>
                    ))}
                  </ul>
                </Section>
              </div>
            </>
          );
        }}
      </QueryView>
    </>
  );
}
