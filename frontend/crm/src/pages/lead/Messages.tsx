import { useMutation, useQueryClient } from "@tanstack/react-query";
import { errorText } from "@xedu/shared/lib";
import { Button, Field, Input, Notice, Textarea, useToast } from "@xedu/shared/ui";
import { useState } from "react";
import { api } from "../../api/client";
import type { ImproveResponse, LeadPage } from "../../api/types";
import { Panel, Section } from "../../components/page";

function EmailComposer({ lead }: { lead: LeadPage }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [subject, setSubject] = useState(lead.email_subject ?? "");
  const [body, setBody] = useState(lead.email_body ?? "");
  const [review, setReview] = useState<ImproveResponse | null>(null);
  const noEmail = lead.do_not_email === "Yes";

  const check = useMutation({
    mutationFn: () =>
      api.post<ImproveResponse>("/emails/improve", {
        draft: body,
        subject,
        tier: lead.recommended_action,
        course: lead.course_type ?? "",
        course_slug: lead.course_slug,
        occupation: lead.current_occupation ?? "",
        name: lead.name,
      }),
    onSuccess: setReview,
  });
  const send = useMutation({
    mutationFn: () =>
      api.post<{ success: boolean; message: string }>("/emails", { lead_id: lead.latest_lead_id, subject, body }),
    onSuccess: (r) => {
      toast({ tone: r.success ? "good" : "bad", text: r.message });
      void qc.invalidateQueries({ queryKey: ["lead", lead.id] });
    },
  });

  return (
    <Panel>
      {noEmail && (
        <Notice tone="warn" className="mb-4">
          This person does not want emails. Only they can change that, in their settings on the website.
        </Notice>
      )}
      <div className="flex flex-col gap-4">
        <Field label="Subject">
          <Input value={subject} onChange={(e) => setSubject(e.target.value)} maxLength={300} />
        </Field>
        <Field label="Message" hint="{first_name} and {course} are filled in when it is sent.">
          <Textarea rows={9} value={body} onChange={(e) => setBody(e.target.value)} />
        </Field>
        {(send.isError || check.isError) && <Notice tone="bad">{errorText(send.error ?? check.error)}</Notice>}
        {review && (
          <div className="rounded-md border border-line bg-sunken px-4 py-3">
            <p className="text-[13px] font-medium text-ink">Review of the draft</p>
            <ul className="mt-1.5 list-disc pl-5 text-[13.5px] text-ink-2">
              {review.suggestions.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
            <p className="mt-2 text-[12.5px] text-muted">{review.note}</p>
            {(review.improved_body !== body || review.improved_subject !== subject) && (
              <Button
                size="sm"
                className="mt-3"
                onClick={() => {
                  setSubject(review.improved_subject);
                  setBody(review.improved_body);
                  setReview(null);
                }}
              >
                Use the reviewed version
              </Button>
            )}
          </div>
        )}
        <div className="flex flex-wrap gap-2">
          <Button
            variant="primary"
            loading={send.isPending}
            disabled={noEmail || !subject.trim() || !body.trim() || !lead.can_change}
            onClick={() => send.mutate()}
          >
            Send email
          </Button>
          <Button loading={check.isPending} disabled={!body.trim()} onClick={() => check.mutate()}>
            Check the draft
          </Button>
        </div>
      </div>
    </Panel>
  );
}

function WhatsAppComposer({ lead }: { lead: LeadPage }) {
  const toast = useToast();
  const [text, setText] = useState(lead.whatsapp_message ?? "");
  const allowed = Boolean(lead.whatsapp_opt_in) && Boolean(lead.phone);
  const open = useMutation({
    mutationFn: () =>
      api.post<{ url: string; message: string }>("/whatsapp", { lead_id: lead.latest_lead_id, message: text }),
    onSuccess: (r) => {
      window.open(r.url, "_blank", "noopener");
      toast({ tone: "info", text: r.message });
    },
    onError: (e) => toast({ tone: "bad", text: errorText(e) }),
  });
  return (
    <Panel>
      {!allowed && (
        <Notice tone="info" className="mb-4">
          {lead.phone
            ? "This person has not opted in to WhatsApp messages."
            : "There is no phone number on this person's profile."}
        </Notice>
      )}
      <Field label="Message" hint="Opens WhatsApp with this text; you press send there.">
        <Textarea rows={5} value={text} onChange={(e) => setText(e.target.value)} />
      </Field>
      <Button
        className="mt-4"
        variant="primary"
        disabled={!allowed || !text.trim() || !lead.can_change}
        loading={open.isPending}
        onClick={() => open.mutate()}
      >
        Open WhatsApp
      </Button>
    </Panel>
  );
}

export function Messages({ lead }: { lead: LeadPage }) {
  return (
    <div>
      {!lead.can_change && lead.can_change_why && (
        <Notice tone="info" className="mb-5">
          {lead.can_change_why}
        </Notice>
      )}
      <Section
        title="Email"
        description="Drafted for this person from their course and tier. Edit it, check it, and send it."
      >
        <EmailComposer lead={lead} />
      </Section>
      <Section title="WhatsApp" className="mt-8">
        <WhatsAppComposer lead={lead} />
      </Section>
      {lead.call_script && (
        <Section title="Call script" description="What to say when you call. It uses your name." className="mt-8">
          <blockquote className="whitespace-pre-line rounded-md border border-line bg-surface px-4 py-3 text-[13.5px] leading-relaxed text-ink">
            {lead.call_script}
          </blockquote>
        </Section>
      )}
    </div>
  );
}
