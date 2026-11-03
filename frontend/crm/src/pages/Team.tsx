import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { dateTime, errorText, int, money, pct, relative } from "@xedu/shared/lib";
import {
  Badge,
  Button,
  Dialog,
  Field,
  Input,
  Menu,
  Notice,
  Select,
  Switch,
  Table,
  Td,
  Th,
  useToast,
} from "@xedu/shared/ui";
import { MoreHorizontal, Plus } from "lucide-react";
import { useState } from "react";
import { api } from "../api/client";
import type { Member, Role } from "../api/types";
import { useMe } from "../app/session";
import { PageHeader, Panel, Section } from "../components/page";
import { QueryView } from "../components/state";

interface TeamSettings {
  auto_assign: boolean;
  assignment_rule: "round_robin" | "least_loaded";
  task_sla_hours: number;
  callback_sla_hours: number;
  task_expiry_days: number;
  lost_reasons: string[];
  login_lockout: { max_failures: number; minutes: number };
}

interface TeamResponse {
  members: Member[];
  settings: TeamSettings;
  roles: { key: Role; label: string }[];
  rules: string[];
}

interface PerfRow {
  key: string;
  name: string;
  role: Role | null;
  leads: number;
  simulated_leads: number;
  open_leads: number;
  lost: number;
  open_tasks: number;
  overdue_tasks: number;
  tasks_done: number;
  callbacks_open: number;
  callbacks_overdue: number;
  bought: number;
  revenue: number;
  median_hours_to_done: number | null;
  conversion_rate: number | null;
}

const RULE_LABEL: Record<string, string> = { round_robin: "In turn", least_loaded: "Fewest open tasks first" };

function suggestPassword(): string {
  const alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  const bytes = new Uint32Array(14);
  crypto.getRandomValues(bytes);
  const p = Array.from(bytes, (b) => alphabet[b % alphabet.length]).join("");
  return /\d/.test(p) ? p : `${p.slice(0, -1)}7`;
}

function useTeamMutation<T>(fn: (v: T) => Promise<{ message?: string }>, done?: string, onDone?: () => void) {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: fn,
    onSuccess: (r) => {
      toast({ tone: "good", text: r?.message ?? done ?? "Saved." });
      void qc.invalidateQueries({ queryKey: ["team"] });
      void qc.invalidateQueries({ queryKey: ["me"] });
      onDone?.();
    },
    onError: (e) => toast({ tone: "bad", text: errorText(e) }),
  });
}

function AddMember({ roles, onClose }: { roles: TeamResponse["roles"]; onClose: () => void }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("counsellor");
  const [password, setPassword] = useState(suggestPassword);
  const add = useTeamMutation(() => api.post("/team", { name, email, role, password }), "Account added.", onClose);
  return (
    <Dialog
      open
      onClose={onClose}
      title="Add an account"
      description="Give them the email address and this first password. They choose their own password when they first sign in."
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            loading={add.isPending}
            disabled={!name.trim() || !email.trim() || password.length < 8}
            onClick={() => add.mutate(undefined)}
          >
            Add the account
          </Button>
        </>
      }
    >
      <div className="grid gap-4">
        <Field label="Name">
          <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} autoFocus />
        </Field>
        <Field label="Work email address">
          <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} maxLength={120} />
        </Field>
        <Field
          label="Role"
          hint="Counsellors work their own leads. Marketing also runs campaigns and tests. Admins also manage the team."
        >
          <Select
            value={role}
            onChange={(e) => setRole(e.target.value as Role)}
            options={roles.map((r) => ({ value: r.key, label: r.label }))}
          />
        </Field>
        <Field
          label="First password"
          hint="Letters and at least one digit, 8 characters or more."
          trailing={<Button onClick={() => setPassword(suggestPassword())}>New</Button>}
        >
          <Input value={password} onChange={(e) => setPassword(e.target.value)} className="num" />
        </Field>
      </div>
    </Dialog>
  );
}

function EditMember({ m, roles, onClose }: { m: Member; roles: TeamResponse["roles"]; onClose: () => void }) {
  const [name, setName] = useState(m.name);
  const [role, setRole] = useState<Role>(m.role);
  const [takes, setTakes] = useState(m.takes_new_leads);
  const save = useTeamMutation(
    () => api.put(`/team/${m.id}`, { name, role, takes_new_leads: takes }),
    undefined,
    onClose,
  );
  return (
    <Dialog
      open
      onClose={onClose}
      title={`Change ${m.name}'s account`}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={save.isPending} onClick={() => save.mutate(undefined)}>
            Save
          </Button>
        </>
      }
    >
      <div className="grid gap-4">
        <Field label="Name">
          <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} />
        </Field>
        <Field label="Role">
          <Select
            value={role}
            disabled={m.is_owner}
            onChange={(e) => setRole(e.target.value as Role)}
            options={roles.map((r) => ({ value: r.key, label: r.label }))}
          />
        </Field>
        <Switch
          checked={takes}
          onChange={setTakes}
          label="Gets new leads"
          description="New leads are given out in turn to everyone who gets them."
        />
      </div>
    </Dialog>
  );
}

