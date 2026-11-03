import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { cn, dateTime, errorText, pct, plural, relative } from "@xedu/shared/lib";
import { Badge, Button, Dialog, EmptyState, Field, Notice, Segmented, Textarea, useToast } from "@xedu/shared/ui";
import { ListChecks, MessageCircle, Phone } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router";
import { api } from "../api/client";
import { useCapacity } from "../api/queries";
import type { ActionRow, ActionsResponse } from "../api/types";
import { useMe } from "../app/session";
import { CapacityMeter } from "../components/capacity";
import { Person, Score } from "../components/lead-bits";
import { PageHeader } from "../components/page";
import { DecisionReceipt } from "../components/receipt";
import { Loading, LoadError } from "../components/state";
import { outcomeLabel } from "../lib/labels";

type Status = "open" | "closed";
type Owner = "me" | "unassigned" | "all";
type Segment = "all" | "real" | "simulated";

const REAL_OUTCOMES: Record<"call" | "whatsapp", { value: string; label: string }[]> = {
  call: [
    { value: "reached", label: "Spoke to them" },
    { value: "no_answer", label: "No answer" },
    { value: "not_interested", label: "Not interested" },
  ],
  whatsapp: [
    { value: "sent", label: "WhatsApp sent" },
    { value: "not_interested", label: "Not interested" },
  ],
};

function useInvalidate() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: ["actions"] });
    void qc.invalidateQueries({ queryKey: ["stats"] });
    void qc.invalidateQueries({ queryKey: ["capacity"] });
    void qc.invalidateQueries({ queryKey: ["simulation"] });
  };
}

function RecordDialog({ task, onClose }: { task: ActionRow; onClose: () => void }) {
  const choices = REAL_OUTCOMES[task.task_type];
  const [outcome, setOutcome] = useState(choices[0].value);
  const [note, setNote] = useState("");
  const toast = useToast();
  const invalidate = useInvalidate();
  const save = useMutation({
    mutationFn: () =>
      api.post<{ message: string; suggest_lost: boolean }>(`/actions/${task.id}/done`, { outcome, note: note || null }),
    onSuccess: (r) => {
      toast({
        tone: "good",
        text: r.suggest_lost ? "Saved. If they will not buy, close the lead as lost on their page." : "Saved.",
      });
      invalidate();
      onClose();
    },
  });
  return (
    <Dialog
      open
      onClose={onClose}
      title={task.task_type === "call" ? `How did the call with ${task.name} go?` : `WhatsApp to ${task.name}`}
      description="The outcome goes on their timeline and teaches the model what this step does."
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={save.isPending} onClick={() => save.mutate()}>
            Save outcome
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        {save.isError && <Notice tone="bad">{errorText(save.error)}</Notice>}
        <div>
          <p className="mb-1.5 text-[13px] font-medium text-ink">Outcome</p>
          <Segmented label="Outcome" value={outcome} onChange={setOutcome} options={choices} />
        </div>
        <Field label="Note" optional hint="Saved on the lead's page, for whoever talks to them next.">
          <Textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
      </div>
    </Dialog>
  );
}

