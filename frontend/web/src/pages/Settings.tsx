import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { errorText } from "@xedu/shared/lib";
import { Button, Dialog, Field, Input, Notice, Select, Switch, useToast } from "@xedu/shared/ui";
import { useState, type ReactNode } from "react";
import { api, setToken } from "../api/client";
import { useMe, useSignOutHome } from "../app/session";
import { passwordProblem } from "../lib/password";
import { OCCUPATION_LABEL, type ProfileOptions } from "../lib/profile";

function Block({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  return (
    <section className="grid grid-cols-1 gap-4 border-t border-line py-8 md:grid-cols-[16rem_minmax(0,1fr)]">
      <div>
        <h2 className="text-[18px] font-semibold text-ink">{title}</h2>
        {description && <p className="mt-1 text-[14px] text-muted">{description}</p>}
      </div>
      <div className="max-w-lg">{children}</div>
    </section>
  );
}

function ProfileForm() {
  const me = useMe();
  const qc = useQueryClient();
  const toast = useToast();
  const p = me.profile;
  const options = useQuery({
    queryKey: ["profile-options"],
    queryFn: () => api.get<ProfileOptions>("/profile/options"),
    staleTime: Infinity,
  });
  const clean = (v: string | null | undefined) => (v && v !== "Unknown" ? v : "");
  const [occupation, setOccupation] = useState(clean(p?.current_occupation));
  const [field, setField] = useState(clean(p?.specialization));
  const [city, setCity] = useState(clean(p?.city));
  const [age, setAge] = useState(clean(p?.age_bracket));
  const save = useMutation({
    mutationFn: () =>
      api.post<{ message: string }>("/profile/complete", {
        current_occupation: occupation,
        specialization: field,
        age_bracket: age || null,
        city: city.trim() || "Unknown",
        phone: null,
        how_did_you_hear: p?.how_did_you_hear ?? "Unknown",
      }),
    onSuccess: (r) => {
      toast({ tone: "good", text: r.message });
      void qc.invalidateQueries({ queryKey: ["me"] });
      void qc.invalidateQueries({ queryKey: ["recommendations"] });
    },
    onError: (e) => toast({ tone: "bad", text: errorText(e) }),
  });
  const o = options.data;
  return (
    <div className="flex flex-col gap-4">
      <Field label="What you do now">
        <Select
          value={occupation}
          onChange={(e) => setOccupation(e.target.value)}
          options={[
            { value: "", label: "Choose one" },
            ...(o?.occupations ?? []).map((v) => ({ value: v, label: OCCUPATION_LABEL[v] ?? v })),
          ]}
        />
      </Field>
      <Field label="Your field">
        <Select
          value={field}
          onChange={(e) => setField(e.target.value)}
          options={[
            { value: "", label: "Choose one" },
            ...(o?.specializations ?? []).map((v) => ({ value: v, label: v })),
          ]}
        />
      </Field>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Age" optional>
          <Select
            value={age}
            onChange={(e) => setAge(e.target.value)}
            options={[
              { value: "", label: "Rather not say" },
              ...(o?.age_brackets ?? []).map((v) => ({ value: v, label: v })),
            ]}
          />
        </Field>
        <Field label="City" optional>
          <Input value={city} onChange={(e) => setCity(e.target.value)} maxLength={60} />
        </Field>
      </div>
      <div>
        <Button
          variant="primary"
          loading={save.isPending}
          disabled={!occupation || !field}
          onClick={() => save.mutate()}
        >
          Save the profile
        </Button>
      </div>
    </div>
  );
}

function Preferences() {
  const me = useMe();
  const qc = useQueryClient();
  const toast = useToast();
  const p = me.profile;
  const [phone, setPhone] = useState(p?.phone ?? "");
  const update = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.put<{ message: string }>("/profile/preferences", body),
    onSuccess: (r) => {
      toast({ tone: "good", text: r.message });
      void qc.invalidateQueries({ queryKey: ["me"] });
    },
    onError: (e) => toast({ tone: "bad", text: errorText(e) }),
  });
  return (
    <div className="flex flex-col gap-5">
      <Switch
        checked={p?.do_not_email !== "Yes"}
        onChange={(v) => update.mutate({ do_not_email: !v })}
        disabled={update.isPending}
        label="Emails about courses"
        description="Course news, reminders and offers. Account emails (codes, receipts) are always sent."
      />
      <Switch
        checked={p?.do_not_call !== "Yes"}
        onChange={(v) => update.mutate({ do_not_call: !v })}
        disabled={update.isPending}
        label="Calls from a counsellor"
        description="Only when you have given a phone number."
      />
      <Switch
        checked={Boolean(p?.whatsapp_opt_in)}
        onChange={(v) => update.mutate({ whatsapp_opt_in: v })}
        disabled={update.isPending || !p?.phone}
        label="WhatsApp messages"
        description={p?.phone ? "Short messages about the courses you looked at." : "Add a phone number first."}
      />
      <form
        className="flex items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          update.mutate({ phone: phone.trim() });
        }}
      >
        <Field label="Phone" className="flex-1">
          <Input
            type="tel"
            autoComplete="tel"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            placeholder="+91 98765 43210"
            maxLength={20}
          />
        </Field>
        <Button type="submit" disabled={phone.trim() === (p?.phone ?? "")}>
          Save
        </Button>
      </form>
    </div>
  );
}

