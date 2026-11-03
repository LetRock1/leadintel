import { useMutation, useQueryClient } from "@tanstack/react-query";
import { errorText, int, relative } from "@xedu/shared/lib";
import { Button, Notice, Switch, useToast } from "@xedu/shared/ui";
import { api } from "../api/client";
import { useSimulation } from "../api/queries";
import { useSession } from "../app/session";
import { KpiStrip, PageHeader, Panel, Section } from "../components/page";
import { QueryView } from "../components/state";

const KIND_LABEL: Record<string, string> = {
  visit: "Visit",
  signup: "Sign-up",
  purchase: "Purchase",
  click: "Email click",
  team: "Team",
  info: "Note",
  error: "Problem",
};

export default function Simulation() {
  const { can } = useSession();
  const qc = useQueryClient();
  const toast = useToast();
  const sim = useSimulation(10_000);
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["simulation"] });
    void qc.invalidateQueries({ queryKey: ["stats"] });
  };
  const switchIt = useMutation({
    mutationFn: (enabled: boolean) => api.post<{ message?: string }>("/simulation/enabled", { enabled }),
    onSuccess: (r, enabled) => {
      toast({
        tone: "good",
        text: r.message ?? (enabled ? "Simulated learners resumed." : "Simulated learners paused."),
      });
      refresh();
    },
    onError: (e) => toast({ tone: "bad", text: errorText(e) }),
  });
  const visit = useMutation({
    mutationFn: (kind: "returning" | "signup") => api.post<{ message: string }>("/simulation/visit", { kind }),
    onSuccess: (r) => {
      toast({ tone: "good", text: r.message });
      refresh();
    },
    onError: (e) => toast({ tone: "bad", text: errorText(e) }),
  });
  const admin = can("marketing");

  return (
    <>
      <PageHeader
        title="Simulated learners"
        description="Only the learners are simulated. They use the website through the same public API as real people, and the CRM treats them exactly the same; everything the team does is real."
      />
      <QueryView query={sim} what="the simulation">
        {(s) => (
          <>
            {s.last_error && (
              <Notice tone="bad" title="The last step failed" className="mb-6">
                {s.last_error}
              </Notice>
            )}
            <div className="mb-6 grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
              <KpiStrip
                items={[
                  { label: "Learners", value: int(s.learners.total), detail: `${int(s.learners.customers)} customers` },
                  {
                    label: "On the website now",
                    value: int(s.learners.on_site_now),
                    detail: `${int(s.learners.still_deciding)} still deciding`,
                  },
                  {
                    label: "Visits, last 24 hours",
                    value: int(s.last_24h.visits),
                    detail: `about ${s.expected_per_day.visits} a day expected`,
                  },
                  {
                    label: "Purchases, last 24 hours",
                    value: int(s.last_24h.purchases),
                    detail: `about ${s.expected_per_day.purchases} a day expected`,
                  },
                ]}
              />
              <Panel>
                <Switch
                  checked={s.enabled}
                  disabled={!admin || switchIt.isPending || Boolean(s.switched_off_by_settings)}
                  onChange={(v) => switchIt.mutate(v)}
                  label={s.switched_off_by_settings ? "Switched off" : s.enabled ? "Running" : "Paused"}
                  description={
                    s.switched_off_by_settings
                      ? "Switched off in backend/.env (SIMULATION_ENABLED=false), for a CRM with real learners only."
                      : s.enabled
                        ? `Last step ${relative(s.last_tick, undefined, "not yet")}.`
                        : "No simulated visits until resumed. Real learners are not affected."
                  }
                />
                {admin && (
                  <div className="mt-4 flex flex-wrap gap-2 border-t border-line pt-4">
                    <Button
                      size="sm"
                      loading={visit.isPending && visit.variables === "returning"}
                      disabled={!s.enabled}
                      onClick={() => visit.mutate("returning")}
                    >
                      Send a learner to the website
                    </Button>
                    <Button
                      size="sm"
                      loading={visit.isPending && visit.variables === "signup"}
                      disabled={!s.enabled}
                      onClick={() => visit.mutate("signup")}
                    >
                      Let a new learner sign up
                    </Button>
                  </div>
                )}
              </Panel>
            </div>

            <div className="grid grid-cols-1 gap-x-6 gap-y-9 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)] [&>section]:mt-0">
              <Section title="What they did recently">
                {s.recent.length === 0 ? (
                  <p className="text-[13.5px] text-muted">
                    Nothing yet. Visits happen at the pace a real audience would visit.
                  </p>
                ) : (
                  <ul className="rounded-md border border-line bg-surface">
                    {s.recent.map((r, i) => (
                      <li
                        key={i}
                        className="grid grid-cols-[6rem_minmax(0,1fr)_auto] items-baseline gap-3 border-b border-line px-4 py-2.5 text-[13.5px] last:border-b-0"
                      >
                        <span className="text-[12.5px] text-muted">{KIND_LABEL[r.kind] ?? r.kind}</span>
                        <span className="text-ink">{r.text}</span>
                        <span className="whitespace-nowrap text-[12.5px] text-muted">{relative(r.at)}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </Section>
              <Section title="Last 24 hours">
                <Panel>
                  <dl className="grid grid-cols-2 gap-y-3 text-[13.5px]">
                    <dt className="text-muted">Sign-ups</dt>
                    <dd className="num text-right text-ink">{int(s.last_24h.signups)}</dd>
                    <dt className="text-muted">Email clicks</dt>
                    <dd className="num text-right text-ink">{int(s.last_24h.email_clicks)}</dd>
                    <dt className="text-muted">Calls and messages by the team</dt>
                    <dd className="num text-right text-ink">{int(s.last_24h.team_tasks)}</dd>
                    <dt className="text-muted">Tasks waiting for the team</dt>
                    <dd className="num text-right text-ink">{int(s.tasks_waiting_for_team)}</dd>
                    <dt className="text-muted">Problems</dt>
                    <dd className="num text-right text-ink">{int(s.last_24h.errors)}</dd>
                  </dl>
                </Panel>
                {s.recent_errors.length > 0 && (
                  <ul className="mt-3 flex flex-col gap-2">
                    {s.recent_errors.map((e, i) => (
                      <li
                        key={i}
                        className="rounded-md border border-bad/30 bg-bad-soft px-3 py-2 text-[13px] text-ink"
                      >
                        {e.text} <span className="text-muted">{relative(e.at)}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </Section>
            </div>
          </>
        )}
      </QueryView>
    </>
  );
}
