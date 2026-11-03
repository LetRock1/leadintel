import { useMutation, useQueryClient } from "@tanstack/react-query";
import { dateTime, errorText, relative } from "@xedu/shared/lib";
import { Button, EmptyState, Field, Notice, Select, Textarea, useToast } from "@xedu/shared/ui";
import { NotebookPen } from "lucide-react";
import { useState } from "react";
import { api } from "../../api/client";
import type { LeadPage, Note } from "../../api/types";
import { useMe } from "../../app/session";

const KINDS = [
  { value: "note", label: "Note" },
  { value: "call", label: "Call" },
  { value: "whatsapp", label: "WhatsApp" },
  { value: "meeting", label: "Meeting" },
];

const KIND_LABEL: Record<string, string> = Object.fromEntries(KINDS.map((k) => [k.value, k.label]));

export function Notes({ lead }: { lead: LeadPage }) {
  const me = useMe();
  const qc = useQueryClient();
  const toast = useToast();
  const [text, setText] = useState("");
  const [kind, setKind] = useState("note");
  const refresh = () => void qc.invalidateQueries({ queryKey: ["lead", lead.id] });

  const add = useMutation({
    mutationFn: () => api.post<{ note: Note }>(`/leads/${lead.id}/notes`, { text, kind }),
    onSuccess: () => {
      setText("");
      toast({ tone: "good", text: "Note added." });
      refresh();
    },
  });
  const remove = useMutation({
    mutationFn: (id: number) => api.del(`/notes/${id}`),
    onSuccess: () => {
      toast({ tone: "info", text: "Note deleted." });
      refresh();
    },
    onError: (e) => toast({ tone: "bad", text: errorText(e) }),
  });

  return (
    <div className="grid gap-6">
      {lead.can_change ? (
        <form
          className="rounded-md border border-line bg-surface p-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (text.trim()) add.mutate();
          }}
        >
          {add.isError && (
            <Notice tone="bad" className="mb-3">
              {errorText(add.error)}
            </Notice>
          )}
          <Field label="Add a note" hint="Everyone on the team sees notes. Do not write card numbers or passwords.">
            <Textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} maxLength={4000} />
          </Field>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Select
              aria-label="Kind of note"
              value={kind}
              onChange={(e) => setKind(e.target.value)}
              options={KINDS}
              className="w-40"
            />
            <Button type="submit" variant="primary" loading={add.isPending} disabled={!text.trim()}>
              Add note
            </Button>
          </div>
        </form>
      ) : (
        lead.can_change_why && <Notice tone="info">{lead.can_change_why}</Notice>
      )}
      {lead.notes.length === 0 ? (
        <EmptyState icon={NotebookPen} title="No notes yet">
          Notes from calls and meetings help whoever talks to this person next.
        </EmptyState>
      ) : (
        <ul className="rounded-md border border-line bg-surface">
          {lead.notes.map((n) => (
            <li key={n.id} className="border-b border-line px-4 py-3 last:border-b-0">
              <div className="flex flex-wrap items-baseline gap-x-3 text-[12.5px] text-muted">
                <span className="font-medium text-ink">{n.author ?? "The CRM"}</span>
                <span>{KIND_LABEL[n.kind] ?? n.kind}</span>
                <span title={dateTime(n.created_at)}>{relative(n.created_at)}</span>
                {(n.member_id === me.id || me.role === "admin") && (
                  <button
                    type="button"
                    className="ml-auto text-[12.5px] text-muted hover:text-bad"
                    onClick={() => remove.mutate(n.id)}
                    disabled={remove.isPending}
                  >
                    Delete
                  </button>
                )}
              </div>
              <p className="mt-1 whitespace-pre-line text-[13.5px] text-ink">{n.text}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
