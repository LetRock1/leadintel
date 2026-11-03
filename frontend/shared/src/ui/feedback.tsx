import { CheckCircle2, Info, Loader2, TriangleAlert, X, XCircle, type LucideIcon } from "lucide-react";
import { useCallback, useMemo, useRef, useState, type ReactNode } from "react";
import { cn } from "../lib";
import { ToastContext, type ToastItem } from "./toast-context";

export type Tone = "neutral" | "brand" | "good" | "bad" | "warn" | "info";

const soft: Record<Tone, string> = {
  neutral: "bg-sunken text-ink-2",
  brand: "bg-brand-soft text-brand-ink",
  good: "bg-good-soft text-good",
  bad: "bg-bad-soft text-bad",
  warn: "bg-warn-soft text-warn",
  info: "bg-info-soft text-info",
};

const outline: Record<Tone, string> = {
  neutral: "border border-line-strong text-ink-2",
  brand: "border border-brand/40 text-brand-ink",
  good: "border border-good/40 text-good",
  bad: "border border-bad/40 text-bad",
  warn: "border border-warn/40 text-warn",
  info: "border border-info/40 text-info",
};

export interface BadgeProps {
  tone?: Tone;
  variant?: "soft" | "outline";
  icon?: LucideIcon;
  className?: string;
  title?: string;
  children: ReactNode;
}

/** A short state label. Never colour alone: the words carry the meaning. */
export function Badge({ tone = "neutral", variant = "soft", icon: Icon, className, title, children }: BadgeProps) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex h-5 items-center gap-1 whitespace-nowrap rounded-xs px-1.5 text-[12px] font-medium leading-none",
        variant === "soft" ? soft[tone] : outline[tone],
        className,
      )}
    >
      {Icon && <Icon aria-hidden className="size-3.5" />}
      {children}
    </span>
  );
}

export function Spinner({ className, label = "Loading" }: { className?: string; label?: string }) {
  return (
    <span role="status" className={cn("inline-flex items-center gap-2 text-muted", className)}>
      <Loader2 aria-hidden className="size-4 animate-spin" />
      <span className="text-[13px]">{label}</span>
    </span>
  );
}

/** A whole page waiting for its code on the first visit (the router's fallback before a lazy page has loaded). */
export function PageLoader({ label = "Loading" }: { label?: string }) {
  return (
    <div className="grid min-h-dvh place-items-center bg-canvas">
      <Spinner label={label} />
    </div>
  );
}

export interface EmptyStateProps {
  icon?: LucideIcon;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
  className?: string;
}

/** An empty list or a missing result: what it means and what to do next. */
export function EmptyState({ icon: Icon, title, children, action, className }: EmptyStateProps) {
  return (
    <div className={cn("flex flex-col items-start gap-2 px-1 py-8", className)}>
      {Icon && <Icon aria-hidden className="size-5 text-muted" />}
      <p className="text-[15px] font-medium text-ink">{title}</p>
      {children && <div className="max-w-prose text-[14px] text-muted">{children}</div>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

const noticeIcon: Record<"info" | "good" | "warn" | "bad", LucideIcon> = {
  info: Info,
  good: CheckCircle2,
  warn: TriangleAlert,
  bad: XCircle,
};

export interface NoticeProps {
  tone?: "info" | "good" | "warn" | "bad";
  title?: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
  className?: string;
}

/** An inline message inside a page: an error to fix, a result, a caveat. */
export function Notice({ tone = "info", title, children, action, className }: NoticeProps) {
  const Icon = noticeIcon[tone];
  return (
    <div
      role={tone === "bad" ? "alert" : "status"}
      className={cn("flex gap-3 rounded-md border px-3.5 py-3 text-[14px]", soft[tone], "border-current/15", className)}
    >
      <Icon aria-hidden className="mt-0.5 size-4 shrink-0" />
      <div className="min-w-0 flex-1 text-ink">
        {title && <p className="font-medium">{title}</p>}
        {children && <div className={cn(title && "mt-0.5", "text-ink-2")}>{children}</div>}
      </div>
      {action}
    </div>
  );
}

/** Short confirmations ("Saved", "Email sent"); errors that need attention stay in the page as a Notice. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const next = useRef(1);
  const show = useCallback((t: Omit<ToastItem, "id">) => {
    const id = next.current++;
    setItems((xs) => [...xs.slice(-3), { ...t, id }]);
    window.setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), t.tone === "bad" ? 7000 : 4000);
  }, []);
  const value = useMemo(() => show, [show]);
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-[min(380px,calc(100vw-2rem))] flex-col gap-2"
      >
        {items.map((t) => {
          const Icon = t.tone === "good" ? CheckCircle2 : t.tone === "bad" ? XCircle : Info;
          return (
            <div
              key={t.id}
              className="pointer-events-auto flex items-start gap-2.5 rounded-md border border-line bg-raised px-3.5 py-3 text-[14px] text-ink shadow-overlay"
            >
              <Icon
                aria-hidden
                className={cn(
                  "mt-0.5 size-4 shrink-0",
                  t.tone === "good" ? "text-good" : t.tone === "bad" ? "text-bad" : "text-info",
                )}
              />
              <p className="flex-1">{t.text}</p>
              <button
                type="button"
                aria-label="Dismiss"
                className="text-muted hover:text-ink"
                onClick={() => setItems((xs) => xs.filter((x) => x.id !== t.id))}
              >
                <X aria-hidden className="size-4" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}
