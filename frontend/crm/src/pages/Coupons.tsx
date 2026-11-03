import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { dateTime, errorText, int, parseTime, plural } from "@xedu/shared/lib";
import {
  Badge,
  Button,
  Dialog,
  EmptyState,
  Field,
  Input,
  Notice,
  Pager,
  Segmented,
  Select,
  Table,
  Td,
  Th,
  useToast,
} from "@xedu/shared/ui";
import { Plus, TicketPercent } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { api } from "../api/client";
import type { Coupon, LeadRow, LeadsResponse } from "../api/types";
import { useSession } from "../app/session";
import { PageHeader } from "../components/page";
import { Loading, LoadError } from "../components/state";

const LIMIT = 50;

/** One page of coupons, newest first; `total` counts the ones the filter shows, `all` and `used` every coupon. */
interface CouponList {
  coupons: Coupon[];
  total: number;
  all: number;
  used: number;
}

interface CouponCheck {
  verdict: "pays" | "costs" | "over_budget" | "control" | "customer" | "has_coupon";
  allowed: boolean;
  message: string;
  note?: string | null;
  expected_discount?: number;
  extra_profit?: number;
}

function NewCoupon({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [q, setQ] = useState("");
  const [person, setPerson] = useState<LeadRow | null>(null);
  const [discount, setDiscount] = useState("10");
  const [hours, setHours] = useState("72");
  const found = useQuery({
    queryKey: ["leads", "coupon-search", q],
    queryFn: () => api.get<LeadsResponse>("/leads", { search: q, limit: 6 }),
    enabled: q.trim().length >= 2 && !person,
  });
  // the coupon guard: what this coupon would do for this person, before anyone gives it
  const guard = useQuery({
    queryKey: ["coupon-check", person?.user_id, discount],
    queryFn: () =>
      api.get<CouponCheck>("/coupons/check", { user_id: person?.user_id ?? 0, discount_pct: Number(discount) }),
    enabled: !!person,
  });
  const verdict = guard.data?.verdict;
  const override = verdict === "costs" || verdict === "over_budget";
  const create = useMutation({
    mutationFn: () =>
      api.post<{ coupon_code: string; message?: string }>("/coupons", {
        user_id: person?.user_id,
        tier: person?.recommended_action ?? "",
        discount_pct: Number(discount),
        expires_hours: Number(hours),
        override,
      }),
    onSuccess: (r) => {
      toast({ tone: "good", text: `Coupon ${r.coupon_code} given to ${person?.name}.` });
      void qc.invalidateQueries({ queryKey: ["coupons"] });
      onClose();
    },
  });
  return (
    <Dialog
      open
      onClose={onClose}
      title="Give a personal coupon"
      description="The code works only for this person, until it expires. They see it in their account and at checkout."
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            variant={override ? "danger" : "primary"}
            loading={create.isPending}
            disabled={!person || verdict === "control" || verdict === "has_coupon" || guard.isPending}
            onClick={() => create.mutate()}
          >
            {override ? "Give it anyway" : "Give the coupon"}
          </Button>
        </>
      }
    >
      <div className="grid gap-4">
        {create.isError && <Notice tone="bad">{errorText(create.error)}</Notice>}
        {person && guard.data && (
          <Notice
            tone={
              verdict === "pays" || verdict === "customer"
                ? "good"
                : verdict === "control" || verdict === "has_coupon"
                  ? "bad"
                  : "warn"
            }
            title={
              verdict === "pays"
                ? "This coupon pays for itself"
                : verdict === "costs"
                  ? "This coupon would mostly give money away"
                  : verdict === "over_budget"
                    ? "Over this month's discount budget"
                    : verdict === "control"
                      ? "Not for the control group"
                      : verdict === "has_coupon"
                        ? "Already has an open coupon"
                        : undefined
            }
          >
            {guard.data.message}
            {guard.data.note ? ` ${guard.data.note}` : ""}
          </Notice>
        )}
        {person ? (
          <div className="flex items-center justify-between rounded-md border border-line bg-sunken px-3 py-2">
            <div>
              <p className="text-[14px] font-medium text-ink">{person.name}</p>
              <p className="text-[12.5px] text-muted">{person.email}</p>
            </div>
            <Button size="sm" variant="ghost" onClick={() => setPerson(null)}>
              Change
            </Button>
          </div>
        ) : (
          <Field label="Who gets it" hint="Type at least two letters of their name or email.">
            <Input value={q} onChange={(e) => setQ(e.target.value)} autoFocus />
          </Field>
        )}
        {!person && found.data && (
          <ul className="rounded-md border border-line">
            {found.data.leads.length === 0 ? (
              <li className="px-3 py-2 text-[13px] text-muted">No one matches.</li>
            ) : (
              found.data.leads.map((l) => (
                <li key={l.id}>
                  <button
                    type="button"
                    className="flex w-full items-baseline gap-3 px-3 py-2 text-left hover:bg-sunken"
                    onClick={() => setPerson(l)}
                  >
                    <span className="text-[13.5px] text-ink">{l.name}</span>
                    <span className="truncate text-[12.5px] text-muted">{l.email}</span>
                  </button>
                </li>
              ))
            )}
          </ul>
        )}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Discount">
            <Select
              value={discount}
              onChange={(e) => setDiscount(e.target.value)}
              options={[5, 10, 15, 20, 25, 30].map((n) => ({ value: String(n), label: `${n}% off` }))}
            />
          </Field>
          <Field label="Valid for">
            <Select
              value={hours}
              onChange={(e) => setHours(e.target.value)}
              options={[
                { value: "24", label: "1 day" },
                { value: "72", label: "3 days" },
                { value: "168", label: "7 days" },
                { value: "336", label: "14 days" },
              ]}
            />
          </Field>
        </div>
      </div>
    </Dialog>
  );
}

