import { useChartColors } from "@xedu/shared/lib";
import { signedPoints } from "../lib/learning";

export interface EffectItem {
  key: string;
  label: string;
  /** Points of buying chance for a typical lead (5.8 means 5.8 percentage points). */
  points: number;
  detail?: string;
}

/**
 * Learned effects as bars that grow left (lowers the chance to buy) or right (raises it) from a centre line, on one
 * scale, with the value written out in text so the colour never carries the meaning on its own.
 */
export function EffectBars({ items, label }: { items: EffectItem[]; label: string }) {
  const c = useChartColors();
  const max = Math.max(...items.map((i) => Math.abs(i.points)), 1);
  return (
    <ul aria-label={label} className="rounded-md border border-line bg-surface">
      {items.map((i) => (
        <li
          key={i.key}
          className="grid grid-cols-[minmax(0,1fr)_minmax(4rem,7rem)_6.5rem] items-center gap-x-4 border-b border-line px-4 py-2.5 last:border-b-0"
        >
          <div className="min-w-0">
            <p className="truncate text-[13.5px] text-ink">{i.label}</p>
            {i.detail && <p className="truncate text-[12.5px] text-muted">{i.detail}</p>}
          </div>
          <div aria-hidden className="relative h-2">
            <span className="absolute inset-y-[-3px] left-1/2 w-px" style={{ background: c.axis }} />
            <span
              className="absolute inset-y-0 rounded-full"
              style={{
                background: i.points >= 0 ? c.series[0] : c.series[1],
                left: i.points >= 0 ? "50%" : `${50 - (50 * Math.abs(i.points)) / max}%`,
                width: `${(50 * Math.abs(i.points)) / max}%`,
              }}
            />
          </div>
          <p className="num text-right text-[13.5px] font-medium text-ink">{signedPoints(i.points)}</p>
        </li>
      ))}
    </ul>
  );
}
