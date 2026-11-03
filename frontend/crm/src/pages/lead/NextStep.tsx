import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { cn, errorText, pct, relative, useChartColors } from "@xedu/shared/lib";
import { Button, Menu, Notice, Select, useToast } from "@xedu/shared/ui";
import { ChevronDown } from "lucide-react";
import { useState } from "react";
import { api } from "../../api/client";
import type { ActResponse, LeadPage, NowRecommendation, PathsResponse } from "../../api/types";
import { Section } from "../../components/page";
import { DecisionReceipt } from "../../components/receipt";
import { Loading, LoadError } from "../../components/state";

function Factors({ factors }: { factors: NonNullable<NowRecommendation["factors"]> }) {
  const c = useChartColors();
  if (!factors.length)
    return <p className="text-[13.5px] text-muted">No signals yet: the person has not done anything on the website.</p>;
  const max = Math.max(...factors.map((f) => Math.abs(f.points)), 1);
  return (
    <ul className="rounded-md border border-line bg-surface">
      {factors.map((f) => (
        <li
          key={f.factor}
          className="grid grid-cols-[minmax(0,1fr)_7rem_4.5rem] items-center gap-x-4 border-b border-line px-4 py-2.5 last:border-b-0"
        >
          <div className="min-w-0">
            <p className="truncate text-[13.5px] text-ink">{f.factor}</p>
            <p className="truncate text-[12.5px] text-muted">{f.detail}</p>
          </div>
          <div aria-hidden className="relative h-2">
            <span className="absolute inset-y-0 left-1/2 w-px" style={{ background: c.axis }} />
            <span
              className="absolute inset-y-0 rounded-full"
              style={{
                background: f.points >= 0 ? c.series[0] : c.series[1],
                left: f.points >= 0 ? "50%" : `${50 - (50 * Math.abs(f.points)) / max}%`,
                width: `${(50 * Math.abs(f.points)) / max}%`,
              }}
            />
          </div>
          <p className="num text-right text-[13.5px] font-medium text-ink">
            {f.points > 0 ? "+" : f.points < 0 ? "−" : ""}
            {Math.abs(Math.round(f.points))} points
          </p>
        </li>
      ))}
    </ul>
  );
}

function Paths({ leadId }: { leadId: number }) {
  const c = useChartColors();
  const paths = useQuery({
    queryKey: ["lead", leadId, "paths"],
    queryFn: () => api.get<PathsResponse>(`/leads/${leadId}/paths`),
    refetchInterval: 60_000,
  });
  const [chosen, setChosen] = useState<string | null>(null);
  if (paths.isPending) return <Loading label="Working out the likely paths" />;
  if (paths.isError)
    return <LoadError error={paths.error} what="the what-if paths" retry={() => void paths.refetch()} />;
  const d = paths.data;
  if (!d.steps.length)
    return <p className="text-[13.5px] text-muted">{d.summary || "No what-if paths for this person."}</p>;
  const step = d.steps.find((s) => s.action === (chosen ?? d.best)) ?? d.steps[0];
  return (
    <div className="rounded-md border border-line bg-surface">
      <div className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-3">
        <label className="text-[13px] text-muted" htmlFor="path-step">
          If the CRM takes
        </label>
        <Select
          id="path-step"
          value={step.action}
          onChange={(e) => setChosen(e.target.value)}
          className="w-64"
          options={d.steps.map((s) => ({
            value: s.action,
            label: s.action === d.best ? `${s.label} (recommended)` : s.label,
          }))}
        />
        <p className="ml-auto text-[13px] text-muted">
          Chance of buying with this step <span className="num text-ink">{pct(step.p_buy_step)}</span>
        </p>
      </div>
      <ul>
        {step.reactions.map((r) => (
          <li
            key={r.reaction}
            className="grid grid-cols-[minmax(0,12rem)_minmax(0,1fr)] items-center gap-x-4 border-b border-line px-4 py-2.5 last:border-b-0 sm:grid-cols-[minmax(0,12rem)_10rem_minmax(0,1fr)]"
          >
            <p className="text-[13.5px] text-ink">{r.label}</p>
            <div className="flex items-center gap-2">
              <span aria-hidden className="h-1.5 flex-1 overflow-hidden rounded-full" style={{ background: c.grid }}>
                <span
                  className="block h-full rounded-full"
                  style={{ width: `${Math.round(r.prob * 100)}%`, background: c.series[0] }}
                />
              </span>
              <span className="num w-10 text-right text-[13px] text-ink">{pct(r.prob)}</span>
            </div>
            <p className="col-span-2 text-[13px] text-muted sm:col-span-1">
              {r.reaction === "bought"
                ? "Done: they bought."
                : r.best_next
                  ? `Then: ${r.best_next.label.toLowerCase()} (chance of buying ${pct(r.best_next.p_buy)})${r.next ? `, score about ${Math.round(r.next.score)}` : ""}`
                  : "Then: nothing more to do."}
            </p>
          </li>
        ))}
      </ul>
      <p className="border-t border-line px-4 py-2.5 text-[12.5px] text-muted">
        Based on {step.evidence.decisions.toLocaleString("en-IN")} earlier decisions:{" "}
        {step.evidence.basis.charAt(0).toLowerCase() + step.evidence.basis.slice(1)}. {d.note}
      </p>
    </div>
  );
}

