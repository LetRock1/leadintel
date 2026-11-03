import { errorText } from "@xedu/shared/lib";
import { Button, Field, Input, Notice, ThemeToggle } from "@xedu/shared/ui";
import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";
import { useSession } from "../app/session";

export default function Login() {
  const { me, signIn } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (me) return <Navigate to={me.must_change_password ? "/account" : from} replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const m = await signIn(email.trim(), password);
      navigate(m.must_change_password ? "/account" : from, { replace: true });
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col">
      <div className="flex justify-end p-4">
        <ThemeToggle />
      </div>
      <main className="flex flex-1 items-start justify-center px-4 pb-24 pt-[8vh]">
        <div className="w-full max-w-[400px]">
          <div className="mb-8 flex items-center gap-3">
            <svg aria-hidden viewBox="0 0 32 32" className="size-9">
              <rect width="32" height="32" rx="7" fill="var(--xe-brand)" />
              <path d="M9 9l14 14M23 9L9 23" stroke="#fff" strokeWidth="3.2" strokeLinecap="round" />
            </svg>
            <div className="leading-tight">
              <p className="text-[16px] font-semibold text-ink">X Education</p>
              <p className="text-[13px] text-muted">Admissions CRM</p>
            </div>
          </div>
          <h1 className="text-[22px] font-semibold text-ink">Sign in</h1>
          <p className="mt-1 text-[14px] text-muted">Use the work account an admin created for you.</p>
          <form onSubmit={submit} className="mt-6 flex flex-col gap-4" noValidate>
            {error && <Notice tone="bad">{error}</Notice>}
            <Field label="Email address">
              <Input
                type="email"
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoFocus
              />
            </Field>
            <Field label="Password">
              <Input
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </Field>
            <Button type="submit" variant="primary" size="lg" loading={busy} disabled={!email || !password}>
              Sign in
            </Button>
          </form>
          <div className="mt-8 border-t border-line pt-5 text-[13px] text-muted">
            <p>Forgotten your password? An admin can set a new one for you on the Team page.</p>
            <p className="mt-2">
              First start: the start window shows the owner account&apos;s address and first password (also in
              backend/data/initial-admin-password.txt). You choose your own after signing in.
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}
