import { date, money, parseTime, time } from "@xedu/shared/lib";
import { Badge, EmptyState } from "@xedu/shared/ui";
import {
  Activity as ActivityIcon,
  CircleDollarSign,
  Gauge,
  Mail,
  MessageCircle,
  MousePointerClick,
  Phone,
  PhoneIncoming,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { useCourses } from "../../api/queries";
import type { LeadPage } from "../../api/types";
import { eventLabel, outcomeLabel, SCORE_REASON_LABEL } from "../../lib/labels";

interface Item {
  at: string;
  icon: LucideIcon;
  text: ReactNode;
  detail?: ReactNode;
  key: string;
}

function minutes(sec: number | null): string | null {
  if (!sec) return null;
  return sec < 60 ? `${sec} s` : `${Math.round(sec / 60)} min`;
}

function items(lead: LeadPage, title: (slug: string | null) => string): Item[] {
  const out: Item[] = [];
  for (const e of lead.behaviour_events) {
    if (e.event_type === "purchase") continue;
    out.push({
      key: `e${e.id}`,
      at: e.created_at,
      icon: MousePointerClick,
      text: eventLabel(e.event_type),
      detail: [title(e.course_slug), minutes(e.time_spent_sec)].filter(Boolean).join(", ") || undefined,
    });
  }
  for (const m of lead.emails) {
    out.push({
      key: `m${m.id}`,
      at: m.sent_at,
      icon: Mail,
      text: m.error ? <>Email not sent: {m.subject}</> : <>Email sent: {m.subject}</>,
      detail: m.error ? (
        <>The mail server did not take it: {m.error}</>
      ) : (
        <>
          {m.campaign_name
            ? `Campaign ${m.campaign_name}. `
            : m.ab_test_id
              ? `A/B test, variant ${m.variant ?? ""}. `
              : ""}
          {m.first_clicked_at
            ? `Clicked ${m.click_count} time${m.click_count === 1 ? "" : "s"}, first at ${time(m.first_clicked_at)}.`
            : "Not clicked."}
        </>
      ),
    });
  }
  for (const p of lead.purchases) {
    out.push({
      key: `p${p.id}`,
      at: p.purchased_at,
      icon: CircleDollarSign,
      text: (
        <>
          Bought {p.course_title} for <span className="num">{money(p.price_paid)}</span>
        </>
      ),
      detail: p.coupon_used ? `Coupon ${p.coupon_used}, ${money(p.discount_amount ?? 0)} off` : undefined,
    });
  }
  for (const t of lead.tasks) {
    out.push({
      key: `t${t.id}`,
      at: t.done_at ?? t.created_at,
      icon: t.task_type === "call" ? Phone : MessageCircle,
      text: t.title,
      detail:
        t.status === "open" ? (
          <Badge tone="warn">Open</Badge>
        ) : (
          <>
            {outcomeLabel(t.outcome)}
            {t.done_by ? `, by ${t.done_by}` : ""}
          </>
        ),
    });
  }
  for (const c of lead.callbacks) {
    out.push({
      key: `c${c.id}`,
      at: c.created_at,
      icon: PhoneIncoming,
      text: "Asked for a call-back",
      detail: [
        c.preferred_time && `Best time: ${c.preferred_time}`,
        c.note,
        c.status === "done" ? `Done by ${c.done_by ?? "the team"}` : "Open",
      ]
        .filter(Boolean)
        .join(". "),
    });
  }
  for (const s of lead.score_history) {
    if (Math.round(s.old_score) === Math.round(s.new_score)) continue;
    out.push({
      key: `s${s.id}`,
      at: s.created_at,
      icon: Gauge,
      text: (
        <>
          Score <span className="num">{Math.round(s.old_score)}</span> to{" "}
          <span className="num">{Math.round(s.new_score)}</span>
        </>
      ),
      detail: `${SCORE_REASON_LABEL[s.reason] ?? s.reason}${s.old_tier !== s.new_tier ? `. Now ${s.new_tier}` : ""}`,
    });
  }
  for (const [i, m] of lead.chat.entries()) {
    if (m.role !== "user") continue;
    out.push({
      key: `q${i}`,
      at: m.created_at,
      icon: MessageCircle,
      text: "Asked the help assistant",
      detail: `"${m.text}"`,
    });
  }
  return out.sort((a, b) => (parseTime(b.at)?.getTime() ?? 0) - (parseTime(a.at)?.getTime() ?? 0));
}

function dayLabel(at: string): string {
  const d = parseTime(at);
  if (!d) return "";
  const today = new Date();
  const y = new Date(today);
  y.setDate(today.getDate() - 1);
  if (d.toDateString() === today.toDateString()) return "Today";
  if (d.toDateString() === y.toDateString()) return "Yesterday";
  return date(at);
}

/** Everything the person did and everything the CRM did for them, newest first, grouped by day. */
export function Activity({ lead }: { lead: LeadPage }) {
  const courses = useCourses();
  const all = items(lead, courses.title);
  if (!all.length) {
    return (
      <EmptyState icon={ActivityIcon} title="No activity yet">
        Visits, emails, calls and purchases appear here as they happen.
      </EmptyState>
    );
  }
  const groups: { day: string; items: Item[] }[] = [];
  for (const it of all) {
    const day = dayLabel(it.at);
    const last = groups[groups.length - 1];
    if (last && last.day === day) last.items.push(it);
    else groups.push({ day, items: [it] });
  }
  return (
    <div className="flex flex-col gap-6">
      {groups.map((g) => (
        <section key={g.day}>
          <h3 className="mb-2 text-[13px] font-semibold text-ink">{g.day}</h3>
          <ol className="relative ml-3 border-l border-line">
            {g.items.map((it) => {
              const Icon = it.icon;
              return (
                <li key={it.key} className="relative pb-3.5 pl-6 last:pb-0">
                  <span className="absolute -left-[13px] top-0 flex size-[26px] items-center justify-center rounded-full border border-line bg-surface text-muted">
                    <Icon aria-hidden className="size-3.5" />
                  </span>
                  <div className="flex flex-wrap items-baseline gap-x-3">
                    <p className="min-w-0 flex-1 text-[13.5px] text-ink">{it.text}</p>
                    <time className="num text-[12.5px] text-muted" dateTime={it.at.replace(" ", "T")}>
                      {time(it.at)}
                    </time>
                  </div>
                  {it.detail && <div className="mt-0.5 text-[12.5px] text-muted">{it.detail}</div>}
                </li>
              );
            })}
          </ol>
        </section>
      ))}
      <p className="text-[12.5px] text-muted">Showing the latest 30 website events, 20 emails and 10 tasks.</p>
    </div>
  );
}
