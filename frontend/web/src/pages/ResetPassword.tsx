import { useMutation } from "@tanstack/react-query";
import { errorText } from "@xedu/shared/lib";
import { Button, Field, Input, Notice, useToast } from "@xedu/shared/ui";
import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router";
import { api } from "../api/client";
import { AuthFrame } from "../components/AuthFrame";
import { passwordProblem } from "../lib/password";

export default function ResetPassword() {
  const [params] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const toast = useToast();
  const message = (location.state as { message?: string } | null)?.message;
  const [email, setEmail] = useState(params.get("email") ?? "");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [tried, setTried] = useState(false);
  const reset = useMutation({
    mutationFn: () =>
      api.post<{ message: string }>("/auth/reset-password", {
        email: email.trim(),
        otp: code.trim(),
        new_password: password,
      }),
    onSuccess: (r) => {
      toast({ tone: "good", text: r.message });
      navigate("/login", { replace: true });
    },
  });
  const pwError = tried ? passwordProblem(password) : null;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setTried(true);
    if (email && code.length === 6 && !passwordProblem(password)) reset.mutate();
  };
  return (
    <AuthFrame
      title="Choose a new password"
      description="Enter the 6-digit code from the email and a new password."
      footer={
        <Link to="/forgot-password" className="font-medium text-brand-ink hover:underline">
          Send a new code
        </Link>
      }
    >
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        {message && !reset.isError && <Notice tone="info">{message}</Notice>}
        {reset.isError && <Notice tone="bad">{errorText(reset.error)}</Notice>}
        {!params.get("email") && (
          <Field label="Email address">
            <Input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
        )}
        <Field label="Code">
          <Input
            inputMode="numeric"
            autoComplete="one-time-code"
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
            className="num text-center text-[18px] tracking-[0.3em]"
            autoFocus
          />
        </Field>
        <Field label="New password" error={pwError} hint="At least 8 characters. A short sentence is easy to remember.">
          <Input
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>
        <Button
          type="submit"
          variant="primary"
          size="lg"
          loading={reset.isPending}
          disabled={code.length < 6 || !password}
        >
          Set the new password
        </Button>
      </form>
    </AuthFrame>
  );
}
