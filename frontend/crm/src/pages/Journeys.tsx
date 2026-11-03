import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { cn, int, pct, points, useChartColors } from "@xedu/shared/lib";
import { Segmented, Select, Table, Td, Th } from "@xedu/shared/ui";
import { ArrowRight, EyeOff, RotateCcw } from "lucide-react";
import { useState } from "react";
import { ResponsiveContainer, Sankey, Tooltip, type TooltipContentProps } from "recharts";
import type { LinkProps, NodeProps } from "recharts/types/chart/Sankey";
import { api } from "../api/client";
import { PageHeader, Panel, Section } from "../components/page";
import { QueryView } from "../components/state";
import { STAGE_LABEL, TIERS } from "../lib/labels";

interface MapNode {
  name: string;
  layer: "stage" | "group" | "reaction" | "outcome";
}

interface MapLink {
  source: number;
  target: number;
  value: number;
  conversion: number;
}

interface JourneyData {
  days: number;
  decisions: number;
  with_outcome: number;
  sankey: { nodes: MapNode[]; links: MapLink[] };
  funnel: { stages: { stage: string; people: number }[]; signed_up: number };
  dropoffs: { from: string; to: string; lost: number; lost_share: number }[];
  top_paths: {
    stage: string;
    action: string;
    action_label: string;
    reaction: string;
    reaction_label: string;
    n: number;
    conversion: number;
    conversion_weighted: number;
  }[];
  action_effects: {
    stage: string;
    action: string;
    label: string;
    n: number;
    rate: number;
    nothing_rate: number;
    lift: number;
  }[];
}

function Funnel({ f }: { f: JourneyData["funnel"] }) {
  const c = useChartColors();
  const max = Math.max(...f.stages.map((s) => s.people), 1);
  return (
    <Panel>
      <ol className="flex flex-col gap-3">
        {f.stages.map((s, i) => {
          const prev = i > 0 ? f.stages[i - 1].people : null;
          return (
            <li
              key={s.stage}
              className="grid grid-cols-[minmax(0,10rem)_minmax(0,1fr)_7rem] items-center gap-4 text-[13.5px]"
            >
              <span className="text-ink">{STAGE_LABEL[s.stage] ?? s.stage}</span>
              <span aria-hidden className="h-5 overflow-hidden rounded-xs" style={{ background: c.grid }}>
                <span
                  className="block h-full rounded-xs"
                  style={{ width: `${(100 * s.people) / max}%`, background: c.series[0] }}
                />
              </span>
              <span className="text-right">
                <span className="num font-medium text-ink">{int(s.people)}</span>
                <span className="num block text-[12px] text-muted">
                  {i === 0
                    ? s.people
                      ? "everyone who signed up"
                      : ""
                    : prev
                      ? `${pct(s.people / prev)} of the stage before`
                      : ""}
                </span>
              </span>
            </li>
          );
        })}
      </ol>
    </Panel>
  );
}

const LAYERS: { layer: MapNode["layer"]; label: string }[] = [
  { layer: "stage", label: "Stage" },
  { layer: "group", label: "Step the CRM took" },
  { layer: "reaction", label: "Reaction within 3 days" },
  { layer: "outcome", label: "In the end" },
];

const STEP_GROUP_LABEL: Record<string, string> = {
  Nothing: "No step",
  Email: "Email",
  Coupon: "Coupon email",
  Call: "Call",
  WhatsApp: "WhatsApp",
};

function nodeLabel(n: MapNode): string {
  if (n.layer === "stage") return STAGE_LABEL[n.name] ?? n.name;
  if (n.layer === "group") return STEP_GROUP_LABEL[n.name] ?? n.name;
  if (n.layer === "outcome") return n.name === "Bought" ? "Bought" : "Not bought yet";
  return n.name === "Bought" ? "Bought within 3 days" : n.name;
}