export function NextStep({ lead }: { lead: LeadPage }) {
  const qc = useQueryClient();
  const toast = useToast();
  const now = useQuery({
    queryKey: ["lead", lead.id, "now"],
    queryFn: () => api.get<NowRecommendation>(`/leads/${lead.id}/now`),
    refetchInterval: 20_000,
  });
  const act = useMutation({
    mutationFn: (action: string) => api.post<ActResponse>(`/leads/${lead.id}/act`, { action }),
    onSuccess: (r) => {
      toast({ tone: "good", text: r.message });
      void qc.invalidateQueries({ queryKey: ["lead", lead.id] });
      void qc.invalidateQueries({ queryKey: ["actions"] });
      void qc.invalidateQueries({ queryKey: ["capacity"] });
    },
    onError: (e) => toast({ tone: "bad", text: errorText(e) }),
  });

  if (now.isPending) return <Loading label="Working out the next step" />;
  if (now.isError) return <LoadError error={now.error} what="the next step" retry={() => void now.refetch()} />;
  const n = now.data;

  if (!n.recommendation) {
    return (
      <Notice tone="good" title="Customer">
        {n.message}
      </Notice>
    );
  }
  const rec = n.recommendation;
  const recent = n.recent ?? {};
  const others = (n.options ?? []).filter(
    (o) => !o.blocked && o.action !== "none" && o.action !== rec.action && !recent[o.action],
  );
  const recentNotes = Object.values(recent).filter(Boolean);
  const recValue = (n.options ?? []).find((o) => o.action === rec.action);
  const noneValue = (n.options ?? []).find((o) => o.action === "none");
  const blockedWhy = !lead.can_change
    ? lead.can_change_why
    : n.control_group
      ? "This person is in the control group."
      : null;

  return (
    <div>
      {n.control_group && (
        <Notice tone="info" title="Control group" className="mb-5">
          The CRM never contacts this person, so their outcome shows what happens without it. The receipt shows what it
          would have done.
        </Notice>
      )}
      <div className="rounded-md border border-brand/30 bg-brand-soft/50 px-4 py-4">
        <p className="text-[12.5px] font-medium text-brand-ink">Recommended now</p>
        <div className="mt-1 flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <p className="text-[18px] font-semibold text-ink">{rec.label}</p>
          <p className="num ml-auto text-[18px] font-semibold text-ink">
            {rec.action === "none" || !recValue || !noneValue
              ? pct(n.probability)
              : `${pct(noneValue.p_convert)} → ${pct(recValue.p_convert)}`}
          </p>
        </div>
        <p className="mt-1 max-w-[70ch] text-[13.5px] text-ink-2">{rec.why}</p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {rec.action !== "none" && (
            <Button
              variant="primary"
              loading={act.isPending && act.variables === rec.action}
              disabled={Boolean(blockedWhy) || act.isPending || Boolean(recent[rec.action])}
              onClick={() => act.mutate(rec.action)}
            >
              {rec.action === "call" || rec.action === "whatsapp" ? "Add to today's actions" : "Send it now"}
            </Button>
          )}
          {others.length > 0 && (
            <Menu
              label="Take another step"
              align="start"
              items={others.map((o) => ({
                label: o.label,
                hint: noneValue ? `${pct(noneValue.p_convert)} → ${pct(o.p_convert)}` : pct(o.p_convert),
                onSelect: () => act.mutate(o.action),
              }))}
              trigger={(p) => (
                <Button {...p} disabled={Boolean(blockedWhy) || act.isPending}>
                  Take another step
                  <ChevronDown aria-hidden className="size-4" />
                </Button>
              )}
            />
          )}
          {blockedWhy && <p className="text-[13px] text-muted">{blockedWhy}</p>}
        </div>
        {!blockedWhy &&
          recentNotes.map((note) => (
            <p key={note} className="mt-2 text-[13px] text-muted">
              {note}
            </p>
          ))}
      </div>

      {n.options && n.options.length > 0 && (
        <Section
          title="Decision receipt"
          description="What each step is expected to add for this person right now."
          className="mt-8"
        >
          <DecisionReceipt
            title="Every step compared"
            options={n.options}
            chosen={rec.action}
            policy="model"
            slotPrice={n.slot_price}
            price={n.course?.price}
            meta={`${n.course?.title ?? ""}${n.nba_model ? `, model ${n.nba_model}` : ""}`}
          />
        </Section>
      )}

      <Section
        title="What could happen next"
        description="The likely reactions to a step, and the best follow-up after each."
        className="mt-8"
      >
        <Paths leadId={lead.id} />
      </Section>

      <Section
        title="Why this score"
        description={`What each signal adds to or takes from the score of ${Math.round(n.score ?? lead.lead_score)}.`}
        className="mt-8"
      >
        <Factors factors={n.factors ?? []} />
      </Section>

      {n.tips && n.tips.length > 0 && (
        <Section
          title="What would raise their score"
          description="Small steps the person could take next, and the score they would give."
          className="mt-8"
        >
          <ul className="rounded-md border border-line bg-surface">
            {n.tips.map((t) => (
              <li
                key={t.title}
                className="flex flex-wrap items-baseline gap-x-4 border-b border-line px-4 py-2.5 last:border-b-0"
              >
                <p className="min-w-0 flex-1 text-[13.5px] text-ink">{t.title}</p>
                <p className={cn("num text-[13px] text-muted")}>{t.detail}</p>
              </li>
            ))}
          </ul>
        </Section>
      )}
      <p className="mt-6 text-[12.5px] text-muted">
        Lead model {n.lead_model ?? "not loaded"}, scored {relative(lead.created_at)}. Away for{" "}
        {n.away_days === null ? "an unknown time" : `${n.away_days.toFixed(1)} days`}.
      </p>
    </div>
  );
}
