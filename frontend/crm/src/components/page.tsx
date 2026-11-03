import { cn } from "@xedu/shared/lib";
import type { ReactNode } from "react";

/** The page title, one line on what the page is for, and the page's main actions. */
export function PageHeader({
  title,
  description,
  actions,
  aside,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  aside?: ReactNode;
}) {
  return (
    <header className="mb-6 flex flex-wrap items-end gap-x-6 gap-y-3">
      <div className="min-w-0 flex-1 basis-80">
        <h1 className="text-[22px] font-semibold leading-tight tracking-[-0.01em] text-ink">{title}</h1>
        {description && <p className="mt-1.5 max-w-[72ch] text-[14px] text-muted">{description}</p>}
        {aside}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

/**
 * A part of a page: a heading with an optional line of context and actions, then the content. Sections are separated
 * by space and a hairline, not boxed; tables, receipts and charts bring their own frame.
 */
export function Section({
  title,
  description,
  actions,
  children,
  className,
  id,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  id?: string;
}) {
  return (
    <section id={id} aria-labelledby={id ? `${id}-title` : undefined} className={cn("mt-9 first:mt-0", className)}>
      <div className="mb-3 flex flex-wrap items-end gap-x-4 gap-y-2">
        <div className="min-w-0 flex-1 basis-72">
          <h2 id={id ? `${id}-title` : undefined} className="text-[16px] font-semibold text-ink">
            {title}
          </h2>
          {description && <p className="mt-0.5 max-w-[80ch] text-[13.5px] text-muted">{description}</p>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {children}
    </section>
  );
}

/** A bordered surface for content that needs a frame (a form, a chart, a short list). */
export function Panel({
  children,
  className,
  padded = true,
}: {
  children: ReactNode;
  className?: string;
  padded?: boolean;
}) {
  return <div className={cn("rounded-md border border-line bg-surface", padded && "p-4", className)}>{children}</div>;
}

export interface Kpi {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
}

/** Headline numbers in one band with hairline dividers (one row on a wide screen, wrapping on a narrow one). */
export function KpiStrip({ items, className }: { items: Kpi[]; className?: string }) {
  const cols =
    items.length >= 6
      ? "grid-cols-2 sm:grid-cols-3 xl:grid-cols-6"
      : items.length === 5
        ? "grid-cols-2 sm:grid-cols-3 xl:grid-cols-5"
        : items.length === 4
          ? "grid-cols-2 lg:grid-cols-4"
          : "grid-cols-1 sm:grid-cols-3";
  return (
    <dl className={cn("grid gap-px overflow-hidden rounded-md border border-line bg-line", cols, className)}>
      {items.map((k) => (
        <div key={k.label} className="bg-surface px-4 py-3.5">
          <dt className="text-[12.5px] text-muted">{k.label}</dt>
          <dd className="num mt-1 text-[22px] font-semibold leading-tight tracking-[-0.01em] text-ink">{k.value}</dd>
          {k.detail && <dd className="mt-0.5 text-[12.5px] text-muted">{k.detail}</dd>}
        </div>
      ))}
    </dl>
  );
}

/** Label and value pairs in two columns (a fact sheet). */
export function Facts({ items, className }: { items: { label: string; value: ReactNode }[]; className?: string }) {
  return (
    <dl className={cn("grid grid-cols-[minmax(0,10rem)_1fr] gap-x-4 gap-y-2 text-[13.5px]", className)}>
      {items.map((f) => (
        <div key={f.label} className="contents">
          <dt className="text-muted">{f.label}</dt>
          <dd className="min-w-0 break-words text-ink">{f.value}</dd>
        </div>
      ))}
    </dl>
  );
}