function PasswordForm() {
  const toast = useToast();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const change = useMutation({
    mutationFn: () =>
      api.post<{ message: string; token: string }>("/auth/change-password", {
        current_password: current,
        new_password: next,
      }),
    onSuccess: (r) => {
      // a new password signs out every other session; this one goes on with the new token
      setToken(r.token);
      toast({ tone: "good", text: r.message });
      setCurrent("");
      setNext("");
    },
  });
  const problem = next ? passwordProblem(next) : null;
  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (current && !passwordProblem(next)) change.mutate();
      }}
    >
      {change.isError && <Notice tone="bad">{errorText(change.error)}</Notice>}
      <Field label="Current password">
        <Input
          type="password"
          autoComplete="current-password"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
        />
      </Field>
      <Field label="New password" error={problem} hint="At least 8 characters. A short sentence is easy to remember.">
        <Input type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} />
      </Field>
      <div>
        <Button type="submit" loading={change.isPending} disabled={!current || !next || Boolean(problem)}>
          Change the password
        </Button>
      </div>
    </form>
  );
}

interface Insights {
  lead_score: number;
  tier: string;
  probability: number;
  factors: { factor: string; detail: string; impact: string; points: number }[];
}

function YourData() {
  const [show, setShow] = useState(false);
  const insights = useQuery({
    queryKey: ["insights"],
    queryFn: () => api.get<Insights>("/me/insights"),
    enabled: show,
  });
  return (
    <div>
      <p className="text-[14.5px] text-ink-2">
        While you are signed in we record the pages you open, how long you stay, and what you add to your cart or
        wishlist. From that, a model works out how interested you seem, which decides the suggestions and follow-ups you
        get.
      </p>
      {!show ? (
        <Button className="mt-4" onClick={() => setShow(true)}>
          Show what the model sees now
        </Button>
      ) : insights.isPending ? (
        <p className="mt-4 text-[14px] text-muted">Working it out</p>
      ) : insights.isError ? (
        <p className="mt-4 text-[14px] text-muted">{errorText(insights.error)}</p>
      ) : (
        <div className="mt-4 rounded-md border border-line bg-surface p-4">
          <p className="text-[14.5px] text-ink">
            Interest score <span className="num font-semibold">{Math.round(insights.data.lead_score)}</span> out of 100.
          </p>
          <ul className="mt-2 flex flex-col gap-1 text-[13.5px] text-ink-2">
            {insights.data.factors.slice(0, 6).map((f) => (
              <li key={f.factor} className="flex gap-3">
                <span className="flex-1">
                  {f.factor} <span className="text-muted">({f.detail})</span>
                </span>
                <span className="num">{f.impact}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function DeleteAccount() {
  const signOutHome = useSignOutHome();
  const [open, setOpen] = useState(false);
  const [confirm, setConfirm] = useState("");
  const remove = useMutation({
    mutationFn: () => api.del("/me"),
    onSuccess: () => signOutHome("Your account and everything linked to it are deleted."),
  });
  return (
    <>
      <p className="text-[14.5px] text-ink-2">
        Deletes your account and everything linked to it: visits, emails, enrolments, notes. This cannot be undone.
      </p>
      <Button variant="danger" className="mt-4" onClick={() => setOpen(true)}>
        Delete my account
      </Button>
      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        size="sm"
        title="Delete your account?"
        description="Everything about you is removed from X Education. Type DELETE to confirm."
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Keep my account</Button>
            <Button
              variant="danger"
              loading={remove.isPending}
              disabled={confirm !== "DELETE"}
              onClick={() => remove.mutate()}
            >
              Delete everything
            </Button>
          </>
        }
      >
        {remove.isError && <Notice tone="bad">{errorText(remove.error)}</Notice>}
        <Field label="Confirmation">
          <Input value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="off" />
        </Field>
      </Dialog>
    </>
  );
}

export default function Settings() {
  const me = useMe();
  return (
    <div className="mx-auto max-w-[1000px] px-5 pb-10 pt-12 sm:px-8">
      <h1 className="text-[34px] font-semibold leading-tight text-ink">Settings</h1>
      <p className="mt-2 text-[15px] text-ink-2">
        Signed in as {me.user.name}, {me.user.email}.
      </p>
      <div className="mt-8">
        <Block title="Profile" description="Used to suggest courses that fit you.">
          <ProfileForm />
        </Block>
        <Block
          title="How we may contact you"
          description="Your choice is followed straight away, including by the CRM's automatic follow-ups."
        >
          <Preferences />
        </Block>
        <Block title="Password">
          <PasswordForm />
        </Block>
        <Block title="Your data" description="What we record, and what it is used for.">
          <YourData />
        </Block>
        <Block title="Delete your account">
          <DeleteAccount />
        </Block>
      </div>
    </div>
  );
}
