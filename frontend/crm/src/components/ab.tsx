import { Badge } from "@xedu/shared/ui";
import type { AbVerdict } from "../api/types";

/** The test's state in two or three words; the full verdict is in the tooltip and on the test's page. */
export function VerdictBadge({ v, state }: { v: AbVerdict | null; state: string }) {
  if (state === "draft") return <Badge>Draft</Badge>;
  if (!v) return <Badge tone="info">Running</Badge>;
  const tone =
    v.status === "winner"
      ? "good"
      : v.status === "broken" || v.status === "loser"
        ? "bad"
        : v.status === "running"
          ? "info"
          : "neutral";
  const label =
    v.status === "winner"
      ? `Variant ${v.winner ?? ""} wins`
      : v.status === "loser"
        ? "A variant did worse"
        : v.status === "broken"
          ? "Split looks broken"
          : v.status === "running"
            ? "Running"
            : v.status === "waiting"
              ? "Not sent"
              : "No clear difference";
  return (
    <Badge tone={tone} title={v.headline}>
      {label}
    </Badge>
  );
}
