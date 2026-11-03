import { useMutation } from "@tanstack/react-query";
import { errorText } from "@xedu/shared/lib";
import { Button, Field, Input, Notice, useToast } from "@xedu/shared/ui";
import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router";
import { api } from "../api/client";
import type { SignInResponse } from "../api/types";
import { useSession } from "../app/session";
import { AuthFrame } from "../components/AuthFrame";

export default function Verify() {
  const { adopt } = useSession();
  const toast = useToast();
  const navigate = useNavigate();
  const location = useLocation();
  const [params] = useSearchParams();
  const state = location.state as { message?: string; from?: string } | null;
  const [email, setEmail] = useState(params.get("email") ?? "");
  const [code, setCode] = useState("");
  const verify = useMutation({
    mutationFn: () => api.post<SignInResponse>("/auth/verify-otp", { email: email.trim(), otp: code.trim() }),
    onSuccess: async (r) => {
      await adopt(r);
      toast({ tone: "good", text: r.message ?? "Email verified." });
      navigate(r.profile_complete ? (state?.from ?? "/my-learning") : "/welcome", {
        replace: true,
        state: { from: state?.from },
      });
    },
  });
  const resend = useMutation({
    mutationFn: () => api.post<{ message: string }>("/auth/resend-otp", { email: email.trim() }),
    onSuccess: (r) => toast({ tone: "info", text: r.message }),
    onError: (e) => toast({ tone: "bad", text: errorText(e) }),
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (email.trim() && code.trim().length >= 4) verify.mutate();
  };
  return (
    <AuthFrame
      title="Check your email"
      description={
        email ? `Enter the 6-digit code we sent to ${email}.` : "Enter your email address and the 6-digit code we sent."
      }
      footer={
        <>
          No code after a minute? Look in the spam folder, or{" "}
          <button
            type="button"
            className="font-medium text-brand-ink hover:underline disabled:opacity-50"
            disabled={!email || resend.isPending}
            onClick={() => resend.mutate()}
          >
            send a new code
          </button>
          . Wrong address?{" "}
          <Link to="/signup" className="font-medium text-brand-ink hover:underline">
            Start again
          </Link>
          .
        </>
      }
    >
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        {state?.message && !verify.isError && <Notice tone="info">{state.message}</Notice>}
        {verify.isError && <Notice tone="bad">{errorText(verify.error)}</Notice>}
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
            className="num h-12 text-center text-[22px] tracking-[0.4em]"
            autoFocus
          />
        </Field>
        <Button
          type="submit"
          variant="primary"
          size="lg"
          loading={verify.isPending}
          disabled={code.length < 6 || !email}
        >
          Verify and continue
        </Button>
      </form>
    </AuthFrame>
  );
}
