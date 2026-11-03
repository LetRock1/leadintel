import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, errorText, pct } from "@xedu/shared/lib";
import { Badge, Button, buttonClass, EmptyState, Tabs, useToast } from "@xedu/shared/ui";
import { ChevronLeft, UserX } from "lucide-react";
import { Link, useParams, useSearchParams } from "react-router";
import { api } from "../api/client";
import type { LeadPage, PathsResponse } from "../api/types";
import { Score, SimulatedTag } from "../components/lead-bits";
import { Loading, LoadError } from "../components/state";
import { Activity } from "./lead/Activity";
import { Decisions } from "./lead/Decisions";
import { Messages } from "./lead/Messages";
import { NextStep } from "./lead/NextStep";
import { Notes } from "./lead/Notes";
import { SidePanel } from "./lead/SidePanel";

type Tab = "next" | "activity" | "decisions" | "messages" | "notes";
const TABS: Tab[] = ["next", "activity", "decisions", "messages", "notes"];

export default function LeadDetail() {
  const { leadId } = useParams();
  const id = Number(leadId);
  const qc = useQueryClient();
  const toast = useToast();
  // the open section is part of the address (?tab=decisions), so it can be linked to and survives a reload
  const [params, setParams] = useSearchParams();
  const asked = params.get("tab") as Tab | null;
  const tab: Tab = asked && TABS.includes(asked) ? asked : "next";
  const setTab = (t: Tab) => setParams(t === "next" ? {} : { tab: t }, { replace: true });
  const lead = useQuery({
    queryKey: ["lead", id],
    queryFn: () => api.get<LeadPage>(`/leads/${id}`),
    refetchInterval: 15_000,
    enabled: Number.isFinite(id),
  });
  // the stage comes with the what-if paths (cached, shared with the Next step tab)
  const paths = useQuery({
    queryKey: ["lead", id, "paths"],
    queryFn: () => api.get<PathsResponse>(`/leads/${id}/paths`),
    enabled: Number.isFinite(id) && Boolean(lead.data && !lead.data.customer),
    refetchInterval: 60_000,
  });
  const rescore = useMutation({
    mutationFn: () => api.post<{ lead_score: number; tier: string }>(`/leads/${id}/rescore`),
    onSuccess: (r) => {
      toast({ tone: "good", text: `Scored again: ${Math.round(r.lead_score)}, ${r.tier}.` });
      void qc.invalidateQueries({ queryKey: ["lead", id] });
    },
    onError: (e) => toast({ tone: "bad", text: errorText(e) }),
  });

  if (lead.isPending) return <Loading label="Loading the lead" />;
  if (lead.isError) {
    if (lead.error instanceof ApiError && lead.error.status === 404) {
      return (
        <EmptyState
          icon={UserX}
          title="This lead does not exist"
          action={
            <Link to="/leads" className={buttonClass("secondary")}>
              Back to the leads
            </Link>
          }
        >
          It may have been deleted when the person deleted their account.
        </EmptyState>
      );
    }
    return <LoadError error={lead.error} what="the lead" retry={() => void lead.refetch()} />;
  }
  const l = lead.data;
  const stage = l.customer ? "Customer" : l.status.lost ? "Lost" : paths.data?.lead.stage_label;

  return (
    <>
      <Link to="/leads" className="mb-3 inline-flex items-center gap-1 text-[13px] text-muted hover:text-ink">
        <ChevronLeft aria-hidden className="size-4" />
        Leads
      </Link>
      <header className="mb-6 flex flex-wrap items-start gap-x-8 gap-y-4">
        <div className="min-w-0 flex-1 basis-96">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-[22px] font-semibold leading-tight text-ink">{l.name}</h1>
            {l.customer && <Badge tone="good">Customer</Badge>}
            {l.status.lost && <Badge>Lost</Badge>}
            {l.global_control && <Badge tone="info">Control group</Badge>}
            {l.simulated && <SimulatedTag />}
          </div>
          <p className="mt-1 text-[13.5px] text-muted">
            {l.email}
            {l.phone ? `, ${l.phone}` : ""}
            {l.course_type && l.course_type !== "Unknown" ? `. Interested in ${l.course_type}` : ""}
            {stage ? `. ${stage}` : ""}
          </p>
        </div>
        <div className="flex items-center gap-6">
          <div>
            <p className="text-[12.5px] text-muted">Lead score</p>
            <Score score={l.lead_score} tier={l.customer ? null : l.recommended_action} large />
          </div>
          {!l.customer && (
            <div>
              <p className="text-[12.5px] text-muted">Chance of buying</p>
              <p className="num text-[20px] font-semibold text-ink">{pct(l.conversion_probability)}</p>
            </div>
          )}
          <Button size="sm" loading={rescore.isPending} onClick={() => rescore.mutate()}>
            Score again
          </Button>
        </div>
      </header>

      <div className="grid grid-cols-1 items-start gap-8 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="min-w-0">
          <Tabs<Tab>
            label="Lead sections"
            value={tab}
            onChange={setTab}
            className="mb-5"
            tabs={[
              { id: "next", label: "Next step" },
              { id: "activity", label: "Activity" },
              { id: "decisions", label: "Decisions", count: l.decisions.length },
              { id: "messages", label: "Messages" },
              { id: "notes", label: "Notes", count: l.notes.length },
            ]}
          />
          <div role="tabpanel" aria-label={tab}>
            {tab === "next" && <NextStep lead={l} />}
            {tab === "activity" && <Activity lead={l} />}
            {tab === "decisions" && <Decisions decisions={l.decisions} />}
            {tab === "messages" && <Messages lead={l} />}
            {tab === "notes" && <Notes lead={l} />}
          </div>
        </div>
        <SidePanel lead={l} stage={stage} />
      </div>
    </>
  );
}
