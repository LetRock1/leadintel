import { useMutation, useQueryClient } from "@tanstack/react-query";
import { date, dateTime, errorText, money, relative } from "@xedu/shared/lib";
import { Badge, Button, Dialog, Field, Menu, Notice, Select, Textarea, useToast } from "@xedu/shared/ui";
import { ChevronDown } from "lucide-react";
import { useState, type ReactNode } from "react";
import { api } from "../../api/client";
import type { LeadPage } from "../../api/types";
import { useMe } from "../../app/session";

function Block({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return (
    <section className="border-b border-line px-4 py-4 last:border-b-0">
      <div className="mb-2 flex items-center gap-2">
        <h2 className="text-[13px] font-semibold text-ink">{title}</h2>
        <div className="ml-auto">{action}</div>
      </div>
      {children}
    </section>
  );
}

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex gap-3 py-0.5 text-[13px]">
      <dt className="w-28 shrink-0 text-muted">{label}</dt>
      <dd className="min-w-0 flex-1 break-words text-ink">{value}</dd>
    </div>
  );
}

function useLeadMutation<T>(lead: LeadPage, fn: (body: T) => Promise<{ message?: string }>, done?: string) {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: fn,
    onSuccess: (r) => {
      toast({ tone: "good", text: r?.message ?? done ?? "Saved." });
      void qc.invalidateQueries({ queryKey: ["lead", lead.id] });
      void qc.invalidateQueries({ queryKey: ["leads"] });
      void qc.invalidateQueries({ queryKey: ["pipeline"] });
    },
    onError: (e) => toast({ tone: "bad", text: errorText(e) }),
  });
}

function Owner({ lead }: { lead: LeadPage }) {
  const me = useMe();
  const change = useLeadMutation<number | null>(lead, (member_id) => api.put(`/leads/${lead.id}/owner`, { member_id }));
  if (me.role === "admin") {
    return (
      <Select
        aria-label="Owner"
        value={lead.owner.id === null ? "" : String(lead.owner.id)}
        disabled={change.isPending}
        onChange={(e) => change.mutate(e.target.value ? Number(e.target.value) : null)}
        options={[
          { value: "", label: "Unassigned" },
          ...lead.team.map((m) => ({ value: String(m.id), label: m.name })),
        ]}
      />
    );
  }
  return (
    <div className="flex items-center gap-2 text-[13.5px]">
      <span className="text-ink">{lead.owner.name}</span>
      {lead.owner.id === null && (
        <Button size="sm" loading={change.isPending} onClick={() => change.mutate(me.id)}>
          Take this lead
        </Button>
      )}
    </div>
  );
}

function LostDialog({ lead, onClose }: { lead: LeadPage; onClose: () => void }) {
  const [reason, setReason] = useState(lead.lost_reasons[0] ?? "");
  const [note, setNote] = useState("");
  const close = useLeadMutation(
    lead,
    () => api.post(`/leads/${lead.id}/status`, { status: "lost", reason, note: note || null }),
    "Closed as lost.",
  );
  return (
    <Dialog
      open
      onClose={onClose}
      title={`Close ${lead.name} as lost`}
      description="The CRM stops every automatic step for them until someone re-opens the lead."
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            variant="danger"
            loading={close.isPending}
            onClick={() => close.mutate(undefined, { onSuccess: onClose })}
          >
            Close as lost
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <Field label="Reason">
          <Select
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            options={lead.lost_reasons.map((r) => ({ value: r, label: r }))}
          />
        </Field>
        <Field label="Note" optional>
          <Textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} maxLength={200} />
        </Field>
      </div>
    </Dialog>
  );
}

const CHANNELS = [
  { key: "email", label: "Emails", off: (l: LeadPage) => l.do_not_email === "Yes" },
  { key: "call", label: "Calls", off: (l: LeadPage) => l.do_not_call === "Yes" },
  { key: "whatsapp", label: "WhatsApp", off: (l: LeadPage) => !l.whatsapp_opt_in },
] as const;

