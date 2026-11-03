import { useMutation } from "@tanstack/react-query";
import { errorText } from "@xedu/shared/lib";
import { Button, Dialog, Field, Input, Notice, Select } from "@xedu/shared/ui";
import { useState } from "react";
import { Link, useLocation } from "react-router";
import { api } from "../api/client";
import { useSession } from "../app/session";

const TIMES = ["Any time", "Morning (9 to 12)", "Afternoon (12 to 5)", "Evening (5 to 8)"];

/** Phone number and a good time; a counsellor calls back. Asking for a call is consent to be called on that number. */
export function CallbackForm({
  courseSlug,
  onDone,
  compact,
}: {
  courseSlug?: string | null;
  onDone?: (message: string) => void;
  compact?: boolean;
}) {
  const { me } = useSession();
  const location = useLocation();
  const [phone, setPhone] = useState(me?.profile?.phone ?? "");
  const [time, setTime] = useState(TIMES[0]);
  const [note, setNote] = useState("");
  const send = useMutation({
    mutationFn: () =>
      api.post<{ message: string }>("/callback", {
        phone,
        preferred_time: time,
        note,
        course_slug: courseSlug ?? null,
      }),
    onSuccess: (r) => onDone?.(r.message),
  });
  if (!me) {
    return (
      <p className="text-[14px] text-ink-2">
        <Link to="/login" state={{ from: location.pathname }} className="font-medium text-brand-ink hover:underline">
          Sign in
        </Link>{" "}
        or{" "}
        <Link to="/signup" className="font-medium text-brand-ink hover:underline">
          create a free account
        </Link>{" "}
        and a counsellor can call you.
      </p>
    );
  }
  if (send.isSuccess) return <Notice tone="good">{send.data.message}</Notice>;
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (phone.trim()) send.mutate();
      }}
    >
      {send.isError && <Notice tone="bad">{errorText(send.error)}</Notice>}
      <Field label="Phone number">
        <Input
          type="tel"
          autoComplete="tel"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          placeholder="+91 98765 43210"
          required
        />
      </Field>
      <Field label="A good time">
        <Select
          value={time}
          onChange={(e) => setTime(e.target.value)}
          options={TIMES.map((t) => ({ value: t, label: t }))}
        />
      </Field>
      {!compact && (
        <Field label="What would you like to talk about?" optional>
          <Input value={note} onChange={(e) => setNote(e.target.value)} maxLength={300} />
        </Field>
      )}
      <Button type="submit" variant="primary" loading={send.isPending} disabled={!phone.trim()}>
        Ask for a call
      </Button>
      <p className="text-[12.5px] text-muted">We use this number only to call you about courses.</p>
    </form>
  );
}

export function CallbackDialog({
  courseSlug,
  courseTitle,
  onClose,
}: {
  courseSlug?: string | null;
  courseTitle?: string;
  onClose: () => void;
}) {
  const [done, setDone] = useState<string | null>(null);
  return (
    <Dialog
      open
      size="sm"
      onClose={onClose}
      title="Talk to a counsellor"
      description={
        courseTitle
          ? `About ${courseTitle}: fees, schedule, whether it fits you.`
          : "About fees, schedules and which course fits you."
      }
      footer={done ? <Button onClick={onClose}>Close</Button> : undefined}
    >
      {done ? <Notice tone="good">{done}</Notice> : <CallbackForm courseSlug={courseSlug} onDone={setDone} />}
    </Dialog>
  );
}
