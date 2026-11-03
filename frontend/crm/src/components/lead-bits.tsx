import { cn } from "@xedu/shared/lib";
import { Badge } from "@xedu/shared/ui";
import { Link } from "react-router";
import { tierLevel } from "../lib/labels";

/** The lead's tier as four rising bars (hottest tier: all four filled). The tier name is in the tooltip and for screen readers. */
export function TierMeter({ tier, className }: { tier: string | null | undefined; className?: string }) {
  const level = tierLevel(tier);
  return (
    <span
      role="img"
      aria-label={tier ? `Tier: ${tier}` : "No tier"}
      title={tier ?? undefined}
      className={cn("inline-flex items-end gap-[2px]", className)}
    >
      {[1, 2, 3, 4].map((i) => (
        <span
          key={i}
          className={cn("w-[3px] rounded-[1px]", i <= level ? "bg-brand" : "bg-line-strong")}
          style={{ height: 3 + i * 2.5 }}
        />
      ))}
    </span>
  );
}

/** Score out of 100 with the tier bars. */
export function Score({
  score,
  tier,
  large,
}: {
  score: number | null | undefined;
  tier?: string | null;
  large?: boolean;
}) {
  return (
    <span className="inline-flex items-center gap-2">
      <TierMeter tier={tier} />
      <span className={cn("num font-semibold text-ink", large ? "text-[20px]" : "text-[13.5px]")}>
        {typeof score === "number" ? Math.round(score) : "None"}
      </span>
    </span>
  );
}

export function SimulatedTag({ className }: { className?: string }) {
  return (
    <Badge
      variant="outline"
      className={className}
      title="A simulated learner: the website and the CRM treat them like anyone else"
    >
      Simulated
    </Badge>
  );
}

/** Name (linked to the lead page) and email, with the simulated, customer and lost tags. */
export function Person({
  leadId,
  name,
  email,
  simulated,
  customer,
  lost,
}: {
  leadId?: number | null;
  name: string;
  email?: string | null;
  simulated?: boolean;
  customer?: boolean;
  lost?: boolean;
}) {
  return (
    <div className="min-w-0">
      <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
        {leadId ? (
          <Link to={`/leads/${leadId}`} className="truncate font-medium text-ink hover:text-brand-ink hover:underline">
            {name}
          </Link>
        ) : (
          <span className="truncate font-medium text-ink">{name}</span>
        )}
        {customer && <Badge tone="good">Customer</Badge>}
        {lost && <Badge>Lost</Badge>}
        {simulated && <SimulatedTag />}
      </div>
      {email && <p className="truncate text-[12.5px] text-muted">{email}</p>}
    </div>
  );
}