function TaskRow({ task }: { task: ActionRow }) {
  const [open, setOpen] = useState(false);
  const [recording, setRecording] = useState(false);
  const toast = useToast();
  const invalidate = useInvalidate();
  const isCall = task.task_type === "call";
  const Icon = isCall ? Phone : MessageCircle;

  const simulate = useMutation({
    mutationFn: () => api.post<{ message: string; outcome: string }>(`/actions/${task.id}/call`, {}),
    onSuccess: (r) => {
      toast({ tone: r.outcome === "reached" || r.outcome === "sent" ? "good" : "info", text: r.message });
      invalidate();
    },
    onError: (e) => toast({ tone: "bad", text: errorText(e) }),
  });
  const skip = useMutation({
    mutationFn: () => api.post(`/actions/${task.id}/done`, { outcome: "skipped" }),
    onSuccess: () => {
      toast({ tone: "info", text: "Skipped. Nothing was sent." });
      invalidate();
    },
    onError: (e) => toast({ tone: "bad", text: errorText(e) }),
  });
  const whatsapp = useMutation({
    mutationFn: () => api.post<{ url: string }>("/whatsapp", { lead_id: task.lead_id, message: task.detail ?? "" }),
    onSuccess: (r) => {
      window.open(r.url, "_blank", "noopener");
      setRecording(true);
    },
    onError: (e) => toast({ tone: "bad", text: errorText(e) }),
  });

  const closed = task.status !== "open";
  return (
    <li className="border-b border-line last:border-b-0">
      <div className="flex gap-3 px-4 py-3.5">
        <span
          aria-hidden
          className={cn(
            "mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full",
            closed ? "bg-sunken text-muted" : "bg-brand-soft text-brand-ink",
          )}
        >
          <Icon className="size-4" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-start gap-x-4 gap-y-1">
            <div className="min-w-0 flex-1 basis-72">
              <p className="text-[14px] font-medium text-ink">{task.title}</p>
              <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-[12.5px] text-muted">
                <Person leadId={task.lead_id} name={task.name} simulated={task.simulated} />
                <Score score={task.lead_score} tier={task.recommended_action} />
                <span>{task.owner}</span>
                <span title={dateTime(task.created_at)}>Created {relative(task.created_at)}</span>
                {task.overdue && <Badge tone="warn">Overdue</Badge>}
                {task.policy === "explore" && (
                  <Badge variant="outline" title="A random step that helps the model learn">
                    Learning step
                  </Badge>
                )}
              </div>
            </div>
            <div className="sm:text-right">
              <p className="num text-[15px] font-semibold text-ink">{taskChance(task)}</p>
              <p className="text-[12px] text-muted">chance of buying, without → with this step</p>
            </div>
          </div>

          {closed ? (
            <p className="mt-2 text-[13px] text-ink-2">
              <Badge tone={task.outcome === "reached" || task.outcome === "sent" ? "good" : "neutral"}>
                {outcomeLabel(task.outcome)}
              </Badge>
              <span className="ml-2 text-muted">
                {task.done_by ? `${task.done_by}, ` : ""}
                {dateTime(task.done_at)}
              </span>
            </p>
          ) : (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              {task.simulated ? (
                <Button size="sm" variant="primary" loading={simulate.isPending} onClick={() => simulate.mutate()}>
                  {isCall ? "Call now" : "Send WhatsApp"}
                </Button>
              ) : isCall ? (
                <>
                  {task.phone && (
                    <a
                      href={`tel:${task.phone.replace(/\s+/g, "")}`}
                      className="num text-[13px] font-medium text-brand-ink hover:underline"
                    >
                      {task.phone}
                    </a>
                  )}
                  <Button size="sm" variant="primary" onClick={() => setRecording(true)}>
                    Record the call
                  </Button>
                </>
              ) : (
                <>
                  <Button size="sm" variant="primary" loading={whatsapp.isPending} onClick={() => whatsapp.mutate()}>
                    Open WhatsApp
                  </Button>
                  <Button size="sm" onClick={() => setRecording(true)}>
                    Record outcome
                  </Button>
                </>
              )}
              <Button size="sm" variant="ghost" loading={skip.isPending} onClick={() => skip.mutate()}>
                Skip
              </Button>
              <Button size="sm" variant="ghost" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
                {open ? "Hide details" : "Script and receipt"}
              </Button>
            </div>
          )}

          {open && !closed && (
            <div className="mt-3 grid grid-cols-1 gap-4 lg:grid-cols-[1fr_minmax(0,26rem)]">
              <div className="min-w-0">
                <p className="mb-1.5 text-[12.5px] font-medium text-muted">{isCall ? "Call script" : "Message"}</p>
                <blockquote className="whitespace-pre-line rounded-md border border-line bg-sunken px-3.5 py-3 text-[13.5px] leading-relaxed text-ink">
                  {task.detail}
                </blockquote>
                {task.tips.length > 0 && (
                  <div className="mt-3">
                    <p className="mb-1.5 text-[12.5px] font-medium text-muted">What would raise their score</p>
                    <ul className="flex flex-col gap-1.5 text-[13.5px]">
                      {task.tips.map((t) => (
                        <li key={t.title}>
                          <span className="text-ink">{t.title}</span>
                          <span className="text-muted"> ({t.detail})</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
              {task.options.length > 0 && (
                <DecisionReceipt
                  compact
                  options={task.options}
                  chosen={task.task_type}
                  modelBest={task.model_best}
                  policy={task.policy}
                  slotPrice={task.slot_price}
                  price={task.course_price}
                  meta={`Decided ${relative(task.created_at)}`}
                />
              )}
            </div>
          )}
        </div>
      </div>
      {recording && <RecordDialog task={task} onClose={() => setRecording(false)} />}
    </li>
  );
}

export default function Actions() {
  const me = useMe();
  const [params, setParams] = useSearchParams();
  const status = (params.get("status") as Status) || "open";
  const owner = (params.get("owner") as Owner) || (me.role === "counsellor" ? "me" : "all");
  const segment = (params.get("segment") as Segment) || "all";
  const set = (k: string, v: string) =>
    setParams(
      (p) => {
        p.set(k, v);
        return p;
      },
      { replace: true },
    );

  const capacity = useCapacity(20_000);
  const list = useQuery({
    queryKey: ["actions", status, owner, segment],
    queryFn: () => api.get<ActionsResponse>("/actions", { status, owner, segment, limit: 300 }),
    refetchInterval: 20_000,
  });

  const rows = list.data?.actions ?? [];
  const open = rows.filter((r) => r.status === "open");
  const overdue = open.filter((r) => r.overdue).length;

  return (
    <>
      <PageHeader
        title="Today's actions"
        description="Calls and WhatsApp messages that next-best-action chose because they raise the chance of buying the most. The ones that help most come first."
      />
      {capacity.data && <CapacityMeter capacity={capacity.data} className="mb-6" />}
      {capacity.isError && (
        <LoadError error={capacity.error} what="the call slots" retry={() => void capacity.refetch()} />
      )}

      <div className="mb-3 flex flex-wrap items-center gap-3">
        <Segmented
          label="Status"
          value={status}
          onChange={(v) => set("status", v)}
          options={[
            { value: "open", label: "To do" },
            { value: "closed", label: "Done" },
          ]}
        />
        <Segmented
          label="Whose leads"
          value={owner}
          onChange={(v) => set("owner", v)}
          options={[
            { value: "me", label: "Mine" },
            { value: "unassigned", label: "Unassigned" },
            { value: "all", label: "Everyone's" },
          ]}
        />
        <Segmented
          label="Learners"
          value={segment}
          onChange={(v) => set("segment", v)}
          options={[
            { value: "all", label: "All" },
            { value: "real", label: "Real people" },
            { value: "simulated", label: "Simulated" },
          ]}
        />
        {status === "open" && list.data && (
          <p className="ml-auto text-[13px] text-muted">
            {plural(open.length, "task")}
            {overdue > 0 && `, ${overdue} overdue`}
          </p>
        )}
      </div>

      {list.isPending ? (
        <Loading label="Loading the tasks" />
      ) : list.isError ? (
        <LoadError error={list.error} what="the tasks" retry={() => void list.refetch()} />
      ) : rows.length === 0 ? (
        <div className="rounded-md border border-line bg-surface px-4">
          <EmptyState
            icon={ListChecks}
            title={status === "open" ? "Nothing to do right now" : "No finished tasks yet"}
            action={
              <Link to="/leads" className="text-[14px] font-medium text-brand-ink hover:underline">
                Look through the leads
              </Link>
            }
          >
            {status === "open"
              ? "Next-best-action adds a call or WhatsApp task when it is the most profitable step for a lead. New tasks appear here by themselves."
              : "Calls and messages the team has done appear here."}
            {list.data.other_segment_count > 0 &&
              ` ${plural(list.data.other_segment_count, "task")} in the other group of learners.`}
          </EmptyState>
        </div>
      ) : (
        <ul className="rounded-md border border-line bg-surface">
          {rows.map((t) => (
            <TaskRow key={t.id} task={t} />
          ))}
        </ul>
      )}
      {list.data && list.data.expiry_days > 0 && status === "open" && rows.length > 0 && (
        <p className="mt-3 text-[12.5px] text-muted">
          A task is overdue after {plural(list.data.sla_hours, "hour")} and closes by itself after{" "}
          {plural(list.data.expiry_days, "day")}.
        </p>
      )}
    </>
  );
}

/** "8% → 14%": the chance of buying without a step and with this task's step, from its decision receipt. */
function taskChance(task: { task_type: string; options: { action: string; p_convert: number }[] }): string {
  const none = task.options.find((o) => o.action === "none");
  const step = task.options.find((o) => o.action === task.task_type);
  return none && step ? `${pct(none.p_convert)} → ${pct(step.p_convert)}` : "";
}
