/**
 * What a signed-in learner does on the website goes to the backend, which re-scores them at once (the CRM's
 * real-time loop). A visit ("session") starts when a tab opens or after 30 minutes without activity; while the page
 * is in use the visit is kept alive every 30 seconds, so the CRM's "visit ended" follow-up waits until the learner
 * has really left. Nothing is recorded for visitors who are not signed in.
 */
import { getToken, setToken } from "../api/client";

const VISIT_KEY = "xe-visit";
const SOURCE_KEY = "xe-source";
const IDLE_MS = 30 * 60 * 1000;

interface Visit {
  id: number;
  last: number;
}

function readVisit(): Visit | null {
  try {
    const v = JSON.parse(sessionStorage.getItem(VISIT_KEY) ?? "null") as Visit | null;
    return v && Date.now() - v.last < IDLE_MS ? v : null;
  } catch {
    return null;
  }
}

function writeVisit(v: Visit | null): void {
  try {
    if (v) sessionStorage.setItem(VISIT_KEY, JSON.stringify(v));
    else sessionStorage.removeItem(VISIT_KEY);
  } catch {
    /* storage blocked: a new visit starts with every page */
  }
}

export function adoptVisit(id: number | null | undefined): void {
  if (id) writeVisit({ id, last: Date.now() });
}

export function forgetVisit(): void {
  writeVisit(null);
}

export function deviceType(): "Mobile" | "Tablet" | "Desktop" {
  const w = window.screen?.width || window.innerWidth;
  if (/iPad|Tablet/i.test(navigator.userAgent) || (w >= 600 && w < 1024 && "ontouchstart" in window)) return "Tablet";
  if (/Mobi|Android|iPhone/i.test(navigator.userAgent) || w < 600) return "Mobile";
  return "Desktop";
}

/** Where this visit came from (kept for the browser tab): an email, an ad, a search engine, or typed in. */
export function leadSource(): string {
  try {
    const kept = sessionStorage.getItem(SOURCE_KEY);
    if (kept) return kept;
  } catch {
    /* ignore */
  }
  const p = new URLSearchParams(window.location.search);
  const utm = (p.get("utm_source") ?? "").toLowerCase();
  const ref = document.referrer.toLowerCase();
  let source = "Direct Traffic";
  if (p.get("ref")) source = "Email Campaign";
  else if (utm.includes("linkedin") || ref.includes("linkedin.")) source = "LinkedIn";
  else if (utm.includes("youtube") || ref.includes("youtube.")) source = "YouTube";
  else if (/facebook|instagram|twitter|x\.com/.test(utm + ref)) source = "Social Media";
  else if (utm.includes("google")) source = "Google";
  else if (/google\.|bing\.|duckduckgo\./.test(ref)) source = "Organic Search";
  else if (utm.includes("webinar")) source = "Webinar";
  else if (utm) source = "Reference";
  try {
    sessionStorage.setItem(SOURCE_KEY, source);
  } catch {
    /* ignore */
  }
  return source;
}

async function post(path: string, body: unknown, keepalive = false): Promise<Response | null> {
  const token = getToken();
  if (!token) return null;
  try {
    return await fetch(`/api/v1${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify(body),
      keepalive,
    });
  } catch {
    return null;
  }
}

let starting: Promise<number | null> | null = null;

/** The current visit's id, starting a new visit when needed. */
export async function ensureVisit(): Promise<number | null> {
  if (!getToken()) return null;
  const v = readVisit();
  if (v) {
    writeVisit({ id: v.id, last: Date.now() });
    return v.id;
  }
  starting ??= (async () => {
    const res = await post("/session/start", { device_type: deviceType(), lead_source: leadSource() });
    const data = res?.ok ? ((await res.json()) as { session_id: number }) : null;
    adoptVisit(data?.session_id);
    starting = null;
    return data?.session_id ?? null;
  })();
  return starting;
}

/** Records one event. Failures are ignored: tracking must never get in the learner's way. */
export async function track(
  eventType: string,
  courseSlug?: string | null,
  seconds = 0,
  keepalive = false,
): Promise<void> {
  const id = keepalive ? (readVisit()?.id ?? null) : await ensureVisit();
  if (!id) return;
  await post(
    "/track",
    { session_id: id, event_type: eventType, course_slug: courseSlug ?? null, time_spent_sec: Math.round(seconds) },
    keepalive,
  );
}

/** Keeps the visit alive every 30 seconds while the page is visible. Returns a function that stops it. */
export function keepVisitAlive(): () => void {
  const timer = window.setInterval(() => {
    const v = readVisit();
    if (!v || document.visibilityState !== "visible") return;
    writeVisit({ id: v.id, last: Date.now() });
    void post("/session/ping", { session_id: v.id });
  }, 30_000);
  return () => window.clearInterval(timer);
}

const reportedClicks = new Set<string>();

/** An email's button brought the learner here (?ref=<token>): the click is recorded, signed in or not. Once per page
 * load: React runs effects twice while it checks the code in development, and one click must count once. */
export async function reportEmailClick(token: string): Promise<void> {
  if (reportedClicks.has(token)) return;
  reportedClicks.add(token);
  try {
    sessionStorage.setItem(SOURCE_KEY, "Email Campaign");
  } catch {
    /* ignore */
  }
  try {
    const res = await fetch("/api/v1/email/click", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    });
    if (res.ok) {
      const data = (await res.json()) as { token?: string; session_id?: number };
      if (data?.session_id) {
        adoptVisit(data.session_id);
      }
      if (data?.token && !getToken()) {
        setToken(data.token);
        if (typeof window !== "undefined") {
          window.dispatchEvent(new CustomEvent("xe-auth-changed"));
        }
      }
    }
  } catch {
    /* ignore */
  }
}
