/** Number, money and date formatting in Indian English (lakh and crore grouping, 24-hour times). */

const LOCALE = "en-IN";

const moneyFmt = new Intl.NumberFormat(LOCALE, { style: "currency", currency: "INR", maximumFractionDigits: 0 });
const compactMoneyFmt = new Intl.NumberFormat(LOCALE, {
  style: "currency",
  currency: "INR",
  notation: "compact",
  maximumFractionDigits: 1,
});
const intFmt = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 0 });
const compactFmt = new Intl.NumberFormat(LOCALE, { notation: "compact", maximumFractionDigits: 1 });

type Num = number | null | undefined;

const isNum = (v: Num): v is number => typeof v === "number" && Number.isFinite(v);

/** 45000 -> "₹45,000"; null -> the fallback. */
export function money(v: Num, fallback = "Not known"): string {
  return isNum(v) ? moneyFmt.format(v) : fallback;
}

/** A signed amount: +₹4,100 or -₹600 (a real minus sign). */
export function signedMoney(v: Num, fallback = "Not known"): string {
  if (!isNum(v)) return fallback;
  const s = moneyFmt.format(Math.abs(v));
  return v > 0 ? `+${s}` : v < 0 ? `−${s}` : s;
}

/**
 * 2450000 -> "₹24.5L" (lakh), 12000000 -> "₹1.2Cr". Below one lakh the full amount is shown (₹15,200): Indian
 * English writes a compact thousand as "T", which reads like a trillion.
 */
export function compactMoney(v: Num, fallback = "Not known"): string {
  if (!isNum(v)) return fallback;
  return Math.abs(v) < 100_000 ? moneyFmt.format(v) : compactMoneyFmt.format(v);
}

export function int(v: Num, fallback = "0"): string {
  return isNum(v) ? intFmt.format(v) : fallback;
}

/** 12345 -> "12,345"; 2450000 -> "24.5L" (counts are compacted only from one lakh). */
export function compact(v: Num, fallback = "0"): string {
  if (!isNum(v)) return fallback;
  return Math.abs(v) < 100_000 ? intFmt.format(v) : compactFmt.format(v);
}

/** 0.4123 -> "41%" (digits: decimals). */
export function pct(v: Num, digits = 0, fallback = "Not known"): string {
  return isNum(v) ? `${(v * 100).toFixed(digits)}%` : fallback;
}

/** A change in probability, in percentage points: 0.052 -> "+5.2 points". */
export function points(v: Num, digits = 1, fallback = "Not known"): string {
  if (!isNum(v)) return fallback;
  const n = (v * 100).toFixed(digits);
  return v > 0 ? `+${n} points` : v < 0 ? `−${n.replace("-", "")} points` : `${n} points`;
}

/** A size of a difference in percentage points, without a sign: 0.05 -> "5 points". */
export function pointsPlain(v: Num, digits = 0, fallback = "Not known"): string {
  return isNum(v) ? `${Math.abs(v * 100).toFixed(digits)} points` : fallback;
}

/** The backend sends local times as "2026-10-17 16:52:03". */
export function parseTime(s: string | null | undefined): Date | null {
  if (!s) return null;
  const d = new Date(s.length > 10 ? s.replace(" ", "T") : `${s}T00:00:00`);
  return Number.isNaN(d.getTime()) ? null : d;
}

const dateFmt = new Intl.DateTimeFormat(LOCALE, { day: "numeric", month: "short", year: "numeric" });
const dateTimeFmt = new Intl.DateTimeFormat(LOCALE, {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});
const timeFmt = new Intl.DateTimeFormat(LOCALE, { hour: "2-digit", minute: "2-digit", hour12: false });
const dayFmt = new Intl.DateTimeFormat(LOCALE, { day: "numeric", month: "short" });

export function date(s: string | null | undefined, fallback = ""): string {
  const d = parseTime(s);
  return d ? dateFmt.format(d) : fallback;
}

export function dateTime(s: string | null | undefined, fallback = ""): string {
  const d = parseTime(s);
  return d ? dateTimeFmt.format(d) : fallback;
}

/** "18 Sep": for chart axes and short lists. */
export function shortDate(s: string | null | undefined, fallback = ""): string {
  const d = parseTime(s);
  return d ? dayFmt.format(d) : fallback;
}

export function time(s: string | null | undefined, fallback = ""): string {
  const d = parseTime(s);
  return d ? timeFmt.format(d) : fallback;
}

const rtf = new Intl.RelativeTimeFormat(LOCALE, { numeric: "auto" });

/** "3 minutes ago", "yesterday", "in 2 days". */
export function relative(s: string | null | undefined, now: Date = new Date(), fallback = ""): string {
  const d = parseTime(s);
  if (!d) return fallback;
  const sec = (d.getTime() - now.getTime()) / 1000;
  const abs = Math.abs(sec);
  if (abs < 45) return "just now";
  const steps: [Intl.RelativeTimeFormatUnit, number][] = [
    ["minute", 60],
    ["hour", 3600],
    ["day", 86400],
    ["week", 604800],
    ["month", 2629800],
    ["year", 31557600],
  ];
  let unit: Intl.RelativeTimeFormatUnit = "minute";
  let size = 60;
  for (const [u, s2] of steps) {
    if (abs >= s2) {
      unit = u;
      size = s2;
    }
  }
  return rtf.format(Math.round(sec / size), unit);
}

/** "Riya Sharma" -> "RS". */
export function initials(name: string | null | undefined): string {
  const parts = (name ?? "").trim().split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase() || "?";
}

/** "1 lead", "3 leads". */
export function plural(n: number, one: string, many = `${one}s`): string {
  return `${int(n)} ${n === 1 ? one : many}`;
}
