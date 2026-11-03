import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { dateTime, relative } from "@xedu/shared/lib";
import { EmptyState, Select, Table, Td, Th } from "@xedu/shared/ui";
import { ScrollText } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { api } from "../api/client";
import { useMe } from "../app/session";
import { PageHeader } from "../components/page";
import { QueryView } from "../components/state";
import { auditLabel } from "../lib/labels";

interface Entry {
  id: number;
  at: string;
  member_id: number | null;
  member_name: string | null;
  role: string | null;
  action: string;
  target_type: string | null;
  target_id: number | null;
  detail: string | null;
  lead_id: number | null;
}

export default function Audit() {
  const me = useMe();
  const [action, setAction] = useState("");
  const [member, setMember] = useState("");
  const log = useQuery({
    queryKey: ["audit", action, member],
    queryFn: () =>
      api.get<{ entries: Entry[]; actions: string[] }>("/audit", { action, member_id: member, limit: 500 }),
    placeholderData: keepPreviousData,
    refetchInterval: 30_000,
  });
  return (
    <>
      <PageHeader
        title="Audit log"
        description="Who on the team changed what, and when. Learners appear by their lead number only."
        actions={
          <>
            <Select
              aria-label="Person"
              value={member}
              onChange={(e) => setMember(e.target.value)}
              className="w-48"
              options={[
                { value: "", label: "Everyone" },
                ...me.team.map((m) => ({ value: String(m.id), label: m.name })),
              ]}
            />
            <Select
              aria-label="Kind of change"
              value={action}
              onChange={(e) => setAction(e.target.value)}
              className="w-64"
              options={[
                { value: "", label: "Every kind of change" },
                ...(log.data?.actions ?? []).map((a) => ({ value: a, label: auditLabel(a) })),
              ]}
            />
          </>
        }
      />
      <QueryView query={log} what="the audit log">
        {(d) =>
          d.entries.length === 0 ? (
            <div className="rounded-md border border-line bg-surface px-4">
              <EmptyState icon={ScrollText} title="Nothing recorded with these filters" />
            </div>
          ) : (
            <Table label="Audit log">
              <thead>
                <tr>
                  <Th>When</Th>
                  <Th>Who</Th>
                  <Th>What</Th>
                  <Th>Details</Th>
                </tr>
              </thead>
              <tbody>
                {d.entries.map((e) => (
                  <tr key={e.id}>
                    <Td className="whitespace-nowrap text-muted" title={dateTime(e.at)}>
                      {relative(e.at)}
                    </Td>
                    <Td className="text-ink">{e.member_name ?? "The CRM"}</Td>
                    <Td className="text-ink-2">{auditLabel(e.action)}</Td>
                    <Td className="max-w-[28rem] text-[13px] text-muted">
                      {e.lead_id ? (
                        <Link to={`/leads/${e.lead_id}`} className="mr-2 text-brand-ink hover:underline">
                          Lead {e.lead_id}
                        </Link>
                      ) : null}
                      {e.detail}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )
        }
      </QueryView>
    </>
  );
}
