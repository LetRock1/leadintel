import { dateTime, money, relative } from "@xedu/shared/lib";
import { Badge, Button, EmptyState } from "@xedu/shared/ui";
import { Scale } from "lucide-react";
import { useState } from "react";
import type { DecisionItem } from "../../api/types";
import { DecisionReceipt } from "../../components/receipt";
import { actionLabel, outcomeLabel, POLICY_LABEL, triggerLabel } from "../../lib/labels";

function Outcome({ d }: { d: DecisionItem }) {
  if (d.outcome === "bought" && d.bought) {
    return (
      <Badge tone="good">
        Bought {d.bought.course} for {money(d.bought.paid)}
      </Badge>
    );
  }
  if (d.outcome === "did_not_buy") return <Badge>Did not buy within the window</Badge>;
  return <Badge tone="info">Waiting{typeof d.days_left === "number" ? `, ${d.days_left} days left` : ""}</Badge>;
}

function Row({ d }: { d: DecisionItem }) {
  const [open, setOpen] = useState(false);
  const title =
    d.kind === "campaign"
      ? `Campaign: ${d.name ?? ""}`
      : d.kind === "ab"
        ? `A/B test: ${d.name ?? ""}`
        : `${d.label ?? actionLabel(d.action)}`;
  return (
    <li className="border-b border-line px-4 py-3 last:border-b-0">
      <div className="flex flex-wrap items-start gap-x-4 gap-y-1.5">
        <div className="min-w-0 flex-1 basis-72">
          <p className="text-[14px] font-medium text-ink">{title}</p>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12.5px] text-muted">
            <span title={dateTime(d.at)}>{relative(d.at)}</span>
            {d.kind === "decision" && d.trigger && <span>After: {triggerLabel(d.trigger).toLowerCase()}</span>}
            {d.kind === "decision" && d.policy && <span>{POLICY_LABEL[d.policy]}</span>}
            {d.kind !== "decision" && d.arm && (
              <span>
                {d.arm === "holdout" || d.arm === "control"
                  ? "Held out at random: no email"
                  : d.kind === "campaign"
                    ? "Sent the campaign email"
                    : `Sent variant ${d.arm}`}
              </span>
            )}
            {d.email && (
              <span>{d.email.clicked_at ? `Email clicked ${relative(d.email.clicked_at)}` : "Email not clicked"}</span>
            )}
            {d.task && (
              <span>
                {d.task.status === "open" ? "Task open" : `Task: ${outcomeLabel(d.task.outcome).toLowerCase()}`}
              </span>
            )}
            {d.next_visit && <span>Came back {relative(d.next_visit)}</span>}
            {d.adopted_email && <span>Standard email from the test {d.adopted_email.test}</span>}
          </div>
        </div>
        <Outcome d={d} />
      </div>
      {d.kind === "decision" && d.options && d.options.length > 0 && (
        <div className="mt-2">
          <Button size="sm" variant="ghost" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
            {open ? "Hide the receipt" : "Show the receipt"}
          </Button>
          {open && (
            <DecisionReceipt
              className="mt-2 max-w-xl"
              compact
              options={d.options}
              chosen={d.action}
              modelBest={d.model_best}
              policy={d.policy}
              slotPrice={d.slot_price}
              price={d.price}
              meta={d.model_version ? `Model ${d.model_version}` : undefined}
            />
          )}
        </div>
      )}
    </li>
  );
}

/** Every step the CRM took, or chose not to take, for this person, and what happened after it. */
export function Decisions({ decisions }: { decisions: DecisionItem[] }) {
  if (!decisions.length) {
    return (
      <EmptyState icon={Scale} title="No decisions yet">
        The CRM decides a step after each visit, enquiry, wishlist, cart or checkout. Each decision is listed here with
        its receipt and its outcome.
      </EmptyState>
    );
  }
  return (
    <>
      <ul className="rounded-md border border-line bg-surface">
        {decisions.map((d, i) => (
          <Row key={`${d.kind}-${d.id ?? i}`} d={d} />
        ))}
      </ul>
      <p className="mt-3 text-[12.5px] text-muted">
        An outcome counts a purchase within the outcome window after the decision. The latest 20 decisions are shown.
      </p>
    </>
  );
}
