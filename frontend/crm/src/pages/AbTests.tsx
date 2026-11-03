import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { dateTime, errorText, int, pct, plural, pointsPlain } from "@xedu/shared/lib";
import {
  Badge,
  Button,
  Dialog,
  EmptyState,
  Field,
  IconButton,
  Input,
  Notice,
  Segmented,
  Select,
  Table,
  Td,
  Textarea,
  Th,
  useToast,
} from "@xedu/shared/ui";
import { FlaskConical, Plus, X } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { api } from "../api/client";
import type { AbPlan, AbTest, AbTestsResponse, Adoption } from "../api/types";
import { VerdictBadge } from "../components/ab";
import { useSession } from "../app/session";
import { SimulatedTag } from "../components/lead-bits";
import { PageHeader, Section } from "../components/page";
import { Loading, LoadError, QueryView } from "../components/state";

interface DraftVariant {
  label: string;
  subject: string;
  body: string;
  offer_pct: number;
}

const KEYS = ["A", "B", "C"];

function NewTest({
  audiences,
  settings,
  onClose,
}: {
  audiences: string[];
  settings: AbTestsResponse["settings"];
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [tier, setTier] = useState(audiences[0] ?? "All leads");
  const [metric, setMetric] = useState<"purchase" | "click">("purchase");
  const [hypothesis, setHypothesis] = useState("");
  const [variants, setVariants] = useState<DraftVariant[]>([
    { label: "", subject: "", body: "Hi {first_name},\n\n", offer_pct: 0 },
    { label: "", subject: "", body: "Hi {first_name},\n\n", offer_pct: 0 },
  ]);
  const controlShare = metric === "purchase" ? settings.control_share : 0;
  const plan = useQuery({
    queryKey: ["ab-plan", tier, metric, variants.length],
    queryFn: () =>
      api.get<AbPlan>("/ab-tests/plan", { tier, metric, variants: variants.length, control_share: controlShare }),
  });
  const create = useMutation({
    mutationFn: () =>
      api.post<{ id: number; message: string; warning: string | null }>("/ab-tests", {
        name,
        tier,
        hypothesis,
        metric,
        control_share: controlShare,
        variants: variants.map((v, i) => ({ ...v, label: v.label || `Variant ${KEYS[i]}` })),
      }),
    onSuccess: (r) => {
      void qc.invalidateQueries({ queryKey: ["ab-tests"] });
      navigate(`/ab-tests/${r.id}`);
    },
  });
  const update = (i: number, patch: Partial<DraftVariant>) =>
    setVariants((vs) => vs.map((v, j) => (j === i ? { ...v, ...patch } : v)));
  const ready = name.trim() && variants.every((v) => v.subject.trim() && v.body.trim());
  return (
    <Dialog
      open
      size="lg"
      onClose={onClose}
      title="New A/B test"
      description="Each person in the audience is given one variant at random. It is saved as a draft: you send it from its page."
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={create.isPending} disabled={!ready} onClick={() => create.mutate()}>
            Save the draft
          </Button>
        </>
      }
    >
      <div className="grid gap-4">
        {create.isError && <Notice tone="bad">{errorText(create.error)}</Notice>}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Name">
            <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={200} />
          </Field>
          <Field label="Audience">
            <Select
              value={tier}
              onChange={(e) => setTier(e.target.value)}
              options={audiences.map((a) => ({ value: a, label: a }))}
            />
          </Field>
        </div>
        <div>
          <p className="mb-1.5 text-[13px] font-medium text-ink">What counts as a success</p>
          <Segmented
            label="Success measure"
            value={metric}
            onChange={setMetric}
            options={[
              { value: "purchase", label: "Buying a course" },
              { value: "click", label: "Clicking the email" },
            ]}
          />
          <p className="mt-1.5 text-[12.5px] text-muted">
            {metric === "purchase"
              ? `${pct(controlShare)} of the audience get no email (the control group), so each variant is compared with sending nothing.`
              : "Everyone gets a variant; the variants are compared with each other."}
          </p>
        </div>
        <Field label="What you expect, and why" optional>
          <Textarea rows={2} value={hypothesis} onChange={(e) => setHypothesis(e.target.value)} maxLength={2000} />
        </Field>
        {variants.map((v, i) => (
          <fieldset key={i} className="rounded-md border border-line p-3">
            <legend className="px-1 text-[13px] font-semibold text-ink">Variant {KEYS[i]}</legend>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_10rem]">
              <Field label="Short name" optional>
                <Input
                  value={v.label}
                  onChange={(e) => update(i, { label: e.target.value })}
                  placeholder={`Variant ${KEYS[i]}`}
                  maxLength={120}
                />
              </Field>
              <Field label="Coupon">
                <Select
                  value={String(v.offer_pct)}
                  onChange={(e) => update(i, { offer_pct: Number(e.target.value) })}
                  options={[0, 10, 15, 20].map((n) => ({ value: String(n), label: n ? `${n}% off` : "No coupon" }))}
                />
              </Field>
            </div>
            <Field label="Subject" className="mt-3">
              <Input value={v.subject} onChange={(e) => update(i, { subject: e.target.value })} maxLength={300} />
            </Field>
            <Field label="Message" className="mt-3">
              <Textarea rows={4} value={v.body} onChange={(e) => update(i, { body: e.target.value })} />
            </Field>
            {variants.length > 2 && (
              <div className="mt-2 flex justify-end">
                <IconButton
                  label={`Remove variant ${KEYS[i]}`}
                  size="sm"
                  onClick={() => setVariants((vs) => vs.filter((_, j) => j !== i))}
                >
                  <X aria-hidden className="size-4" />
                </IconButton>
              </div>
            )}
          </fieldset>
        ))}
        {variants.length < Math.min(3, settings.max_variants) && (
          <div>
            <Button
              size="sm"
              icon={<Plus aria-hidden className="size-4" />}
              onClick={() =>
                setVariants((vs) => [...vs, { label: "", subject: "", body: "Hi {first_name},\n\n", offer_pct: 0 }])
              }
            >
              Add a variant
            </Button>
          </div>
        )}
        {plan.data && (
          <Notice
            tone={plan.data.enough ? "info" : "warn"}
            title={plan.data.enough ? "The audience is big enough" : "The audience is small for this test"}
          >
            To notice a difference of {pointsPlain(plan.data.mde)}, each variant needs about{" "}
            {int(plan.data.planned_per_arm)} people; this audience gives about {int(plan.data.per_arm_available)} each.
            {!plan.data.enough && plan.data.detectable_lift
              ? ` With that many, only a difference of ${pointsPlain(plan.data.detectable_lift)} or more would show.`
              : ""}
          </Notice>
        )}
      </div>
    </Dialog>
  );
}

