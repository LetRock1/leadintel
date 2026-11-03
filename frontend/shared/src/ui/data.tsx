import { ChevronLeft, ChevronRight } from "lucide-react";
import { useRef, type KeyboardEvent, type ReactNode, type TdHTMLAttributes, type ThHTMLAttributes } from "react";
import { cn, int } from "../lib";

/** A horizontally scrollable table frame with a hairline border. */
export function Table({ children, className, label }: { children: ReactNode; className?: string; label?: string }) {
  return (
    <div className={cn("overflow-x-auto rounded-md border border-line bg-surface", className)}>
      <table aria-label={label} className="w-full border-collapse text-left text-[13.5px]">
        {children}
      </table>
    </div>
  );
}

export function Th({ className, children, ...rest }: ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      scope="col"
      className={cn(
        "sticky top-0 z-[1] h-9 whitespace-nowrap border-b border-line bg-sunken px-3 text-[12.5px] font-medium text-muted",
        className,
      )}
      {...rest}
    >
      {children}
    </th>
  );
}

export function Td({ className, children, ...rest }: TdHTMLAttributes<HTMLTableCellElement>) {
  return (
    <td className={cn("border-b border-line px-3 py-2.5 align-middle", className)} {...rest}>
      {children}
    </td>
  );
}

export interface LeaderProps {
  label: ReactNode;
  value: ReactNode;
  strong?: boolean;
  muted?: boolean;
  className?: string;
}

/** One itemised line: label, a dotted leader, the value (right-aligned, tabular figures). */
export function Leader({ label, value, strong, muted, className }: LeaderProps) {
  return (
    <div className={cn("flex items-baseline text-[13.5px]", muted && "text-muted", className)}>
      <span className={cn("min-w-0 truncate", strong ? "font-semibold text-ink" : muted ? "" : "text-ink-2")}>
        {label}
      </span>
      <span aria-hidden className="leader" />
      <span className={cn("num shrink-0 text-right", strong ? "font-semibold text-ink" : "text-ink")}>{value}</span>
    </div>
  );
}

export interface SegmentOption<T extends string> {
  value: T;
  label: string;
  count?: number;
}

/** A small set of mutually exclusive filters, side by side. */
export function Segmented<T extends string>({
  options,
  value,
  onChange,
  label,
  size = "md",
}: {
  options: SegmentOption<T>[];
  value: T;
  onChange: (v: T) => void;
  label: string;
  size?: "sm" | "md";
}) {
  return (
    <div role="group" aria-label={label} className="inline-flex rounded-sm border border-line-strong bg-surface p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={value === o.value}
          onClick={() => onChange(o.value)}
          className={cn(
            "rounded-[4px] px-2.5 font-medium transition-colors",
            size === "sm" ? "h-7 text-[12.5px]" : "h-8 text-[13px]",
            value === o.value ? "bg-brand-soft text-brand-ink" : "text-ink-2 hover:text-ink",
          )}
        >
          {o.label}
          {o.count !== undefined && <span className="num ml-1.5 text-muted">{int(o.count)}</span>}
        </button>
      ))}
    </div>
  );
}

export interface TabItem<T extends string> {
  id: T;
  label: string;
  count?: number;
}

/** Tabs (the panel is rendered by the page); arrow keys move between tabs. */
export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
  label,
  className,
}: {
  tabs: TabItem<T>[];
  value: T;
  onChange: (v: T) => void;
  label: string;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    const i = tabs.findIndex((t) => t.id === value);
    const next = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
    onChange(next.id);
    ref.current?.querySelector<HTMLButtonElement>(`[data-tab="${next.id}"]`)?.focus();
  };
  return (
    <div
      ref={ref}
      role="tablist"
      aria-label={label}
      onKeyDown={onKey}
      className={cn("flex gap-5 border-b border-line", className)}
    >
      {tabs.map((t) => (
        <button
          key={t.id}
          data-tab={t.id}
          type="button"
          role="tab"
          aria-selected={value === t.id}
          tabIndex={value === t.id ? 0 : -1}
          onClick={() => onChange(t.id)}
          className={cn(
            "-mb-px border-b-2 pb-2.5 pt-1 text-[14px] font-medium transition-colors",
            value === t.id ? "border-brand text-ink" : "border-transparent text-muted hover:text-ink",
          )}
        >
          {t.label}
          {t.count !== undefined && <span className="num ml-1.5 text-[12.5px] text-muted">{int(t.count)}</span>}
        </button>
      ))}
    </div>
  );
}

/** "1 to 50 of 1,234" with previous and next. */
export function Pager({
  offset,
  limit,
  total,
  onChange,
}: {
  offset: number;
  limit: number;
  total: number;
  onChange: (offset: number) => void;
}) {
  if (total <= limit) return null;
  const end = Math.min(offset + limit, total);
  return (
    <nav aria-label="Pages" className="flex items-center justify-end gap-2 text-[13px] text-muted">
      <span className="num">
        {int(offset + 1)} to {int(end)} of {int(total)}
      </span>
      <button
        type="button"
        aria-label="Previous page"
        disabled={offset === 0}
        onClick={() => onChange(Math.max(0, offset - limit))}
        className="inline-flex size-8 items-center justify-center rounded-sm border border-line-strong bg-surface text-ink-2 hover:bg-sunken disabled:opacity-40"
      >
        <ChevronLeft aria-hidden className="size-4" />
      </button>
      <button
        type="button"
        aria-label="Next page"
        disabled={end >= total}
        onClick={() => onChange(offset + limit)}
        className="inline-flex size-8 items-center justify-center rounded-sm border border-line-strong bg-surface text-ink-2 hover:bg-sunken disabled:opacity-40"
      >
        <ChevronRight aria-hidden className="size-4" />
      </button>
    </nav>
  );
}