export function SidePanel({ lead, stage }: { lead: LeadPage; stage?: string }) {
  const [losing, setLosing] = useState(false);
  const reopen = useLeadMutation(lead, () => api.post(`/leads/${lead.id}/status`, { status: "open" }), "Re-opened.");
  const consent = useLeadMutation<string>(lead, (channel) => api.post(`/leads/${lead.id}/consent`, { channel }));
  const allowed = CHANNELS.filter((c) => !c.off(lead));
  return (
    <aside className="rounded-md border border-line bg-surface">
      <Block title="Owner">
        <Owner lead={lead} />
        {lead.owner.assigned_at && (
          <p className="mt-1.5 text-[12.5px] text-muted">
            Since {date(lead.owner.assigned_at)}
            {lead.owner.how === "round_robin" || lead.owner.how === "auto" ? ", given out automatically" : ""}
          </p>
        )}
      </Block>

      <Block title="About">
        <dl>
          <Row
            label="Course"
            value={lead.course_type && lead.course_type !== "Unknown" ? lead.course_type : "Not chosen yet"}
          />
          {stage && <Row label="Stage" value={stage} />}
          <Row label="Signed up" value={dateTime(lead.signed_up_at)} />
          {lead.last_active_at && (
            <Row
              label="Last visit"
              value={<span title={dateTime(lead.last_active_at)}>{relative(lead.last_active_at)}</span>}
            />
          )}
          <Row label="Occupation" value={lead.current_occupation ?? "Not given"} />
          {lead.specialization && <Row label="Field" value={lead.specialization} />}
          {lead.city && <Row label="City" value={lead.city} />}
          {lead.age_bracket && <Row label="Age" value={lead.age_bracket} />}
          <Row label="Came from" value={lead.lead_source ?? "Not known"} />
          <Row label="Device" value={lead.device_type ?? "Not known"} />
          <Row label="Phone" value={lead.phone ?? "Not given"} />
          <Row label="Touches" value={`${lead.touches.length} contact records`} />
        </dl>
      </Block>

      <Block
        title="Contact preferences"
        action={
          lead.can_change && allowed.length > 0 ? (
            <Menu
              label="Record a preference"
              items={allowed.map((c) => ({
                label: `They do not want ${c.label.toLowerCase()}`,
                onSelect: () => consent.mutate(c.key),
              }))}
              trigger={(p) => (
                <Button size="sm" variant="ghost" {...p}>
                  Record
                  <ChevronDown aria-hidden className="size-3.5" />
                </Button>
              )}
            />
          ) : undefined
        }
      >
        <ul className="flex flex-col gap-1 text-[13px]">
          {CHANNELS.map((c) => (
            <li key={c.key} className="flex items-center justify-between">
              <span className="text-ink-2">{c.label}</span>
              {c.off(lead) ? (
                <Badge>{c.key === "whatsapp" ? "Not opted in" : "Does not want"}</Badge>
              ) : (
                <Badge tone="good">Allowed</Badge>
              )}
            </li>
          ))}
        </ul>
        <p className="mt-2 text-[12px] text-muted">
          Only the person can switch a channel back on, in their settings on the website.
        </p>
      </Block>

      <Block title="Status">
        {lead.customer ? (
          <p className="text-[13.5px] text-ink">
            Customer since {date(lead.purchases[lead.purchases.length - 1]?.purchased_at)}
          </p>
        ) : lead.status.lost ? (
          <>
            <p className="text-[13.5px] text-ink">
              Closed as lost{lead.status.reason ? `: ${lead.status.reason}` : ""}
            </p>
            <p className="mt-0.5 text-[12.5px] text-muted">
              {lead.status.by ? `By ${lead.status.by}, ` : ""}
              {relative(lead.status.since)}
              {lead.status.note ? `. ${lead.status.note}` : ""}
            </p>
            {lead.can_change && (
              <Button size="sm" className="mt-2" loading={reopen.isPending} onClick={() => reopen.mutate(undefined)}>
                Re-open the lead
              </Button>
            )}
          </>
        ) : (
          <>
            <p className="text-[13.5px] text-ink">Open</p>
            {lead.can_change && (
              <Button size="sm" variant="danger" className="mt-2" onClick={() => setLosing(true)}>
                Close as lost
              </Button>
            )}
          </>
        )}
        {lead.global_control && (
          <Notice tone="info" className="mt-3">
            In the control group: the CRM never contacts them.
          </Notice>
        )}
      </Block>

      {lead.purchases.length > 0 && (
        <Block title="Purchases">
          <ul className="flex flex-col gap-1.5 text-[13px]">
            {lead.purchases.map((p) => (
              <li key={p.id} className="flex items-baseline gap-2">
                <span className="min-w-0 flex-1 truncate text-ink">{p.course_title}</span>
                <span className="num text-ink">{money(p.price_paid)}</span>
              </li>
            ))}
          </ul>
        </Block>
      )}

      {lead.coupons.length > 0 && (
        <Block title="Coupons">
          <ul className="flex flex-col gap-1.5 text-[13px]">
            {lead.coupons.slice(0, 6).map((c) => (
              <li key={c.id} className="flex items-baseline gap-2">
                <span className="num min-w-0 flex-1 truncate text-ink">{c.coupon_code}</span>
                <span className="text-muted">
                  {c.discount_pct}% {c.used ? "used" : c.expires_at ? `until ${date(c.expires_at)}` : ""}
                </span>
              </li>
            ))}
          </ul>
        </Block>
      )}
      {losing && <LostDialog lead={lead} onClose={() => setLosing(false)} />}
    </aside>
  );
}