function ResetPassword({ m, onClose }: { m: Member; onClose: () => void }) {
  const [password, setPassword] = useState(suggestPassword);
  const reset = useTeamMutation(() => api.post(`/team/${m.id}/password`, { password }), undefined, onClose);
  return (
    <Dialog
      open
      onClose={onClose}
      title={`Set a new password for ${m.name}`}
      description="Give it to them in person. They choose their own at the next sign-in, and a locked sign-in is unlocked."
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            loading={reset.isPending}
            disabled={password.length < 8}
            onClick={() => reset.mutate(undefined)}
          >
            Set the password
          </Button>
        </>
      }
    >
      <Field label="New password" trailing={<Button onClick={() => setPassword(suggestPassword())}>New</Button>}>
        <Input value={password} onChange={(e) => setPassword(e.target.value)} className="num" />
      </Field>
    </Dialog>
  );
}

function SettingsForm({ s }: { s: TeamSettings }) {
  const [auto, setAuto] = useState(s.auto_assign);
  const [rule, setRule] = useState(s.assignment_rule);
  const [task, setTask] = useState(String(s.task_sla_hours));
  const [callback, setCallback] = useState(String(s.callback_sla_hours));
  const [expiry, setExpiry] = useState(String(s.task_expiry_days));
  const save = useTeamMutation(
    () =>
      api.put("/team-settings", {
        auto_assign: auto,
        assignment_rule: rule,
        task_sla_hours: Number(task),
        callback_sla_hours: Number(callback),
        task_expiry_days: Number(expiry),
      }),
    "Team settings saved.",
  );
  const assign = useTeamMutation(() => api.post<{ message: string }>("/team/assign-now", undefined, { backlog: true }));
  return (
    <Panel>
      <div className="grid gap-4">
        <Switch
          checked={auto}
          onChange={setAuto}
          label="Give out new leads by themselves"
          description="Each new sign-up goes to a counsellor who gets new leads."
        />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="How">
            <Select
              value={rule}
              onChange={(e) => setRule(e.target.value as TeamSettings["assignment_rule"])}
              options={Object.entries(RULE_LABEL).map(([value, label]) => ({ value, label }))}
            />
          </Field>
          <Field label="Task overdue after" hint="Hours">
            <Input
              type="number"
              min={0.25}
              max={720}
              step={0.25}
              value={task}
              onChange={(e) => setTask(e.target.value)}
            />
          </Field>
          <Field label="Call-back overdue after" hint="Hours">
            <Input
              type="number"
              min={0.25}
              max={720}
              step={0.25}
              value={callback}
              onChange={(e) => setCallback(e.target.value)}
            />
          </Field>
          <Field label="Open tasks close after" hint="Days (0: never)">
            <Input type="number" min={0} max={90} value={expiry} onChange={(e) => setExpiry(e.target.value)} />
          </Field>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="primary" loading={save.isPending} onClick={() => save.mutate(undefined)}>
            Save settings
          </Button>
          <Button loading={assign.isPending} onClick={() => assign.mutate(undefined)}>
            Give out unassigned leads now
          </Button>
        </div>
        <p className="text-[12.5px] text-muted">
          After {s.login_lockout.max_failures} wrong passwords in a row an address is locked for{" "}
          {s.login_lockout.minutes} minutes.
        </p>
      </div>
    </Panel>
  );
}

