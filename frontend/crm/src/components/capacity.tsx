import { cn, int, money, plural } from "@xedu/shared/lib";
import { Badge } from "@xedu/shared/ui";
import type { Capacity } from "../api/types";

/** One cell per call slot while the day's capacity is small enough to count; a plain bar above that. */
function SlotCells({ used, capacity }: { used: number; capacity: number }) {
  const shown = Math.min(used, capacity);
  if (capacity <= 40) {
    return (
      <div aria-hidden className="flex gap-[3px]">
        {Array.from({ length: capacity }, (_, i) => (
          <span
            key={i}
            className={cn("h-3 flex-1 rounded-[2px]", i < shown ? "bg-brand" : "bg-sunken ring-1 ring-inset ring-line")}
          />
        ))}
      </div>
    );
  }
  return (
    <div aria-hidden className="h-3 overflow-hidden rounded-[2px] bg-sunken ring-1 ring-inset ring-line">
      <div className="h-full bg-brand" style={{ width: `${(100 * shown) / Math.max(capacity, 1)}%` }} />
    </div>
  );
}

function priceSentence(c: Capacity): string {
  if (c.full) return "Today's call slots are used up. New decisions choose the best step without a call.";
  if (c.policy === "fcfs") return "Calls are given out first come, first served until the slots are used.";
  if (!c.price) return "Calls are not scarce right now, so every call worth making gets a slot.";
  return `A call is created only when it adds more than ${money(c.price)} over the best step without a call.`;
}

function teamSentence(c: Capacity): string {
  if (c.full) return "Today's call slots are used up. New decisions choose the best step without a call.";
  if (c.policy === "fcfs") return "Calls are given out first come, first served until the slots are used.";
  if (!c.price) return "Calls are not scarce right now, so every call worth making gets a slot.";
  return "Calls are scarce, so the CRM keeps them for the learners a call helps most; the others get the best step without a call.";
}

/**
 * Today's call slots (capacity-aware next-best-action): how many are used, and the price a call has to beat. The
 * price is the extra profit of the call that would otherwise be crowded out later today.
 */
export function CapacityMeter({
  capacity: c,
  className,
  showPrice = false,
}: {
  capacity: Capacity;
  className?: string;
  /** The rupee price of a slot: for the Next-best-action page, not for the team's own call list. */
  showPrice?: boolean;
}) {
  const label = `${int(c.calls_today)} of ${int(c.capacity)} call slots used today`;
  return (
    <div className={cn("rounded-md border border-line bg-surface px-4 py-3.5", className)}>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 className="text-[14px] font-semibold text-ink">Call slots today</h2>
        <Badge tone={c.policy === "priced" ? "brand" : "neutral"} variant="outline">
          {c.policy === "priced" ? "Priced slots" : "First come, first served"}
        </Badge>
        <span className="ml-auto text-[13px] text-muted">
          <span className="num font-semibold text-ink">{int(c.calls_today)}</span> of{" "}
          <span className="num">{int(c.capacity)}</span> used
        </span>
      </div>
      <div
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={c.capacity}
        aria-valuenow={c.calls_today}
        className="mt-2.5"
      >
        <SlotCells used={c.calls_today} capacity={c.capacity} />
      </div>
      {showPrice ? (
        <div className="mt-3 flex flex-wrap items-baseline gap-x-6 gap-y-1.5">
          <p className="text-[13.5px] text-ink">
            Price of a call slot{" "}
            <span className="num text-[16px] font-semibold">
              {c.full ? "Full" : c.price === null ? "Not set" : money(c.price)}
            </span>
          </p>
          <p className="min-w-0 flex-1 basis-80 text-[13px] text-muted">{priceSentence(c)}</p>
        </div>
      ) : (
        <p className="mt-3 text-[13px] text-muted">{teamSentence(c)}</p>
      )}
      <p className="mt-2 text-[12.5px] text-muted">
        Worked out from {plural(c.candidates, "decision")} that could have used a call in the last{" "}
        {plural(c.days_seen || c.lookback_days, "day")}: about {Math.round(c.per_day)} a day.
        {c.note ? ` ${c.note}` : ""}
      </p>
    </div>
  );
}
