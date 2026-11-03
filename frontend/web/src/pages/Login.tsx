import { ApiError, errorText } from "@xedu/shared/lib";
import { Button, Field, Input, Notice } from "@xedu/shared/ui";
import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router";
import { useSession } from "../app/session";
import { AuthFrame } from "../components/AuthFrame";

export default function Login() {
  const { me, signIn } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from;
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  if (me) return <Navigate to={from ?? "/my-learning"} replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const r = await signIn(email.trim(), password);
      navigate(r.profile_complete ? (from ?? "/my-learning") : "/welcome", { replace: true, state: { from } });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  const unverified = error instanceof ApiError && error.status === 403;

  return (
    <AuthFrame
      title="Sign in"
      footer={
        <>
          New here?{" "}
          <Link to="/signup" state={{ from }} className="font-medium text-brand-ink hover:underline">
            Create a free account
          </Link>
        </>
      }
    >
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        {Boolean(error) && (
          <Notice tone="bad">
            {errorText(error)}{" "}
            {unverified && (
              <Link to={`/verify?email=${encodeURIComponent(email.trim())}`} className="font-medium underline">
                Enter the code
              </Link>
            )}
          </Notice>
        )}
        <Field label="Email address">
          <Input
            type="email"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoFocus
          />
        </Field>
        <Field label="Password">
          <Input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>
        <Button type="submit" variant="primary" size="lg" loading={busy} disabled={!email || !password}>
          Sign in
        </Button>
        <Link to="/forgot-password" className="text-[14px] font-medium text-brand-ink hover:underline">
          Forgotten your password?
        </Link>
      </form>
    </AuthFrame>
  );
}
