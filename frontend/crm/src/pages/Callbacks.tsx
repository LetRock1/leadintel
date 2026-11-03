import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { dateTime, errorText, plural, relative } from "@xedu/shared/lib";
import { Badge, Button, Dialog, EmptyState, Field, Segmented, Textarea, useToast } from "@xedu/shared/ui";
import { PhoneIncoming } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router";
import { api } from "../api/client";
import { useCourses } from "../api/queries";
import type { CallbackRow } from "../api/types";
import { useMe } from "../app/session";
import { Person } from "../components/lead-bits";
import { PageHeader } from "../components/page";
import { Loading, LoadError } from "../components/state";

function DoneDialog({ cb, onClose }: { cb: CallbackRow; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [note, setNote] = useState("");
  const done = useMutation({
    mutationFn: () => api.post(`/callbacks/${cb.id}/done`, { note: note || null }),
    onSuccess: () => {
      toast({ tone: "good", text: "Marked as done." });
      void qc.invalidateQueries({ queryKey: ["callbacks"] });
      void qc.invalidateQueries({ queryKey: ["stats"] });
      onClose();
    },
    onError: (e) => toast({ tone: "bad", text: errorText(e) }),
  });
  return (
    <Dialog
      open
      onClose={onClose}
      title={`Call-back to ${cb.name ?? "this learner"} done`}
      description="The note goes on their page for whoever talks to them next."
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={done.isPending} onClick={() => done.mutate()}>
            Mark as done
          </Button>
        </>
      }
    >
      <Field label="What was said" optional>
        <Textarea rows={4} value={note} onChange={(e) => setNote(e.target.value)} />
      </Field>
    </Dialog>
  );
}

export default function Callbacks() {
  const me = useMe();
  const courses = useCourses();
  const [params, setParams] = useSearchParams();
  const status = params.get("status") ?? "open";
  const owner = params.get("owner") ?? (me.role === "counsellor" ? "me" : "all");
  const [closing, setClosing] = useState<CallbackRow | null>(null);
  const set = (k: string, v: string) =>
    setParams(
      (p) => {
        p.set(k, v);
        return p;
      },
      { replace: true },
    );
  const list = useQuery({
    queryKey: ["callbacks", status, owner],
    queryFn: () => api.get<{ callbacks: CallbackRow[]; sla_hours: number }>("/callbacks", { status, owner }),
    refetchInterval: 20_000,
  });

  return (
    <>
      <PageHeader
        title="Call-backs"
        description="People who asked on the website for a counsellor to call them. Call them before the service level runs out."
      />
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <Segmented
          label="Status"
          value={status}
          onChange={(v) => set("status", v)}
          options={[
            { value: "open", label: "Waiting" },
            { value: "done", label: "Done" },
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
        {list.data && (
          <p className="ml-auto text-[13px] text-muted">
            {plural(list.data.callbacks.length, "request")}. Call back within {plural(list.data.sla_hours, "hour")}.
          </p>
        )}
      </div>
      {list.isPending ? (
        <Loading label="Loading the call-backs" />
      ) : list.isError ? (
        <LoadError error={list.error} what="the call-backs" retry={() => void list.refetch()} />
      ) : list.data.callbacks.length === 0 ? (
        <div className="rounded-md border border-line bg-surface px-4">
          <EmptyState
            icon={PhoneIncoming}
            title={status === "open" ? "No one is waiting for a call" : "No call-backs done yet"}
          >
            A request appears here as soon as someone asks for a call on a course page.
          </EmptyState>
        </div>
      ) : (
        <ul className="rounded-md border border-line bg-surface">
          {list.data.callbacks.map((cb) => (
            <li
              key={cb.id}
              className="flex flex-wrap items-start gap-x-6 gap-y-2 border-b border-line px-4 py-3.5 last:border-b-0"
            >
              <div className="min-w-0 flex-1 basis-64">
                <Person leadId={cb.lead_id} name={cb.name ?? "Learner"} email={cb.email} simulated={cb.simulated} />
                <p className="mt-1 text-[13px] text-ink-2">
                  {courses.title(cb.course_slug) || "No course given"}
                  {cb.preferred_time ? `. Best time: ${cb.preferred_time}` : ""}
                </p>
                {cb.note && <p className="mt-1 text-[13px] text-muted">&ldquo;{cb.note}&rdquo;</p>}
              </div>
              <div className="text-[13px]">
                <a
                  href={`tel:${cb.phone.replace(/\s+/g, "")}`}
                  className="num font-medium text-brand-ink hover:underline"
                >
                  {cb.phone}
                </a>
                <p className="text-[12.5px] text-muted">{cb.owner}</p>
              </div>
              <div className="flex min-w-40 flex-col items-end gap-1.5 text-right">
                <span className="text-[12.5px] text-muted" title={dateTime(cb.created_at)}>
                  Asked {relative(cb.created_at)}
                </span>
                {cb.status === "open" ? (
                  <div className="flex items-center gap-2">
                    {cb.overdue && <Badge tone="warn">Overdue</Badge>}
                    <Button size="sm" variant="primary" onClick={() => setClosing(cb)}>
                      Mark as done
                    </Button>
                  </div>
                ) : (
                  <Badge tone="good">Done{cb.done_by ? ` by ${cb.done_by}` : ""}</Badge>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      {closing && <DoneDialog cb={closing} onClose={() => setClosing(null)} />}
    </>
  );
}