/** The journey map: stage, the step the CRM took, the reaction and the outcome, with step flow cards, a visual map, and a table of the same flows. */
function JourneyMap({ map, topPaths }: { map: JourneyData["sankey"]; topPaths?: JourneyData["top_paths"] }) {
  const c = useChartColors();
  const [view, setView] = useState<"flows" | "map" | "table">("flows");
  const [hidden, setHidden] = useState(false);
  const lastLayer = map.nodes.reduce(
    (m, n) =>
      Math.max(
        m,
        LAYERS.findIndex((l) => l.layer === n.layer),
      ),
    0,
  );
  const flows = map.links.map((l) => ({ ...l, from: map.nodes[l.source], to: map.nodes[l.target] }));

  if (hidden) {
    return (
      <div className="flex items-center justify-between rounded-md border border-line bg-surface px-4 py-3 text-[13px] text-muted">
        <span>Journey map is hidden.</span>
        <button
          type="button"
          onClick={() => setHidden(false)}
          className="flex items-center gap-1.5 font-medium text-brand hover:underline"
        >
          <RotateCcw className="size-3.5" />
          Show journey map
        </button>
      </div>
    );
  }

  const MapNodeShape = ({ x, y, width, height, payload }: NodeProps) => {
    const node = payload as unknown as MapNode & { value: number; depth: number };
    const end = node.depth >= lastLayer;
    const tx = end ? x - 8 : x + width + 8;
    return (
      <g>
        <rect x={x} y={y} width={width} height={Math.max(height, 1)} rx={2} fill={c.brand} />
        {/* a halo in the surface colour keeps the label readable where it crosses the bands */}
        <text
          x={tx}
          y={y + height / 2}
          dy="0.35em"
          textAnchor={end ? "end" : "start"}
          fontSize={12}
          fill={c.ink}
          stroke={c.surface}
          strokeWidth={4}
          strokeLinejoin="round"
          paintOrder="stroke"
        >
          {nodeLabel(node)}
          <tspan fill={c.text}> {int(node.value)}</tspan>
        </text>
      </g>
    );
  };

  const MapLinkShape = (p: LinkProps) => {
    const conv = (p.payload as unknown as { conversion?: number }).conversion ?? 0;
    // Semantic color coding based on conversion performance instead of confusing muddy opacity
    const strokeColor = conv >= 0.25 ? "#10b981" : conv >= 0.1 ? "#6366f1" : "#94a3b8";
    const opacity = 0.28 + 0.5 * Math.min(1, Math.max(0, conv));
    return (
      <path
        d={`M${p.sourceX},${p.sourceY}C${p.sourceControlX},${p.sourceY} ${p.targetControlX},${p.targetY} ${p.targetX},${p.targetY}`}
        fill="none"
        stroke={strokeColor}
        strokeOpacity={opacity}
        strokeWidth={Math.max(1.5, p.linkWidth)}
      />
    );
  };

  const tip = ({ active, payload }: Partial<TooltipContentProps<number, string>>) => {
    const item = payload?.[0]?.payload as
      { source?: MapNode & { value: number }; target?: MapNode; value?: number; payload?: unknown } | undefined;
    if (!active || !item) return null;
    const link = (item.payload ?? item) as { source?: MapNode; target?: MapNode; value?: number; conversion?: number };
    return (
      <div className="min-w-48 rounded-sm border border-line bg-raised px-3 py-2 text-[12.5px] shadow-overlay">
        {link.source && link.target ? (
          <>
            <p className="font-medium text-ink">
              {nodeLabel(link.source)} to {nodeLabel(link.target)}
            </p>
            <p className="mt-0.5 flex text-ink-2">
              Decisions<span className="num ml-auto pl-4 font-medium text-ink">{int(link.value)}</span>
            </p>
            <p className="flex text-ink-2">
              Bought in the end
              <span
                className={cn(
                  "num ml-auto pl-4 font-semibold",
                  (link.conversion ?? 0) >= 0.25
                    ? "text-emerald-600 dark:text-emerald-400"
                    : (link.conversion ?? 0) >= 0.1
                      ? "text-indigo-600 dark:text-indigo-400"
                      : "text-ink",
                )}
              >
                {pct(link.conversion, 1)}
              </span>
            </p>
          </>
        ) : (
          <p className="font-medium text-ink">
            {nodeLabel(item as unknown as MapNode)}: {int((item as { value?: number }).value)}
          </p>
        )}
      </div>
    );
  };

  return (
    <figure className="rounded-md border border-line bg-surface">
      <figcaption className="flex flex-wrap items-start gap-3 px-4 pt-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2.5">
            <p className="text-[14px] font-semibold text-ink">Journey map</p>
            <button
              type="button"
              onClick={() => setHidden(true)}
              className="flex items-center gap-1 text-[11.5px] text-muted hover:text-ink"
              title="Hide journey map section"
            >
              <EyeOff className="size-3" /> Hide
            </button>
          </div>
          <p className="mt-0.5 text-[12.5px] text-muted">
            {view === "flows" && "Top converting paths learners take from their initial trigger to final purchase."}
            {view === "map" && "Full pathway diagram: band thickness reflects volume; color indicates conversion rate."}
            {view === "table" && "Complete decision flow metrics across stages and responses."}
          </p>
        </div>
        <Segmented
          size="sm"
          label="Journey map: show as"
          value={view}
          onChange={(v) => setView(v as "flows" | "map" | "table")}
          options={[
            { value: "flows", label: "Step flows" },
            { value: "map", label: "Sankey map" },
            { value: "table", label: "Table" },
          ]}
        />
      </figcaption>

      {view === "flows" ? (
        <div className="p-4">
          {!topPaths || topPaths.length === 0 ? (
            <p className="py-4 text-center text-[13px] text-muted">Not enough journey data yet to display top flows.</p>
          ) : (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              {topPaths.slice(0, 6).map((p, i) => {
                const isHigh = p.conversion_weighted >= 0.25;
                const isMed = p.conversion_weighted >= 0.1;
                return (
                  <div
                    key={i}
                    className="flex flex-col justify-between rounded-md border border-line bg-canvas/40 p-3.5 transition-colors hover:border-brand/40"
                  >
                    <div>
                      <div className="flex items-center justify-between gap-2 border-b border-line/60 pb-2 text-[12px]">
                        <span className="font-semibold text-ink">Pathway #{i + 1}</span>
                        <span className="num font-medium text-muted">{int(p.n)} learners</span>
                      </div>
                      <div className="mt-3 flex flex-wrap items-center gap-1.5 text-[12px]">
                        <span className="rounded border border-line/60 bg-surface px-2 py-1 font-medium text-ink-2">
                          {STAGE_LABEL[p.stage] ?? p.stage}
                        </span>
                        <ArrowRight className="size-3 shrink-0 text-muted" />
                        <span className="rounded bg-brand-soft px-2 py-1 font-medium text-brand-ink">
                          {p.action_label}
                        </span>
                        <ArrowRight className="size-3 shrink-0 text-muted" />
                        <span className="rounded border border-line/60 bg-surface px-2 py-1 font-medium text-ink-2">
                          {p.reaction_label}
                        </span>
                      </div>
                    </div>
                    <div className="mt-3.5 flex items-center justify-between border-t border-line/60 pt-2 text-[12px]">
                      <span className="text-muted">Final conversion:</span>
                      <span
                        className={cn(
                          "num rounded px-2 py-0.5 font-semibold",
                          isHigh
                            ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                            : isMed
                              ? "bg-indigo-500/10 text-indigo-600 dark:text-indigo-400"
                              : "bg-slate-500/10 text-muted",
                        )}
                      >
                        {pct(p.conversion_weighted, 1)} enrolled
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      ) : view === "map" ? (
        <div className="overflow-x-auto px-4 pb-3 pt-2">
          <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1.5 rounded border border-line/50 bg-canvas/60 px-3 py-1.5 text-[11.5px] text-muted">
            <span className="font-medium text-ink">Legend:</span>
            <span className="flex items-center gap-1.5">
              <span className="inline-block size-2 rounded-full bg-emerald-500" /> High conversion (≥25%)
            </span>
            <span className="flex items-center gap-1.5">
              <span className="inline-block size-2 rounded-full bg-indigo-500" /> Moderate (10–25%)
            </span>
            <span className="flex items-center gap-1.5">
              <span className="inline-block size-2 rounded-full bg-slate-400" /> Low / Drop-off (&lt;10%)
            </span>
            <span className="ml-auto text-muted">Band width = Decision volume</span>
          </div>
          <div className="min-w-[680px]">
            {/* column names over the node columns, which sit at equal steps across the drawing */}
            <div className="relative mx-2 h-5 text-[12px] font-medium text-muted">
              {LAYERS.slice(0, lastLayer + 1).map((l, i) => (
                <span
                  key={l.layer}
                  className="absolute top-0 whitespace-nowrap"
                  style={
                    i === lastLayer && lastLayer > 0
                      ? { right: 0 }
                      : { left: lastLayer > 0 ? `${(100 * i) / lastLayer}%` : 0 }
                  }
                >
                  {l.label}
                </span>
              ))}
            </div>
            <div style={{ height: 420 }}>
              <ResponsiveContainer width="100%" height="100%">
                <Sankey
                  data={map}
                  node={MapNodeShape}
                  link={MapLinkShape}
                  nodeWidth={10}
                  nodePadding={22}
                  margin={{ top: 10, right: 8, bottom: 10, left: 8 }}
                  iterations={64}
                >
                  <Tooltip content={(p) => tip(p as Partial<TooltipContentProps<number, string>>)} />
                </Sankey>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      ) : (
        <div className="max-h-96 overflow-auto px-4 pb-3 pt-2">
          <table className="w-full border-collapse text-[13px]" aria-label="Journey map as a table">
            <thead>
              <tr>
                {["From", "To", "Decisions", "Bought in the end"].map((h, i) => (
                  <th
                    key={h}
                    scope="col"
                    className={`sticky top-0 border-b border-line bg-surface py-1.5 font-medium text-muted ${i > 1 ? "pl-3 text-right" : "pr-3 text-left"}`}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {flows.map((f, i) => (
                <tr key={i}>
                  <td className="border-b border-line py-1.5 pr-3 text-ink-2">{nodeLabel(f.from)}</td>
                  <td className="border-b border-line py-1.5 pr-3 text-ink">{nodeLabel(f.to)}</td>
                  <td className="num border-b border-line py-1.5 pl-3 text-right text-ink">{int(f.value)}</td>
                  <td className="num border-b border-line py-1.5 pl-3 text-right text-ink">{pct(f.conversion, 1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </figure>
  );
}

export default function Journeys() {
  const [days, setDays] = useState("180");
  const [tier, setTier] = useState("");
  const data = useQuery({
    queryKey: ["journeys", days, tier],
    queryFn: () => api.get<JourneyData>("/journeys", { days, tier }),
    placeholderData: keepPreviousData,
    refetchInterval: 120_000,
  });
  return (
    <>
      <PageHeader
        title="Journeys"
        description="How people move from sign-up to buying, and what each step did at each stage. Outcomes are weighted by how likely each logged step was, so busy steps do not look better than they are."
        actions={
          <>
            <Select
              aria-label="Period"
              value={days}
              onChange={(e) => setDays(e.target.value)}
              className="w-40"
              options={[
                { value: "30", label: "Last 30 days" },
                { value: "90", label: "Last 90 days" },
                { value: "180", label: "Last 180 days" },
                { value: "365", label: "Last year" },
              ]}
            />
            <Select
              aria-label="Tier"
              value={tier}
              onChange={(e) => setTier(e.target.value)}
              className="w-56"
              options={[{ value: "", label: "Every tier" }, ...TIERS.map((t) => ({ value: t, label: t }))]}
            />
          </>
        }
      />
      <QueryView query={data} what="the journeys">
        {(d) => (
          <>
            <Section
              title="From sign-up to customer"
              description={`${int(d.funnel.signed_up)} people signed up in the period.`}
            >
              <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
                <Funnel f={d.funnel} />
                <div>
                  <p className="mb-2 text-[13px] font-semibold text-ink">Where people stop</p>
                  {(d.dropoffs ?? []).length === 0 && (
                    <p className="text-[13.5px] text-muted">Nobody signed up in the period yet.</p>
                  )}
                  <ul className="rounded-md border border-line bg-surface empty:hidden">
                    {(d.dropoffs ?? []).map((x) => (
                      <li
                        key={`${x.from}-${x.to}`}
                        className="flex items-baseline gap-3 border-b border-line px-4 py-2.5 text-[13.5px] last:border-b-0"
                      >
                        <span className="text-ink-2">
                          {STAGE_LABEL[x.from] ?? x.from} to {STAGE_LABEL[x.to] ?? x.to}
                        </span>
                        <span className="num ml-auto text-ink">{int(x.lost)} stopped</span>
                        <span className="num w-12 text-right text-muted">{pct(x.lost_share)}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </Section>

            {d.sankey.links.length > 0 && (
              <Section
                title="How journeys run"
                description={`Stage, the step the CRM took, how the person reacted and whether they bought, from ${int(d.with_outcome)} decisions with a known outcome.`}
              >
                <JourneyMap map={d.sankey} topPaths={d.top_paths} />
              </Section>
            )}

            <Section
              title="What each step did, by stage"
              description="Share who bought after a step, against the share who bought after no step at the same stage."
            >
              {(d.action_effects ?? []).length === 0 ? (
                <p className="text-[13.5px] text-muted">
                  Not enough decisions with a known outcome yet. A step shows here once it was taken at least 10 times
                  at a stage and nothing was done 10 times at that stage, and their outcomes are known (the outcome
                  window after each decision has passed).
                </p>
              ) : (
                <Table label="Step effects by stage">
                  <thead>
                    <tr>
                      <Th>Stage</Th>
                      <Th>Step</Th>
                      <Th className="text-right">Decisions</Th>
                      <Th className="text-right">Bought after it</Th>
                      <Th className="text-right">After no step</Th>
                      <Th className="text-right">Difference</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {(d.action_effects ?? []).map((e) => (
                      <tr key={`${e.stage}-${e.action}`}>
                        <Td className="text-ink-2">{STAGE_LABEL[e.stage] ?? e.stage}</Td>
                        <Td className="text-ink">{e.label}</Td>
                        <Td className="num text-right">{int(e.n)}</Td>
                        <Td className="num text-right">{pct(e.rate, 1)}</Td>
                        <Td className="num text-right">{pct(e.nothing_rate, 1)}</Td>
                        <Td className="num text-right font-medium text-ink">{points(e.lift)}</Td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              )}
            </Section>

            <Section
              title="Paths that led to buying"
              description={`Stage, step and reaction, from ${int(d.with_outcome)} decisions with a known outcome.`}
            >
              {(d.top_paths ?? []).length === 0 ? (
                <p className="text-[13.5px] text-muted">
                  Not enough decisions with a known outcome yet: a path shows here once it happened at least 15 times.
                </p>
              ) : (
                <Table label="Converting paths">
                  <thead>
                    <tr>
                      <Th>Stage</Th>
                      <Th>Step</Th>
                      <Th>Reaction</Th>
                      <Th className="text-right">Times</Th>
                      <Th className="text-right">Bought (weighted)</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {(d.top_paths ?? []).map((p, i) => (
                      <tr key={i}>
                        <Td className="text-ink-2">{STAGE_LABEL[p.stage] ?? p.stage}</Td>
                        <Td className="text-ink">{p.action_label}</Td>
                        <Td className="text-ink-2">{p.reaction_label}</Td>
                        <Td className="num text-right">{int(p.n)}</Td>
                        <Td className="num text-right">
                          {pct(p.conversion_weighted, 1)}
                          <span className="block text-[12px] text-muted">raw {pct(p.conversion, 0)}</span>
                        </Td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              )}
            </Section>
          </>
        )}
      </QueryView>
    </>
  );
}
