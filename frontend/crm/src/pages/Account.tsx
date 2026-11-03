import { useMutation, useQueryClient } from "@tanstack/react-query";
import { dateTime, errorText } from "@xedu/shared/lib";
import { Button, Field, Input, Notice, useToast } from "@xedu/shared/ui";
import { LogOut } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import { api, setToken } from "../api/client";
import { useMe, useSession } from "../app/session";
import { Facts, PageHeader, Panel, Section } from "../components/page";

function problem(pw: string): string | null {
  if (pw.length < 8) return "Use at least 8 characters.";
  if (!/[a-z]/i.test(pw) || !/\d/.test(pw)) return "Use letters and at least one digit.";
  return null;
}

export default function Account() {
  const me = useMe();
  const { signOut } = useSession();
  const qc = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [tried, setTried] = useState(false);

  const change = useMutation({
    mutationFn: () =>
      api.post<{ message: string; token: string }>("/me/password", { current_password: current, new_password: next }),
    onSuccess: async (r) => {
      // a new password signs out every other session; this one goes on with the new token
      setToken(r.token);
      setCurrent("");
      setNext("");
      setAgain("");
      setTried(false);
      toast({ tone: "good", text: "Password changed." });
      const first = me.must_change_password;
      await qc.invalidateQueries({ queryKey: ["me"] });
      if (first) navigate("/", { replace: true });
    },
  });

  const nextProblem = tried ? problem(next) : null;
  const againProblem = tried && again !== next ? "The two passwords are not the same." : null;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setTried(true);
    if (problem(next) || again !== next || !current) return;
    change.mutate();
  };

  return (
    <>
      <PageHeader title="Your account" description="Your details and your password." />
      {me.must_change_password && (
        <Notice tone="warn" title="Choose your own password to continue" className="mb-6 max-w-2xl">
          You signed in with a password someone else set. Choose a new one that only you know.
        </Notice>
      )}
      <div className="grid grid-cols-1 max-w-4xl gap-8 lg:grid-cols-[1fr_1.2fr]">
        <Section title="Details">
          <Facts
            items={[
              { label: "Name", value: me.name },
              { label: "Email address", value: me.email },
              { label: "Role", value: me.is_owner ? `${me.role_label} (owner)` : me.role_label },
              { label: "Gets new leads", value: me.takes_new_leads ? "Yes" : "No" },
              { label: "Last sign-in", value: dateTime(me.last_login_at, "Now") },
            ]}
          />
        </Section>
        <Section title="Change your password" description="At least 8 characters, with letters and a digit.">
          {me.env_password ? (
            <Notice tone="info">
              The owner account&apos;s password is set by CRM_OWNER_PASSWORD in backend/.env. Change it there and
              restart the backend.
            </Notice>
          ) : (
            <Panel>
              <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
                {change.isError && <Notice tone="bad">{errorText(change.error)}</Notice>}
                <Field label="Current password">
                  <Input
                    type="password"
                    autoComplete="current-password"
                    value={current}
                    onChange={(e) => setCurrent(e.target.value)}
                  />
                </Field>
                <Field label="New password" error={nextProblem}>
                  <Input
                    type="password"
                    autoComplete="new-password"
                    value={next}
                    onChange={(e) => setNext(e.target.value)}
                  />
                </Field>
                <Field label="New password again" error={againProblem}>
                  <Input
                    type="password"
                    autoComplete="new-password"
                    value={again}
                    onChange={(e) => setAgain(e.target.value)}
                  />
                </Field>
                <div>
                  <Button
                    type="submit"
                    variant="primary"
                    loading={change.isPending}
                    disabled={!current || !next || !again}
                  >
                    Change password
                  </Button>
                </div>
              </form>
            </Panel>
          )}
        </Section>

        <Section title="Sign out" description="End your current CRM session on this device.">
          <Panel>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-[13.5px] font-medium text-ink">Signed in as {me.name}</p>
                <p className="text-[12.5px] text-muted">
                  {me.email} ({me.role})
                </p>
              </div>
              <Button type="button" variant="secondary" onClick={signOut}>
                <LogOut className="mr-1.5 size-4" />
                Sign out
              </Button>
            </div>
          </Panel>
        </Section>
      </div>
    </>
  );
}
