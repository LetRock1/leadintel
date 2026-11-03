import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { errorText, int, money, plural, relative } from "@xedu/shared/lib";
import { Button, EmptyState, Pager, Segmented, Select, Table, Td, Th, useToast } from "@xedu/shared/ui";
import { Download, Users, X } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router";
import { api } from "../api/client";
import type { LeadsResponse } from "../api/types";
import { useMe, useSession } from "../app/session";
import { Person, Score } from "../components/lead-bits";
import { PageHeader } from "../components/page";
import { Loading, LoadError } from "../components/state";
import { actionLabel, TIERS } from "../lib/labels";

const LIMIT = 50;

export default function Leads() {
  const me = useMe();
  const { can } = useSession();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const search = params.get("search") ?? "";
  const tier = params.get("tier") ?? "";
  const segment = params.get("segment") ?? "all";
  const owner = params.get("owner") ?? "all";
  const sort = params.get("sort") ?? "";
  const offset = Number(params.get("offset") ?? 0) || 0;
  const [exporting, setExporting] = useState(false);

  const set = (changes: Record<string, string | null>) =>
    setParams(
      (p) => {
        for (const [k, v] of Object.entries(changes)) {
          if (v === null || v === "") p.delete(k);
          else p.set(k, v);
        }
        if (!("offset" in changes)) p.delete("offset");
        return p;
      },
      { replace: true },
    );

  const leads = useQuery({
    queryKey: ["leads", { search, tier, segment, owner, sort, offset }],
    queryFn: () => api.get<LeadsResponse>("/leads", { search, tier, segment, owner, sort, offset, limit: LIMIT }),
    placeholderData: keepPreviousData,
    refetchInterval: 30_000,
  });

  const exportCsv = async () => {
    setExporting(true);
    try {
      await api.download("/leads/export.csv", "leads.csv");
    } catch (e) {
      toast({ tone: "bad", text: errorText(e) });
    } finally {
      setExporting(false);
    }
  };

  const counts = leads.data?.counts;
  const ownerOptions = [
    { value: "all", label: "Everyone's leads" },
    { value: "me", label: `Mine${counts ? ` (${int(counts.mine)})` : ""}` },
    { value: "unassigned", label: `Unassigned${counts ? ` (${int(counts.unassigned)})` : ""}` },
    ...me.team.filter((m) => m.id !== me.id && m.active).map((m) => ({ value: String(m.id), label: m.name })),
  ];

  return (
    <>
      <PageHeader
        title="Leads"
        description="Everyone who signed up, one row per person, with their current score and the step the CRM would take next."
        actions={
          can("marketing") ? (
            <Button
              icon={<Download aria-hidden className="size-4" />}
              loading={exporting}
              onClick={() => void exportCsv()}
            >
              Export CSV
            </Button>
          ) : undefined
        }
      />

      <div className="mb-3 flex flex-wrap items-center gap-2.5">
        <Segmented
          label="Learners"
          value={segment}
          onChange={(v) => set({ segment: v === "all" ? null : v })}
          options={[
            { value: "all", label: "All", count: counts?.all },
            { value: "real", label: "Real people", count: counts?.real },
            { value: "simulated", label: "Simulated", count: counts?.simulated },
          ]}
        />
        <Select
          aria-label="Tier"
          value={tier}
          onChange={(e) => set({ tier: e.target.value })}
          className="w-56"
          options={[
            { value: "", label: "Every tier" },
            ...TIERS.map((t) => ({ value: t, label: t })),
            { value: "Customers", label: "Customers" },
          ]}
        />
        <Select
          aria-label="Whose leads"
          value={owner}
          onChange={(e) => set({ owner: e.target.value === "all" ? null : e.target.value })}
          className="w-52"
          options={ownerOptions}
        />
        <Select
          aria-label="Sort by"
          value={sort}
          onChange={(e) => set({ sort: e.target.value })}
          className="w-52"
          options={[
            { value: "", label: "Latest visit first" },
            { value: "added", label: "Latest contact record first" },
            { value: "score", label: "Highest score first" },
            { value: "name", label: "Name, A to Z" },
          ]}
        />
        {search && (
          <span className="inline-flex h-8 items-center gap-1.5 rounded-sm bg-brand-soft pl-2.5 pr-1 text-[13px] text-brand-ink">
            Matching &ldquo;{search}&rdquo;
            <button
              type="button"
              aria-label="Clear the search"
              className="rounded-xs p-1 hover:bg-surface/60"
              onClick={() => set({ search: null })}
            >
              <X aria-hidden className="size-3.5" />
            </button>
          </span>
        )}
        {leads.data && (
          <p className="ml-auto text-[13px] text-muted">{plural(leads.data.matching, "person", "people")}</p>
        )}
      </div>

      {leads.isPending ? (
        <Loading label="Loading the leads" />
      ) : leads.isError ? (
        <LoadError error={leads.error} what="the leads" retry={() => void leads.refetch()} />
      ) : leads.data.leads.length === 0 ? (
        <div className="rounded-md border border-line bg-surface px-4">
          <EmptyState
            icon={Users}
            title={search || tier || owner !== "all" ? "No one matches these filters" : "No leads yet"}
          >
            {search || tier || owner !== "all"
              ? "Change the filters or clear the search."
              : "A lead appears here as soon as someone signs up on the website."}
          </EmptyState>
        </div>
      ) : (
        <>
          <Table label="Leads">
            <thead>
              <tr>
                <Th>Person</Th>
                <Th>Course</Th>
                <Th>Score</Th>
                <Th>Next step</Th>
                <Th>Owner</Th>
                <Th className="text-right">Last visit</Th>
              </tr>
            </thead>
            <tbody>
              {leads.data.leads.map((l) => (
                <tr key={l.id} className="hover:bg-sunken/60">
                  <Td className="max-w-72">
                    <Person
                      leadId={l.id}
                      name={l.name}
                      email={l.email}
                      simulated={l.simulated}
                      customer={l.customer}
                      lost={l.lost}
                    />
                  </Td>
                  <Td className="max-w-52">
                    <span className="block truncate text-ink-2">{l.course_type ?? "Not chosen"}</span>
                    {l.customer && <span className="block text-[12.5px] text-muted">Spent {money(l.spent)}</span>}
                  </Td>
                  <Td>
                    <Score score={l.lead_score} tier={l.customer ? null : l.recommended_action} />
                  </Td>
                  <Td className="text-ink-2">{l.customer || l.lost ? "" : actionLabel(l.nba_action, true)}</Td>
                  <Td className="text-ink-2">{l.owner}</Td>
                  <Td
                    className="whitespace-nowrap text-right text-muted"
                    title="The last time this person was on the website"
                  >
                    {relative(l.last_active_at ?? l.created_at)}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
          <div className="mt-3">
            <Pager
              offset={offset}
              limit={LIMIT}
              total={leads.data.matching}
              onChange={(o) => set({ offset: o ? String(o) : null })}
            />
          </div>
        </>
      )}
    </>
  );
}