function state(c: Coupon): { label: string; tone: "good" | "neutral" | "info" } {
  if (c.used) return { label: `Used ${dateTime(c.used_at)}`, tone: "good" };
  const exp = parseTime(c.expires_at);
  if (exp && exp.getTime() < Date.now()) return { label: "Expired", tone: "neutral" };
  return { label: `Valid until ${dateTime(c.expires_at)}`, tone: "info" };
}

export default function Coupons() {
  const { can } = useSession();
  const qc = useQueryClient();
  const toast = useToast();
  const [creating, setCreating] = useState(false);
  const [show, setShow] = useState<"all" | "used" | "open">("all");
  const [offset, setOffset] = useState(0);
  const list = useQuery({
    queryKey: ["coupons", show, offset],
    queryFn: () => api.get<CouponList>("/coupons", { show, limit: LIMIT, offset }),
    placeholderData: keepPreviousData,
    refetchInterval: 60_000,
  });
  const rows = list.data?.coupons ?? [];
  const total = list.data?.total ?? 0;
  const withdraw = useMutation({
    mutationFn: (id: number) => api.del<{ message: string }>(`/coupons/${id}`),
    onSuccess: (r) => {
      toast({ tone: "good", text: r.message ?? "Coupon withdrawn." });
      // the last coupon on a later page was withdrawn: go back one page instead of showing an empty one
      if (offset > 0 && rows.length === 1) setOffset(Math.max(0, offset - LIMIT));
      void qc.invalidateQueries({ queryKey: ["coupons"] });
    },
    onError: (e) => toast({ tone: "bad", text: errorText(e) }),
  });

  return (
    <>
      <PageHeader
        title="Coupons"
        description="Every personal coupon the CRM or the team gave out, and whether it was used."
        actions={
          can("marketing") ? (
            <Button variant="primary" icon={<Plus aria-hidden className="size-4" />} onClick={() => setCreating(true)}>
              Give a coupon
            </Button>
          ) : undefined
        }
      />
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <Segmented
          label="Show"
          value={show}
          onChange={(v) => {
            setShow(v);
            setOffset(0);
          }}
          options={[
            { value: "all", label: "All" },
            { value: "open", label: "Not used" },
            { value: "used", label: "Used" },
          ]}
        />
        {list.data && (
          <p className="ml-auto text-[13px] text-muted">
            {plural(list.data.all, "coupon")}, {int(list.data.used)} used
          </p>
        )}
      </div>
      {list.isPending ? (
        <Loading label="Loading the coupons" />
      ) : list.isError ? (
        <LoadError error={list.error} what="the coupons" retry={() => void list.refetch()} />
      ) : rows.length === 0 ? (
        <div className="rounded-md border border-line bg-surface px-4">
          {total > 0 ? (
            <EmptyState icon={TicketPercent} title="Nothing on this page any more">
              Coupons were withdrawn while it was open.{" "}
              <Button size="sm" variant="ghost" onClick={() => setOffset(0)}>
                Go to the first page
              </Button>
            </EmptyState>
          ) : (
            <EmptyState icon={TicketPercent} title="No coupons here">
              Next-best-action gives a coupon when a discount adds more profit than it costs.
            </EmptyState>
          )}
        </div>
      ) : (
        <>
          <Table label="Coupons">
            <thead>
              <tr>
                <Th>Code</Th>
                <Th>Person</Th>
                <Th className="text-right">Discount</Th>
                <Th>Status</Th>
                <Th>Given</Th>
                {can("marketing") && <Th aria-label="Actions" />}
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => {
                const s = state(c);
                return (
                  <tr key={c.id}>
                    <Td className="num font-medium text-ink">{c.coupon_code}</Td>
                    <Td>
                      <span className="text-ink">{c.name}</span>
                      <span className="block text-[12.5px] text-muted">{c.email}</span>
                    </Td>
                    <Td className="num text-right">{c.discount_pct}%</Td>
                    <Td>
                      <Badge tone={s.tone}>{s.label}</Badge>
                    </Td>
                    <Td className="whitespace-nowrap text-muted">{dateTime(c.created_at)}</Td>
                    {can("marketing") && (
                      <Td className="text-right">
                        {!c.used && (
                          <Button
                            size="sm"
                            variant="ghost"
                            loading={withdraw.isPending && withdraw.variables === c.id}
                            onClick={() => withdraw.mutate(c.id)}
                          >
                            Withdraw
                          </Button>
                        )}
                      </Td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </Table>
          <div className="mt-3">
            <Pager offset={offset} limit={LIMIT} total={total} onChange={setOffset} />
          </div>
        </>
      )}
      <p className="mt-4 text-[12.5px] text-muted">
        Coupons from A/B tests carry the test&apos;s code. See{" "}
        <Link to="/ab-tests" className="text-brand-ink hover:underline">
          A/B tests
        </Link>{" "}
        for whether a discount paid for itself.
      </p>
      {creating && <NewCoupon onClose={() => setCreating(false)} />}
    </>
  );
}
