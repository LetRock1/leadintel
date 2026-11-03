import { useQuery } from "@tanstack/react-query";
import { int, pct } from "@xedu/shared/lib";
import { Table, Td, Th } from "@xedu/shared/ui";
import { api } from "../api/client";
import type { ModelHealth as Health } from "../api/types";
import { TrendChart } from "../components/charts";
import { KpiStrip, PageHeader, Section } from "../components/page";
import { QueryView } from "../components/state";
import { TIERS } from "../lib/labels";

interface Card {
  version?: string;
  model_type?: string;
  trained_at?: string;
  metrics?: Record<string, number>;
  base_rate?: number;
  trained_on?: Record<string, number>;
}

export default function ModelHealth() {
  const health = useQuery({
    queryKey: ["model", "health"],
    queryFn: () => api.get<Health & { retrain_hint?: string }>("/model/health"),
    refetchInterval: 60_000,
  });
  return (
    <>
      <PageHeader
        title="Model health"
        description="Is the lead score still right? Scores from the last weeks are compared with what the people then did."
      />
      <QueryView query={health} what="the model check">
        {(h) => {
          const card = (h.model ?? {}) as Card;
          const m = card.metrics ?? {};
          const calibration = h.calibration.map((b) => ({
            bin: `${(b.bin - 1) * 10} to ${b.bin * 10}`,
            predicted: b.predicted,
            actual: b.actual,
            n: b.n,
          }));
          return (
            <>
              <KpiStrip
                items={[
                  {
                    label: "Ranking (AUC)",
                    value: m.roc_auc?.toFixed(3) ?? "None",
                    detail: "1.0 ranks every buyer first",
                  },
                  {
                    label: "Chance error (log-loss)",
                    value: m.log_loss?.toFixed(3) ?? "None",
                    detail: "Lower is better",
                  },
                  {
                    label: "Calibration error",
                    value: m.ece?.toFixed(3) ?? "None",
                    detail: "Gap between score and reality",
                  },
                  {
                    label: "Buyers in the top 10%",
                    value: pct(m.precision_top10, 0, "None"),
                    detail: "Buyers among the highest scores",
                  },
                  {
                    label: "Scores checked",
                    value: int(h.snapshots_labelled),
                    detail: `of ${int(h.snapshots_total)} in ${h.window_days} days`,
                  },
                ]}
              />
              <p className="mt-2 text-[12.5px] text-muted">
                Model {card.version ?? "not loaded"} ({(card.model_type ?? "").replace(/_/g, " ")}). The first four
                numbers are from held-out training data.
              </p>

              <Section
                title="Calibration"
                description="For each tenth of the scores: the chance of buying the score said, against the share who really bought."
              >
                {calibration.length ? (
                  <TrendChart
                    title="Predicted and actual share who bought"
                    description="By score band"
                    data={calibration}
                    x="bin"
                    series={[
                      { key: "predicted", label: "Predicted" },
                      { key: "actual", label: "Actual" },
                    ]}
                    format={(v) => pct(v, 0)}
                    height={260}
                    footer="When the two lines are close, the score can be read as a chance of buying."
                  />
                ) : (
                  <p className="text-[13.5px] text-muted">Not enough known outcomes yet.</p>
                )}
              </Section>

              <Section title="By tier">
                {h.by_tier.length === 0 ? (
                  <p className="text-[13.5px] text-muted">
                    Not enough known outcomes yet: a score is checked {h.window_days} days after it was given.
                  </p>
                ) : (
                  <Table label="By tier">
                    <thead>
                      <tr>
                        <Th>Tier</Th>
                        <Th className="text-right">Scores</Th>
                        <Th className="text-right">Predicted</Th>
                        <Th className="text-right">Actual</Th>
                      </tr>
                    </thead>
                    <tbody>
                      {[...h.by_tier]
                        .sort(
                          (a, b) =>
                            TIERS.indexOf(a.tier as (typeof TIERS)[number]) -
                            TIERS.indexOf(b.tier as (typeof TIERS)[number]),
                        )
                        .map((t) => (
                          <tr key={t.tier}>
                            <Td className="text-ink">{t.tier}</Td>
                            <Td className="num text-right">{int(t.snapshots)}</Td>
                            <Td className="num text-right">{pct(t.predicted_rate, 1)}</Td>
                            <Td className="num text-right">{pct(t.actual_rate, 1)}</Td>
                          </tr>
                        ))}
                    </tbody>
                  </Table>
                )}
                {h.retrain_hint && <p className="mt-3 max-w-[80ch] text-[13px] text-muted">{h.retrain_hint}</p>}
                <p className="mt-2 max-w-[80ch] text-[12.5px] text-muted">
                  People the team worked on buy more than their score said, because the follow-ups work. The learning
                  loop checks new models on the untouched control group for that reason.
                </p>
              </Section>
            </>
          );
        }}
      </QueryView>
    </>
  );
}
