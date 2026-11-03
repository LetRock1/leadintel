import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { dateTime, errorText, int, pct, plural, points } from "@xedu/shared/lib";
import {
  Badge,
  Button,
  Dialog,
  EmptyState,
  Field,
  Input,
  Menu,
  Notice,
  Segmented,
  Select,
  Table,
  Td,
  Textarea,
  Th,
  useToast,
} from "@xedu/shared/ui";
import { MoreHorizontal, Plus, Send } from "lucide-react";
import { useState } from "react";
import { api } from "../api/client";
import type { AbPlan, Campaign, CampaignsResponse } from "../api/types";
import { useSession } from "../app/session";
import { SimulatedTag } from "../components/lead-bits";
import { PageHeader } from "../components/page";
import { Loading, LoadError } from "../components/state";

function localNow(minutesAhead = 0): string {
  const d = new Date(Date.now() + minutesAhead * 60_000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function NewCampaign({ audiences, holdout, onClose }: { audiences: string[]; holdout: number; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [name, setName] = useState("");
  const [tier, setTier] = useState(audiences[0] ?? "All leads");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("Hi {first_name},\n\n");
  const [when, setWhen] = useState<"now" | "later">("later");
  const [at, setAt] = useState(() => localNow(60));
  const [share, setShare] = useState(String(holdout));
  const reach = useQuery({
    queryKey: ["ab-plan", tier, "reach"],
    queryFn: () => api.get<AbPlan>("/ab-tests/plan", { tier, variants: 1, metric: "purchase", control_share: 0 }),
  });
  const create = useMutation({
    mutationFn: async () => {
      const r = await api.post<{ id: number; message: string }>("/campaigns", {
        name,
        tier,
        subject,
        body,
        scheduled_at: when === "now" ? localNow() : at,
        holdout_share: Number(share),
      });
      if (when === "now") return api.post<{ message: string }>(`/campaigns/${r.id}/send-now`);
      return r;
    },
    onSuccess: (r) => {
      toast({ tone: "good", text: r.message });
      void qc.invalidateQueries({ queryKey: ["campaigns"] });
      onClose();
    },
  });
  const ready = name.trim() && subject.trim() && body.trim() && (when === "now" || at);
  return (
    <Dialog
      open
      size="lg"
      onClose={onClose}
      title="New campaign"
      description="One email to everyone in an audience who accepts email. A random hold-out group gets nothing, so the campaign's real effect can be measured."
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={create.isPending} disabled={!ready} onClick={() => create.mutate()}>
            {when === "now" ? "Send now" : "Schedule"}
          </Button>
        </>
      }
    >
      <div className="grid gap-4">
        {create.isError && <Notice tone="bad">{errorText(create.error)}</Notice>}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Name" hint="Only the team sees it.">
            <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={200} />
          </Field>
          <Field
            label="Audience"
            hint={reach.data ? `${plural(reach.data.audience, "person", "people")} would get it now.` : " "}
          >
            <Select
              value={tier}
              onChange={(e) => setTier(e.target.value)}
              options={audiences.map((a) => ({ value: a, label: a }))}
            />
          </Field>
        </div>
        <Field label="Subject">
          <Input value={subject} onChange={(e) => setSubject(e.target.value)} maxLength={300} />
        </Field>
        <Field
          label="Message"
          hint="{first_name} and {course} are filled in for each person. An unsubscribe link is added."
        >
          <Textarea rows={8} value={body} onChange={(e) => setBody(e.target.value)} />
        </Field>
        <div className="grid grid-cols-1 items-end gap-4 sm:grid-cols-[auto_1fr_auto]">
          <div>
            <p className="mb-1.5 text-[13px] font-medium text-ink">When</p>
            <Segmented
              label="When"
              value={when}
              onChange={setWhen}
              options={[
                { value: "later", label: "Schedule" },
                { value: "now", label: "Send now" },
              ]}
            />
          </div>
          {when === "later" ? (
            <Field label="Date and time">
              <Input type="datetime-local" value={at} onChange={(e) => setAt(e.target.value)} />
            </Field>
          ) : (
            <span />
          )}
          <Field label="Hold-out group">
            <Select
              value={share}
              onChange={(e) => setShare(e.target.value)}
              options={[0, 0.05, 0.1, 0.2].map((v) => ({
                value: String(v),
                label: v ? `${v * 100}% get nothing` : "No hold-out",
              }))}
            />
          </Field>
        </div>
      </div>
    </Dialog>
  );
}

function Effect({ c }: { c: Campaign }) {
  if (!c.incremental) return <span className="text-muted">{c.sent ? "No hold-out" : ""}</span>;
  const { lift, ci, final } = c.incremental;
  return (
    <div className="text-right">
      <p className="num font-medium text-ink">{points(lift)}</p>
      <p className="num text-[12px] text-muted">
        {points(ci[0])} to {points(ci[1])}
        {final ? "" : ", still counting"}
      </p>
    </div>
  );
}

function Status({ c }: { c: Campaign }) {
  if (c.sent) return <Badge tone="good">Sent {dateTime(c.sent_at)}</Badge>;
  if (c.status === "failed")
    return (
      <Badge tone="bad" title={c.error ?? undefined}>
        Failed
      </Badge>
    );
  if (c.status === "draft" || !c.scheduled_at) return <Badge>Draft</Badge>;
  return <Badge tone="info">Scheduled {dateTime(c.scheduled_at)}</Badge>;
}

export default function Campaigns() {
  const { can } = useSession();
  const qc = useQueryClient();
  const toast = useToast();
  const [creating, setCreating] = useState(false);
  const list = useQuery({
    queryKey: ["campaigns"],
    queryFn: () => api.get<CampaignsResponse>("/campaigns"),
    refetchInterval: 30_000,
  });
  const act = useMutation({
    mutationFn: ({ c, what }: { c: Campaign; what: "send" | "delete" | "again" }) =>
      what === "send"
        ? api.post<{ message: string }>(`/campaigns/${c.id}/send-now`)
        : what === "again"
          ? api.post<{ message: string }>(`/campaigns/${c.id}/send-failed`)
          : api.del<{ message: string }>(`/campaigns/${c.id}`),
    onSuccess: (r) => {
      toast({ tone: "good", text: r.message });
      void qc.invalidateQueries({ queryKey: ["campaigns"] });
    },
    onError: (e) => toast({ tone: "bad", text: errorText(e) }),
  });
  const marketing = can("marketing");

  return (
    <>
      <PageHeader
        title="Campaigns"
        description="Emails to a whole audience. Each one keeps a random hold-out group, so its effect is measured against people who got nothing."
        actions={
          marketing ? (
            <Button
              variant="primary"
              icon={<Plus aria-hidden className="size-4" />}
              onClick={() => setCreating(true)}
              disabled={!list.data}
            >
              New campaign
            </Button>
          ) : undefined
        }
      />
      {list.isPending ? (
        <Loading label="Loading the campaigns" />
      ) : list.isError ? (
        <LoadError error={list.error} what="the campaigns" retry={() => void list.refetch()} />
      ) : list.data.campaigns.length === 0 ? (
        <div className="rounded-md border border-line bg-surface px-4">
          <EmptyState icon={Send} title="No campaigns yet">
            Create a campaign to email an audience, such as everyone in the Nurture tier.
          </EmptyState>
        </div>
      ) : (
        <>
          <Table label="Campaigns">
            <thead>
              <tr>
                <Th>Campaign</Th>
                <Th>Audience</Th>
                <Th>Status</Th>
                <Th className="text-right">Emails</Th>
                <Th className="text-right">Clicked</Th>
                <Th className="text-right">Bought</Th>
                <Th
                  className="text-right"
                  title="Share who bought among those emailed, minus the share among the hold-out group"
                >
                  Effect on buying
                </Th>
                {marketing && <Th aria-label="Actions" />}
              </tr>
            </thead>
            <tbody>
              {list.data.campaigns.map((c) => (
                <tr key={c.id}>
                  <Td className="max-w-80">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium text-ink">{c.name}</span>
                      {c.simulated && <SimulatedTag />}
                    </div>
                    <p className="truncate text-[12.5px] text-muted">{c.subject}</p>
                  </Td>
                  <Td className="text-ink-2">{c.tier}</Td>
                  <Td>
                    <Status c={c} />
                  </Td>
                  <Td className="num text-right">
                    {c.sent ? int(c.delivered) : c.audience_now !== null ? `${int(c.audience_now)} now` : ""}
                    {c.sent && c.held_out ? <p className="text-[12px] text-muted">{int(c.held_out)} held out</p> : null}
                    {c.sent && c.failed > 0 ? (
                      <p className="text-[12px] text-bad" title={c.failed_reason ?? undefined}>
                        {int(c.failed)} not sent
                      </p>
                    ) : null}
                  </Td>
                  <Td className="num text-right">
                    {c.sent ? pct(c.delivered ? c.clicks / c.delivered : null, 0, "") : ""}
                  </Td>
                  <Td className="num text-right">
                    {c.sent ? int(c.conversions) : ""}
                    {c.holdout && (
                      <p className="text-[12px] text-muted">
                        {int(c.holdout.conversions)} of {int(c.holdout.people)} held out
                      </p>
                    )}
                  </Td>
                  <Td>
                    <Effect c={c} />
                  </Td>
                  {marketing && (
                    <Td className="w-10">
                      {(!c.sent || c.failed > 0) && (
                        <Menu
                          label={`Campaign ${c.name}`}
                          items={
                            c.sent
                              ? [
                                  {
                                    label: `Send the ${plural(c.failed, "email")} that did not go out again`,
                                    onSelect: () => act.mutate({ c, what: "again" }),
                                  },
                                ]
                              : [
                                  { label: "Send now", onSelect: () => act.mutate({ c, what: "send" }) },
                                  { label: "Delete", danger: true, onSelect: () => act.mutate({ c, what: "delete" }) },
                                ]
                          }
                          trigger={(p) => (
                            <button
                              type="button"
                              {...p}
                              aria-label={`Actions for ${c.name}`}
                              className="rounded-sm p-1.5 text-muted hover:bg-sunken hover:text-ink"
                            >
                              <MoreHorizontal aria-hidden className="size-4" />
                            </button>
                          )}
                        />
                      )}
                    </Td>
                  )}
                </tr>
              ))}
            </tbody>
          </Table>
          <p className="mt-3 max-w-[80ch] text-[12.5px] text-muted">
            Effect on buying is in percentage points with a 95% interval. An interval that includes zero means the
            campaign has not shown an effect yet. Purchases count for {plural(list.data.window_days, "day")} after the
            email.
          </p>
        </>
      )}
      {creating && list.data && (
        <NewCampaign
          audiences={list.data.audiences}
          holdout={list.data.default_holdout_share}
          onClose={() => setCreating(false)}
        />
      )}
    </>
  );
}
