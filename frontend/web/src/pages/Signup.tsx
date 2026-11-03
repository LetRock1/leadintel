import { useMutation } from "@tanstack/react-query";
import { errorText } from "@xedu/shared/lib";
import { Button, Field, Input, Notice } from "@xedu/shared/ui";
import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router";
import { api } from "../api/client";
import { useSession } from "../app/session";
import { AuthFrame } from "../components/AuthFrame";
import { EMAIL_RE, passwordProblem } from "../lib/password";

export default function Signup() {
  const { me } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from;
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [tried, setTried] = useState(false);
  const signup = useMutation({
    mutationFn: () =>
      api.post<{ message: string }>("/auth/signup", { name: name.trim(), email: email.trim(), password }),
    onSuccess: (r) =>
      navigate(`/verify?email=${encodeURIComponent(email.trim().toLowerCase())}`, {
        state: { message: r.message, from },
      }),
  });
  if (me) return <Navigate to="/my-learning" replace />;

  const nameError = tried && !name.trim() ? "Enter your name." : null;
  const emailError = tried && !EMAIL_RE.test(email.trim()) ? "Enter an email address like name@example.com." : null;
  const pwError = tried ? passwordProblem(password) : null;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setTried(true);
    if (name.trim() && EMAIL_RE.test(email.trim()) && !passwordProblem(password)) signup.mutate();
  };

  return (
    <AuthFrame
      title="Create your free account"
      description="Save courses, ask questions, book a call with a counsellor, and enrol when you are ready."
      footer={
        <>
          Already have an account?{" "}
          <Link to="/login" state={{ from }} className="font-medium text-brand-ink hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        {signup.isError && <Notice tone="bad">{errorText(signup.error)}</Notice>}
        <Field label="Your name" error={nameError}>
          <Input autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} maxLength={80} autoFocus />
        </Field>
        <Field label="Email address" error={emailError} hint="We send a 6-digit code to check it is yours.">
          <Input
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            maxLength={120}
          />
        </Field>
        <Field label="Password" error={pwError} hint="At least 8 characters. A short sentence is easy to remember.">
          <Input
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            maxLength={128}
          />
        </Field>
        <Button type="submit" variant="primary" size="lg" loading={signup.isPending}>
          Create the account
        </Button>
        <p className="text-[13px] text-muted">
          By creating an account you agree that we record the pages you visit while signed in, to suggest courses. You
          can delete the account and everything about you at any time. See{" "}
          <Link to="/privacy" className="text-brand-ink hover:underline">
            Privacy
          </Link>
          .
        </p>
      </form>
    </AuthFrame>
  );
}