export default function Team() {
  const me = useMe();
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<Member | null>(null);
  const [resetting, setResetting] = useState<Member | null>(null);
  const team = useQuery({ queryKey: ["team"], queryFn: () => api.get<TeamResponse>("/team"), refetchInterval: 60_000 });
  const perf = useQuery({
    queryKey: ["team", "performance"],
    queryFn: () => api.get<{ days: number; rows: PerfRow[] }>("/team/performance"),
    refetchInterval: 60_000,
  });
  const toggle = useTeamMutation((m: Member) => api.put(`/team/${m.id}`, { active: !m.active }));
  const remove = useTeamMutation((m: Member) => api.del(`/team/${m.id}`));

  return (
    <>
      <PageHeader
        title="Team"
        description="Accounts of the people who use the CRM, how leads are given out, and how each counsellor is doing."
        actions={
          <Button
            variant="primary"
            icon={<Plus aria-hidden className="size-4" />}
            onClick={() => setAdding(true)}
            disabled={!team.data}
          >
            Add an account
          </Button>
        }
      />
      <QueryView query={team} what="the team">
        {(t) => (
          <>
            <Section title="Accounts">
              <Table label="Accounts">
                <thead>
                  <tr>
                    <Th>Name</Th>
                    <Th>Role</Th>
                    <Th>New leads</Th>
                    <Th>Status</Th>
                    <Th>Last sign-in</Th>
                    <Th aria-label="Actions" />
                  </tr>
                </thead>
                <tbody>
                  {t.members.map((m) => (
                    <tr key={m.id}>
                      <Td>
                        <span className="font-medium text-ink">{m.name}</span>
                        {m.is_owner && <span className="ml-2 text-[12.5px] text-muted">Owner</span>}
                        <span className="block text-[12.5px] text-muted">{m.email}</span>
                      </Td>
                      <Td className="text-ink-2">{m.role_label}</Td>
                      <Td className="text-ink-2">{m.takes_new_leads ? "Gets them" : "No"}</Td>
                      <Td>
                        {!m.active ? (
                          <Badge>Switched off</Badge>
                        ) : m.must_change_password ? (
                          <Badge tone="warn">First sign-in pending</Badge>
                        ) : (
                          <Badge tone="good">Active</Badge>
                        )}
                      </Td>
                      <Td className="whitespace-nowrap text-muted" title={dateTime(m.last_login_at)}>
                        {m.last_login_at ? relative(m.last_login_at) : "Never"}
                      </Td>
                      <Td className="text-right">
                        <Menu
                          label={`Account of ${m.name}`}
                          items={[
                            { label: "Change", onSelect: () => setEditing(m) },
                            { label: "Set a new password", onSelect: () => setResetting(m) },
                            ...(m.is_owner || m.id === me.id
                              ? []
                              : [
                                  {
                                    label: m.active ? "Switch off" : "Switch on",
                                    hint: m.active
                                      ? team.data?.settings.auto_assign &&
                                        (team.data?.members ?? []).some(
                                          (x) => x.role === "counsellor" && x.active && x.id !== m.id,
                                        )
                                        ? "Their leads go to the other counsellors"
                                        : "Their leads become unassigned"
                                      : undefined,
                                    onSelect: () => toggle.mutate(m),
                                  },
                                  { label: "Delete", danger: true, onSelect: () => remove.mutate(m) },
                                ]),
                          ]}
                          trigger={(p) => (
                            <button
                              type="button"
                              {...p}
                              aria-label={`Actions for ${m.name}`}
                              className="rounded-sm p-1.5 text-muted hover:bg-sunken hover:text-ink"
                            >
                              <MoreHorizontal aria-hidden className="size-4" />
                            </button>
                          )}
                        />
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
              {!t.members.some((m) => m.role === "counsellor" && m.active) && (
                <Notice tone="info" className="mt-3">
                  There is no counsellor yet, so new leads stay unassigned. Add a counsellor account to give leads out.
                </Notice>
              )}
            </Section>
            <div className="mt-9 grid grid-cols-1 gap-x-6 gap-y-9 xl:grid-cols-[minmax(0,26rem)_minmax(0,1fr)] [&>section]:mt-0">
              <Section title="Giving out leads">
                <SettingsForm key={JSON.stringify(t.settings)} s={t.settings} />
              </Section>
              <Section
                title="How each person is doing"
                description={perf.data ? `Last ${perf.data.days} days.` : undefined}
              >
                <QueryView query={perf} what="the team's numbers">
                  {(p) => (
                    <Table label="Performance">
                      <thead>
                        <tr>
                          <Th>Who</Th>
                          <Th className="text-right">Leads</Th>
                          <Th className="text-right">Open tasks</Th>
                          <Th className="text-right">Done</Th>
                          <Th className="text-right">Hours to do a task</Th>
                          <Th className="text-right">Bought</Th>
                          <Th className="text-right">Revenue</Th>
                        </tr>
                      </thead>
                      <tbody>
                        {p.rows.map((r) => (
                          <tr key={r.key}>
                            <Td className="text-ink">{r.name}</Td>
                            <Td className="num text-right">
                              {int(r.leads)}
                              <span className="block text-[12px] text-muted">{int(r.open_leads)} open</span>
                            </Td>
                            <Td className="num text-right">
                              {int(r.open_tasks)}
                              {r.overdue_tasks > 0 && (
                                <span className="block text-[12px] text-warn">{int(r.overdue_tasks)} overdue</span>
                              )}
                            </Td>
                            <Td className="num text-right">{int(r.tasks_done)}</Td>
                            <Td className="num text-right">
                              {r.median_hours_to_done === null ? "None" : r.median_hours_to_done.toFixed(1)}
                            </Td>
                            <Td className="num text-right">
                              {int(r.bought)}
                              <span className="block text-[12px] text-muted">{pct(r.conversion_rate, 0, "")}</span>
                            </Td>
                            <Td className="num text-right">{money(r.revenue)}</Td>
                          </tr>
                        ))}
                      </tbody>
                    </Table>
                  )}
                </QueryView>
              </Section>
            </div>
            {adding && <AddMember roles={t.roles} onClose={() => setAdding(false)} />}
            {editing && <EditMember m={editing} roles={t.roles} onClose={() => setEditing(null)} />}
            {resetting && <ResetPassword m={resetting} onClose={() => setResetting(null)} />}
          </>
        )}
      </QueryView>
    </>
  );
}
