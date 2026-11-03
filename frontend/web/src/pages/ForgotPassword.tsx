import { useMutation } from "@tanstack/react-query";
import { errorText } from "@xedu/shared/lib";
import { Button, Field, Input, Notice } from "@xedu/shared/ui";
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router";
import { api } from "../api/client";
import { AuthFrame } from "../components/AuthFrame";
import { EMAIL_RE } from "../lib/password";

export default function ForgotPassword() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const send = useMutation({
    mutationFn: () => api.post<{ message: string }>("/auth/forgot-password", { email: email.trim() }),
    onSuccess: (r) =>
      navigate(`/reset-password?email=${encodeURIComponent(email.trim().toLowerCase())}`, {
        state: { message: r.message },
      }),
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (EMAIL_RE.test(email.trim())) send.mutate();
  };
  return (
    <AuthFrame
      title="Reset your password"
      description="Enter the email address of your account. We send a code to set a new password."
      footer={
        <Link to="/login" className="font-medium text-brand-ink hover:underline">
          Back to sign in
        </Link>
      }
    >
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        {send.isError && <Notice tone="bad">{errorText(send.error)}</Notice>}
        <Field label="Email address">
          <Input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />
        </Field>
        <Button
          type="submit"
          variant="primary"
          size="lg"
          loading={send.isPending}
          disabled={!EMAIL_RE.test(email.trim())}
        >
          Send the code
        </Button>
      </form>
    </AuthFrame>
  );
}