function Adoptions() {
  const qc = useQueryClient();
  const toast = useToast();
  const { can } = useSession();
  const list = useQuery({
    queryKey: ["adoptions"],
    queryFn: () => api.get<{ adoptions: Adoption[]; auto_adopt: boolean; check_share: number }>("/adoptions"),
    refetchInterval: 60_000,
  });
  const revert = useMutation({
    mutationFn: (id: number) => api.post(`/adoptions/${id}/revert`),
    onSuccess: () => {
      toast({ tone: "good", text: "Switched back to the old standard email." });
      void qc.invalidateQueries({ queryKey: ["adoptions"] });
    },
    onError: (e) => toast({ tone: "bad", text: errorText(e) }),
  });
  return (
    <QueryView query={list} what="the adopted emails">
      {(d) =>
        d.adoptions.length === 0 ? (
          <p className="text-[13.5px] text-muted">
            None yet.{" "}
            {d.auto_adopt
              ? "When a content test ends with a clear winner, the CRM uses it as the standard email by itself."
              : ""}
          </p>
        ) : (
          <Table label="Adopted emails">
            <thead>
              <tr>
                <Th>Email</Th>
                <Th>From the test</Th>
                <Th>Status</Th>
                <Th>Check</Th>
                {can("marketing") && <Th aria-label="Actions" />}
              </tr>
            </thead>
            <tbody>
              {d.adoptions.map((a) => (
                <tr key={a.id}>
                  <Td className="max-w-72">
                    <span className="font-medium text-ink">{a.variant_label}</span>
                    <p className="truncate text-[12.5px] text-muted">{a.subject}</p>
                  </Td>
                  <Td className="text-ink-2">
                    {a.test_name} {a.simulated && <SimulatedTag className="ml-1" />}
                  </Td>
                  <Td>
                    <Badge tone={a.status === "confirmed" ? "good" : a.status === "reverted" ? "neutral" : "info"}>
                      {a.status === "confirmed"
                        ? "Confirmed"
                        : a.status === "reverted"
                          ? "Switched back"
                          : "In use, being checked"}
                    </Badge>
                  </Td>
                  <Td className="max-w-80 text-[12.5px] text-muted">
                    {a.reason ??
                      `${pct(a.check_share)} of the audience still get the old email, to check the winner keeps winning.`}
                  </Td>
                  {can("marketing") && (
                    <Td>
                      {a.status === "active" && (
                        <Button
                          size="sm"
                          variant="ghost"
                          loading={revert.isPending && revert.variables === a.id}
                          onClick={() => revert.mutate(a.id)}
                        >
                          Switch back
                        </Button>
                      )}
                    </Td>
                  )}
                </tr>
              ))}
            </tbody>
          </Table>
        )
      }
    </QueryView>
  );
}

export default function AbTests() {
  const { can } = useSession();
  const [creating, setCreating] = useState(false);
  const tests = useQuery({
    queryKey: ["ab-tests"],
    queryFn: () => api.get<AbTestsResponse>("/ab-tests"),
    refetchInterval: 30_000,
  });
  const audiences = useQuery({
    queryKey: ["campaigns"],
    queryFn: () => api.get<{ audiences: string[] }>("/campaigns"),
    select: (d) => d.audiences,
  });
  return (
    <>
      <PageHeader
        title="A/B tests"
        description="Compare two or three emails on a random split of an audience. Results come with a 95% interval and are corrected when several variants are compared."
        actions={
          can("marketing") ? (
            <Button
              variant="primary"
              icon={<Plus aria-hidden className="size-4" />}
              disabled={!tests.data || !audiences.data}
              onClick={() => setCreating(true)}
            >
              New A/B test
            </Button>
          ) : undefined
        }
      />
      {tests.isPending ? (
        <Loading label="Loading the tests" />
      ) : tests.isError ? (
        <LoadError error={tests.error} what="the tests" retry={() => void tests.refetch()} />
      ) : tests.data.ab_tests.length === 0 ? (
        <div className="rounded-md border border-line bg-surface px-4">
          <EmptyState icon={FlaskConical} title="No A/B tests yet">
            Test a new subject line, a coupon or a different message on part of an audience before sending it to
            everyone.
          </EmptyState>
        </div>
      ) : (
        <Table label="A/B tests">
          <thead>
            <tr>
              <Th>Test</Th>
              <Th>Audience</Th>
              <Th>Measures</Th>
              <Th className="text-right">People</Th>
              <Th>Started</Th>
              <Th>Verdict</Th>
            </tr>
          </thead>
          <tbody>
            {tests.data.ab_tests.map((t: AbTest) => (
              <tr key={t.id} className="hover:bg-sunken/60">
                <Td className="max-w-96">
                  <div className="flex flex-wrap items-center gap-2">
                    <Link
                      to={`/ab-tests/${t.id}`}
                      className="font-medium text-ink hover:text-brand-ink hover:underline"
                    >
                      {t.name}
                    </Link>
                    {t.simulated && <SimulatedTag />}
                  </div>
                  <p className="truncate text-[12.5px] text-muted">
                    {t.variants.map((v) => v.label).join(" against ")}
                  </p>
                </Td>
                <Td className="text-ink-2">{t.tier}</Td>
                <Td className="text-ink-2">{t.metric === "purchase" ? "Buying" : "Clicks"}</Td>
                <Td className="num text-right">{t.state === "draft" ? "" : int(t.people)}</Td>
                <Td className="whitespace-nowrap text-muted">{t.started_at ? dateTime(t.started_at) : "Not sent"}</Td>
                <Td>
                  <VerdictBadge v={t.verdict} state={t.state} />
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
      <Section
        title="Winners in use"
        description={`A clear winner of a content test becomes the standard email. A small share of people keep getting the old one, so the CRM can switch back if the winner stops winning.`}
        className="mt-10"
      >
        <Adoptions />
      </Section>
      {tests.data && audiences.data && creating && (
        <NewTest audiences={audiences.data} settings={tests.data.settings} onClose={() => setCreating(false)} />
      )}
      {tests.data && (
        <p className="mt-6 text-[12.5px] text-muted">
          Purchases count for {plural(tests.data.window_days, "day")} after the email. Significance level{" "}
          {pct(tests.data.settings.alpha, 0)}, power {pct(tests.data.settings.power, 0)}.
        </p>
      )}
    </>
  );
}
